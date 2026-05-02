from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)

MAX_RESULT_SIZE_CHARS = 30000
PROGRESS_THRESHOLD_MS = 2000
DEFAULT_TIMEOUT_MS = 120000

BASH_SEARCH_COMMANDS = {"grep", "rg", "find", "locate", "fd", "which", "whereis", "type"}
BASH_READ_COMMANDS = {"cat", "head", "tail", "less", "more", "wc", "file", "stat", "ls"}
BASH_LIST_COMMANDS = {"ls", "dir", "tree", "find", "fd"}

DANGEROUS_PATTERNS = [
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"mkfs\.", re.IGNORECASE),
    re.compile(r"dd\s+if=", re.IGNORECASE),
    re.compile(r"chmod\s+777\s+/", re.IGNORECASE),
    re.compile(r">\s*/dev/sd[a-z]", re.IGNORECASE),
    re.compile(r"fork\s+bomb", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;", re.IGNORECASE),
    re.compile(r"shutdown\s+-h\s+now", re.IGNORECASE),
    re.compile(r"reboot", re.IGNORECASE),
    re.compile(r"sudo\s+rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"wget\s+.*\|\s*sh", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*sh", re.IGNORECASE),
    re.compile(r"git\s+push\s+--force.*origin\s+master", re.IGNORECASE),
    re.compile(r"git\s+push\s+--force.*origin\s+main", re.IGNORECASE),
]


class BashInput(BaseModel):
    command: str = Field(description="The command to execute")
    timeout: int = Field(default=DEFAULT_TIMEOUT_MS, description="Timeout in milliseconds")
    description: str = Field(default="", description="Description of the command")
    run_in_background: bool = Field(default=False, description="Whether to run in background")


class BashOutput(BaseModel):
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    interrupted: bool = Field(default=False)
    is_image: bool = Field(default=False)
    background_task_id: str | None = Field(default=None)


def _check_dangerous_command(command: str) -> str | None:
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return f"Dangerous command pattern detected: {pattern.pattern}"
    return None


def _get_command_category(command: str) -> dict[str, bool]:
    parts = command.strip().split()
    if not parts:
        return {}
    base_cmd = os.path.basename(parts[0]).lower()
    result: dict[str, bool] = {}
    if base_cmd in BASH_SEARCH_COMMANDS:
        result["isSearch"] = True
    if base_cmd in BASH_READ_COMMANDS:
        result["isRead"] = True
    if base_cmd in BASH_LIST_COMMANDS:
        result["isList"] = True
    return result


class BashTool(Tool[BashInput, BashOutput, Any]):
    @property
    def name(self) -> str:
        return "Bash"

    @property
    def input_schema(self) -> type[BashInput]:
        return BashInput

    @property
    def max_result_size_chars(self) -> int:
        return MAX_RESULT_SIZE_CHARS

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "execute shell commands"

    def is_concurrency_safe(self, input: BashInput | None = None) -> bool:
        return False

    def is_read_only(self, input: BashInput | None = None) -> bool:
        return False

    def is_destructive(self, input: BashInput | None = None) -> bool:
        return False

    def is_search_or_read_command(self, input: BashInput | None = None) -> dict[str, bool] | None:
        if input is not None:
            return _get_command_category(input.command)
        return None

    def requires_user_interaction(self) -> bool:
        return False

    async def validate_input(self, input: BashInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.command or not input.command.strip():
            errors.append("command is required")
        dangerous_msg = _check_dangerous_command(input.command)
        if dangerous_msg:
            errors.append(dangerous_msg)
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: BashInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        timeout_seconds = max(1, args.timeout / 1000.0)
        env = os.environ.copy()
        loop = asyncio.get_running_loop()
        start_time = time.time()

        async def _run():
            try:
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_shell(
                        args.command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    ),
                    timeout=timeout_seconds,
                )
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout_seconds,
                    )
                except TimeoutError:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    try:
                        stdout_bytes, stderr_bytes = await process.communicate()
                    except Exception:
                        stdout_bytes, stderr_bytes = (b"", b"")
                    elapsed = (time.time() - start_time) * 1000
                    return BashOutput(
                        stdout=stdout_bytes.decode("utf-8", errors="replace")[
                            :MAX_RESULT_SIZE_CHARS
                        ],
                        stderr=stderr_bytes.decode("utf-8", errors="replace")[
                            :MAX_RESULT_SIZE_CHARS
                        ],
                        interrupted=True,
                    )
                stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_RESULT_SIZE_CHARS]
                stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_RESULT_SIZE_CHARS]
                return BashOutput(stdout=stdout, stderr=stderr, interrupted=False)
            except TimeoutError:
                return BashOutput(
                    stdout="",
                    stderr="Command timed out",
                    interrupted=True,
                )
            except Exception as e:
                return BashOutput(
                    stdout="",
                    stderr=str(e),
                    interrupted=True,
                )

        if args.run_in_background:
            task_id = str(uuid.uuid4())
            asyncio.create_task(_run())
            return ToolCallResult(
                data=BashOutput(
                    stdout="",
                    stderr="",
                    interrupted=False,
                    background_task_id=task_id,
                )
            )

        result = await _run()
        return ToolCallResult(data=result)

    async def description(self, input: BashInput, options: dict[str, Any]) -> str:
        return f"Execute: {input.command}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Execute shell commands"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: BashInput) -> Any:
        return input.command

    def map_tool_result_to_tool_result_block_param(
        self, content: BashOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

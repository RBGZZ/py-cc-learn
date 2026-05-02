from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)

MAX_EDIT_FILE_SIZE = 1 * 1024 * 1024 * 1024


class ReadInput(BaseModel):
    file_path: str = Field(description="Path to the file to read")
    offset: int = Field(default=1, description="Line number to start reading from")
    limit: int | None = Field(default=None, description="Maximum number of lines to read")


class ReadOutput(BaseModel):
    type: str = Field(default="text")
    file_path: str = Field(default="")
    content: str = Field(default="")
    num_lines: int = Field(default=0)
    start_line: int = Field(default=1)
    total_lines: int = Field(default=0)


def _is_binary_file(file_path: str) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
            text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
            non_text = chunk.translate(None, text_chars)
            return len(non_text) / max(len(chunk), 1) > 0.30
    except Exception:
        return False


class FileReadTool(Tool[ReadInput, ReadOutput, Any]):
    @property
    def name(self) -> str:
        return "Read"

    @property
    def input_schema(self) -> type[ReadInput]:
        return ReadInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "read file contents with line numbers"

    def is_concurrency_safe(self, input: ReadInput | None = None) -> bool:
        return True

    def is_read_only(self, input: ReadInput | None = None) -> bool:
        return True

    def is_destructive(self, input: ReadInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: ReadInput | None = None) -> bool:
        return True

    def get_path(self, input: ReadInput) -> str | None:
        return input.file_path

    async def validate_input(self, input: ReadInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.file_path or not input.file_path.strip():
            errors.append("file_path is required")
        if input.offset < 1:
            errors.append("offset must be >= 1")
        if input.limit is not None and input.limit < 1:
            errors.append("limit must be >= 1")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: ReadInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        resolved_path = os.path.abspath(os.path.expanduser(args.file_path))
        try:
            file_size = os.path.getsize(resolved_path)
        except OSError:
            return ToolCallResult(
                data=ReadOutput(
                    type="text",
                    file_path=resolved_path,
                    content=f"Error reading file: File not found at '{resolved_path}'",
                    num_lines=0,
                    start_line=args.offset,
                    total_lines=0,
                )
            )
        if file_size > MAX_EDIT_FILE_SIZE:
            return ToolCallResult(
                data=ReadOutput(
                    type="text",
                    file_path=resolved_path,
                    content=f"Error: File exceeds maximum size of {MAX_EDIT_FILE_SIZE} bytes",
                    num_lines=0,
                    start_line=args.offset,
                    total_lines=0,
                )
            )
        if _is_binary_file(resolved_path):
            return ToolCallResult(
                data=ReadOutput(
                    type="image",
                    file_path=resolved_path,
                    content="Binary file detected",
                    num_lines=0,
                    start_line=args.offset,
                    total_lines=0,
                )
            )
        try:
            with open(resolved_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except PermissionError:
            return ToolCallResult(
                data=ReadOutput(
                    type="text",
                    file_path=resolved_path,
                    content=f"Error: Permission denied reading '{resolved_path}'",
                    num_lines=0,
                    start_line=args.offset,
                    total_lines=0,
                )
            )
        except Exception as e:
            return ToolCallResult(
                data=ReadOutput(
                    type="text",
                    file_path=resolved_path,
                    content=f"Error reading file: {e}",
                    num_lines=0,
                    start_line=args.offset,
                    total_lines=0,
                )
            )
        total_lines = len(lines)
        start_idx = max(0, args.offset - 1)
        end_idx = total_lines
        if args.limit is not None:
            end_idx = min(total_lines, start_idx + args.limit)
        selected = lines[start_idx:end_idx]
        numbered = []
        for i, line in enumerate(selected):
            line_num = start_idx + i + 1
            numbered.append(f"{line_num}\t{line}")
        content = "".join(numbered)
        return ToolCallResult(
            data=ReadOutput(
                type="text",
                file_path=resolved_path,
                content=content,
                num_lines=len(selected),
                start_line=start_idx + 1,
                total_lines=total_lines,
            )
        )

    async def description(self, input: ReadInput, options: dict[str, Any]) -> str:
        return f"Read {input.file_path}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Read file contents"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: ReadInput) -> Any:
        return input.file_path

    def map_tool_result_to_tool_result_block_param(
        self, content: ReadOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

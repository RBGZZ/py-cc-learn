from __future__ import annotations

import glob as glob_module
import os
import time
from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)

DEFAULT_MAX_RESULTS = 100


class GlobInput(BaseModel):
    pattern: str = Field(description="The glob pattern to match files against")
    path: str | None = Field(default=None, description="Directory to search in")


class GlobOutput(BaseModel):
    duration_ms: int = Field(default=0)
    num_files: int = Field(default=0)
    filenames: list[str] = Field(default_factory=list)
    truncated: bool = Field(default=False)


class GlobTool(Tool[GlobInput, GlobOutput, Any]):
    @property
    def name(self) -> str:
        return "Glob"

    @property
    def input_schema(self) -> type[GlobInput]:
        return GlobInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "find files by glob pattern"

    def is_concurrency_safe(self, input: GlobInput | None = None) -> bool:
        return True

    def is_read_only(self, input: GlobInput | None = None) -> bool:
        return True

    def is_destructive(self, input: GlobInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    async def validate_input(self, input: GlobInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.pattern or not input.pattern.strip():
            errors.append("pattern is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: GlobInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        start = time.time()
        search_path = args.path
        if search_path:
            search_path = os.path.abspath(os.path.expanduser(search_path))
        else:
            search_path = os.getcwd()
        normalized_pattern = os.path.join(search_path, args.pattern)
        all_files = glob_module.glob(normalized_pattern, recursive=True)
        if os.name == "nt":
            alt_pattern = args.pattern.replace("/", "\\")
            alt_full = os.path.join(search_path, alt_pattern)
            if alt_full != normalized_pattern:
                extra = glob_module.glob(alt_full, recursive=True)
                all_files = list(set(all_files + extra))
        all_files = sorted([os.path.normpath(f) for f in all_files if os.path.isfile(f)])
        total = len(all_files)
        truncated = total > DEFAULT_MAX_RESULTS
        result_files = all_files[:DEFAULT_MAX_RESULTS]
        elapsed = int((time.time() - start) * 1000)
        return ToolCallResult(
            data=GlobOutput(
                duration_ms=elapsed,
                num_files=total,
                filenames=result_files,
                truncated=truncated,
            )
        )

    async def description(self, input: GlobInput, options: dict[str, Any]) -> str:
        return f"Find files matching {input.pattern}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Find files matching a glob pattern"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: GlobInput) -> Any:
        return input.pattern

    def map_tool_result_to_tool_result_block_param(
        self, content: GlobOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

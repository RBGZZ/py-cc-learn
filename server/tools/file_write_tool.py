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

MAX_RESULT_SIZE_CHARS = 100000


class WriteInput(BaseModel):
    file_path: str = Field(description="Path to the file to write")
    content: str = Field(description="Content to write to the file")


class WriteOutput(BaseModel):
    type: str = Field(default="create")
    file_path: str = Field(default="")
    content: str = Field(default="")
    structured_patch: list[Any] = Field(default_factory=list)
    original_file: str | None = Field(default=None)


class FileWriteTool(Tool[WriteInput, WriteOutput, Any]):
    @property
    def name(self) -> str:
        return "Write"

    @property
    def input_schema(self) -> type[WriteInput]:
        return WriteInput

    @property
    def max_result_size_chars(self) -> int:
        return MAX_RESULT_SIZE_CHARS

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "write or create files"

    def is_concurrency_safe(self, input: WriteInput | None = None) -> bool:
        return False

    def is_read_only(self, input: WriteInput | None = None) -> bool:
        return False

    def is_destructive(self, input: WriteInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: WriteInput | None = None) -> bool:
        return True

    def get_path(self, input: WriteInput) -> str | None:
        return input.file_path

    async def validate_input(self, input: WriteInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.file_path or not input.file_path.strip():
            errors.append("file_path is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: WriteInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        resolved_path = os.path.abspath(os.path.expanduser(args.file_path))
        existed = os.path.exists(resolved_path)
        original_file: str | None = None
        if existed:
            try:
                with open(resolved_path, encoding="utf-8", errors="replace") as f:
                    original_file = f.read()
            except Exception:
                original_file = None
        try:
            os.makedirs(os.path.dirname(resolved_path) or ".", exist_ok=True)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(args.content)
        except Exception as e:
            return ToolCallResult(
                data=WriteOutput(
                    type="create" if not existed else "update",
                    file_path=resolved_path,
                    content=f"Error writing file: {e}",
                    structured_patch=[],
                    original_file=original_file,
                )
            )

        diff_summary = ""
        try:
            from server.utils.git import get_git_diff_summary

            diff_summary = await get_git_diff_summary()
        except Exception:
            pass

        result_messages: list[dict[str, Any]] = []
        if diff_summary:
            result_messages.append({"type": "text", "text": f"Diff summary:\n{diff_summary}"})

        return ToolCallResult(
            data=WriteOutput(
                type="create" if not existed else "update",
                file_path=resolved_path,
                content=args.content[:MAX_RESULT_SIZE_CHARS],
                structured_patch=[],
                original_file=original_file,
            ),
            new_messages=result_messages if result_messages else None,
        )

    async def description(self, input: WriteInput, options: dict[str, Any]) -> str:
        return f"Write to {input.file_path}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Write file contents"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: WriteInput) -> Any:
        return input.file_path

    def map_tool_result_to_tool_result_block_param(
        self, content: WriteOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

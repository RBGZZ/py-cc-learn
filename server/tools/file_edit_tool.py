from __future__ import annotations

import difflib
import os
from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class EditInput(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    old_string: str = Field(description="The text to replace")
    new_string: str = Field(description="The text to replace it with")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


class EditOutput(BaseModel):
    file_path: str = Field(default="")
    old_string: str = Field(default="")
    new_string: str = Field(default="")
    original_file: str | None = Field(default=None)
    structured_patch: list[Any] = Field(default_factory=list)
    replace_all: bool = Field(default=False)
    user_modified: bool = Field(default=False)


class FileEditTool(Tool[EditInput, EditOutput, Any]):
    @property
    def name(self) -> str:
        return "Edit"

    @property
    def input_schema(self) -> type[EditInput]:
        return EditInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "edit files with search and replace"

    def is_concurrency_safe(self, input: EditInput | None = None) -> bool:
        return False

    def is_read_only(self, input: EditInput | None = None) -> bool:
        return False

    def is_destructive(self, input: EditInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: EditInput | None = None) -> bool:
        return True

    def get_path(self, input: EditInput) -> str | None:
        return input.file_path

    async def validate_input(self, input: EditInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.file_path or not input.file_path.strip():
            errors.append("file_path is required")
        if not input.old_string:
            errors.append("old_string is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: EditInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        resolved_path = os.path.abspath(os.path.expanduser(args.file_path))
        try:
            with open(resolved_path, encoding="utf-8") as f:
                original_file = f.read()
        except FileNotFoundError:
            return ToolCallResult(
                data=EditOutput(
                    file_path=resolved_path,
                    old_string=args.old_string,
                    new_string=args.new_string,
                    original_file=None,
                    structured_patch=[],
                    replace_all=args.replace_all,
                    user_modified=False,
                ),
                new_messages=[
                    {
                        "type": "text",
                        "text": f"Error: File not found at '{resolved_path}'",
                    }
                ],
            )
        except PermissionError:
            return ToolCallResult(
                data=EditOutput(
                    file_path=resolved_path,
                    old_string=args.old_string,
                    new_string=args.new_string,
                    original_file=None,
                    structured_patch=[],
                    replace_all=args.replace_all,
                    user_modified=False,
                ),
                new_messages=[
                    {
                        "type": "text",
                        "text": f"Error: Permission denied reading '{resolved_path}'",
                    }
                ],
            )
        if args.replace_all:
            count = original_file.count(args.old_string)
            if count == 0:
                return ToolCallResult(
                    data=EditOutput(
                        file_path=resolved_path,
                        old_string=args.old_string,
                        new_string=args.new_string,
                        original_file=original_file,
                        structured_patch=[],
                        replace_all=args.replace_all,
                        user_modified=False,
                    ),
                    new_messages=[
                        {
                            "type": "text",
                            "text": "Error: old_string not found in file (even after relaxing whitespace). If you are unsure of the exact string to replace or the current file contents, read the file and try again.",
                        }
                    ],
                )
            new_content = original_file.replace(args.old_string, args.new_string)
        else:
            count = original_file.count(args.old_string)
            if count == 0:
                return ToolCallResult(
                    data=EditOutput(
                        file_path=resolved_path,
                        old_string=args.old_string,
                        new_string=args.new_string,
                        original_file=original_file,
                        structured_patch=[],
                        replace_all=False,
                        user_modified=False,
                    ),
                    new_messages=[
                        {
                            "type": "text",
                            "text": "Error: old_string not found in file (even after relaxing whitespace). If you are unsure of the exact string to replace or the current file contents, read the file and try again.",
                        }
                    ],
                )
            if count > 1:
                lines_info = []
                for idx, _ in enumerate(original_file.split(args.old_string)[:-1]):
                    pos = 0
                    for i in range(idx + 1):
                        pos = original_file.index(args.old_string, pos) + len(args.old_string)
                    pos -= len(args.old_string)
                    line_num = original_file[:pos].count("\n") + 1
                    lines_info.append(str(line_num))
                return ToolCallResult(
                    data=EditOutput(
                        file_path=resolved_path,
                        old_string=args.old_string,
                        new_string=args.new_string,
                        original_file=original_file,
                        structured_patch=[],
                        replace_all=False,
                        user_modified=False,
                    ),
                    new_messages=[
                        {
                            "type": "text",
                            "text": f"Error: Found {count} matches of the string to replace. Add more lines/context to old_string to make it unique. Matches found on lines: {', '.join(lines_info)}. Alternatively, set replace_all=True to replace all occurrences.",
                        }
                    ],
                )
            new_content = original_file.replace(args.old_string, args.new_string, 1)
        patch_lines = list(
            difflib.unified_diff(
                original_file.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=resolved_path,
                tofile=resolved_path,
            )
        )
        structured_patch = []
        for line in patch_lines:
            if line.startswith("@@"):
                structured_patch.append({"type": "hunk_header", "text": line.rstrip("\n")})
            elif line.startswith("+"):
                structured_patch.append({"type": "added", "text": line.rstrip("\n")})
            elif line.startswith("-"):
                structured_patch.append({"type": "removed", "text": line.rstrip("\n")})
            elif line.startswith(" "):
                structured_patch.append({"type": "context", "text": line.rstrip("\n")})
        try:
            os.makedirs(os.path.dirname(resolved_path) or ".", exist_ok=True)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return ToolCallResult(
                data=EditOutput(
                    file_path=resolved_path,
                    old_string=args.old_string,
                    new_string=args.new_string,
                    original_file=original_file,
                    structured_patch=structured_patch,
                    replace_all=args.replace_all,
                    user_modified=True,
                ),
                new_messages=[{"type": "text", "text": f"Error writing file: {e}"}],
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
            data=EditOutput(
                file_path=resolved_path,
                old_string=args.old_string,
                new_string=args.new_string,
                original_file=original_file,
                structured_patch=structured_patch,
                replace_all=args.replace_all,
                user_modified=False,
            ),
            new_messages=result_messages if result_messages else None,
        )

    async def description(self, input: EditInput, options: dict[str, Any]) -> str:
        return f"Edit {input.file_path}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Edit file contents with search and replace"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: EditInput) -> Any:
        return input.file_path

    def map_tool_result_to_tool_result_block_param(
        self, content: EditOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

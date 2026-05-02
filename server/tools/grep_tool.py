from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any, Literal

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)

DEFAULT_HEAD_LIMIT = 250
EXCLUDED_DIRS = {".git", ".svn", ".hg", ".hgrc", ".bzr", "CVS"}


class GrepInput(BaseModel):
    pattern: str = Field(description="The regular expression pattern to search for")
    path: str | None = Field(default=None, description="File or directory to search in")
    glob: str | None = Field(default=None, description="Glob pattern to filter files")
    output_mode: Literal["content", "files_with_matches", "count"] = Field(
        default="files_with_matches"
    )
    B: int | None = Field(default=None, alias="-B")
    A: int | None = Field(default=None, alias="-A")
    C: int | None = Field(default=None, alias="-C")
    n: bool = Field(default=True, alias="-n")
    i: bool = Field(default=False, alias="-i")
    type: str | None = Field(default=None)
    head_limit: int = Field(default=DEFAULT_HEAD_LIMIT)
    multiline: bool = Field(default=False)


class GrepOutput(BaseModel):
    num_files: int = Field(default=0)
    filenames: list[str] = Field(default_factory=list)
    content: str | None = Field(default=None)
    num_lines: int | None = Field(default=None)


def _walk_files(root: str, file_glob: str | None = None) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            if file_glob is not None:
                try:
                    if not re.match(
                        file_glob.replace(".", r"\.").replace("*", ".*").replace("?", "."),
                        fname,
                    ):
                        continue
                except re.error:
                    pass
            yield full


def _glob_to_regex(glob_pattern: str) -> str:
    return (
        glob_pattern.replace(".", r"\.")
        .replace("**", "___DOUBLESTAR___")
        .replace("*", "[^/]*")
        .replace("___DOUBLESTAR___", ".*")
        .replace("?", "[^/]")
    )


class GrepTool(Tool[GrepInput, GrepOutput, Any]):
    @property
    def name(self) -> str:
        return "Grep"

    @property
    def input_schema(self) -> type[GrepInput]:
        return GrepInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "search file contents with regex"

    def is_concurrency_safe(self, input: GrepInput | None = None) -> bool:
        return True

    def is_read_only(self, input: GrepInput | None = None) -> bool:
        return True

    def is_destructive(self, input: GrepInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    async def validate_input(self, input: GrepInput, context: Any) -> ValidationResult:
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
        args: GrepInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        search_path = args.path
        if search_path:
            search_path = os.path.abspath(os.path.expanduser(search_path))
        else:
            search_path = os.getcwd()
        flags = 0
        if args.i:
            flags |= re.IGNORECASE
        if args.multiline:
            flags |= re.DOTALL
        try:
            regex = re.compile(args.pattern, flags)
        except re.error as e:
            return ToolCallResult(
                data=GrepOutput(
                    num_files=0,
                    filenames=[],
                    content=f"Invalid regex pattern: {e}",
                    num_lines=0,
                )
            )
        context_before = args.C if args.B is None and args.C is not None else (args.B or 0)
        context_after = args.C if args.A is None and args.C is not None else (args.A or 0)
        file_glob = args.glob
        if os.path.isfile(search_path):
            files = [search_path]
        else:
            files = list(_walk_files(search_path, file_glob))
            files.sort()
        matched_files: list[str] = []
        output_lines: list[str] = []
        total_lines = 0
        for filepath in files:
            try:
                with open(filepath, encoding="utf-8", errors="replace") as f:
                    file_lines = f.readlines()
            except (OSError, UnicodeDecodeError):
                continue
            file_matches: list[int] = []
            if args.multiline:
                content = "".join(file_lines)
                for m in regex.finditer(content):
                    start_line = content[: m.start()].count("\n")
                    end_line = content[: m.end()].count("\n")
                    for ln in range(start_line, end_line + 1):
                        if ln not in file_matches:
                            file_matches.append(ln)
            else:
                for idx, line in enumerate(file_lines):
                    if regex.search(line):
                        file_matches.append(idx)
            if not file_matches:
                continue
            matched_files.append(filepath)
            if args.output_mode == "files_with_matches":
                if len(matched_files) <= args.head_limit:
                    continue
            elif args.output_mode == "count":
                output_lines.append(f"{filepath}:{len(file_matches)}")
                total_lines += 1
                if total_lines >= args.head_limit:
                    break
            else:
                printed: set[int] = set()
                for match_line in file_matches:
                    start = max(0, match_line - context_before)
                    end = min(len(file_lines), match_line + context_after + 1)
                    for ln in range(start, end):
                        if ln in printed:
                            continue
                        printed.add(ln)
                        line_num = ln + 1
                        prefix = ""
                        if context_before > 0 or context_after > 0:
                            if ln == match_line:
                                prefix = f"{filepath}:"
                            else:
                                prefix = f"{filepath}-"
                        else:
                            prefix = f"{filepath}:"
                        line_prefix = f"{line_num}:" if args.n else ""
                        output_lines.append(f"{prefix}{line_prefix}{file_lines[ln].rstrip()}")
                        total_lines += 1
                        if total_lines >= args.head_limit:
                            break
                    if total_lines >= args.head_limit:
                        break
                    if match_line + context_after < end - 1:
                        output_lines.append("--")
                        total_lines += 1
                if total_lines >= args.head_limit:
                    break
        if args.output_mode == "files_with_matches":
            matched_files = matched_files[: args.head_limit]
            return ToolCallResult(
                data=GrepOutput(
                    num_files=len(matched_files),
                    filenames=matched_files,
                    content=None,
                    num_lines=None,
                )
            )
        elif args.output_mode == "count":
            return ToolCallResult(
                data=GrepOutput(
                    num_files=len(matched_files),
                    filenames=matched_files,
                    content="\n".join(output_lines[: args.head_limit]),
                    num_lines=min(total_lines, args.head_limit),
                )
            )
        else:
            return ToolCallResult(
                data=GrepOutput(
                    num_files=len(matched_files),
                    filenames=matched_files,
                    content="\n".join(output_lines),
                    num_lines=total_lines,
                )
            )

    async def description(self, input: GrepInput, options: dict[str, Any]) -> str:
        return f"Search for '{input.pattern}'"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Search file contents with regex"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: GrepInput) -> Any:
        return input.pattern

    def map_tool_result_to_tool_result_block_param(
        self, content: GrepOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

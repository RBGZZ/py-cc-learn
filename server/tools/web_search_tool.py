from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)

MIN_QUERY_LENGTH = 2


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query to execute", min_length=MIN_QUERY_LENGTH)
    allowed_domains: list[str] | None = Field(
        default=None, description="Domains to include in search results"
    )
    blocked_domains: list[str] | None = Field(
        default=None, description="Domains to exclude from search results"
    )


class SearchResultItem(BaseModel):
    title: str = Field(default="")
    url: str = Field(default="")
    snippet: str = Field(default="")


class WebSearchOutput(BaseModel):
    query: str = Field(default="")
    results: list[SearchResultItem] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0)


class WebSearchTool(Tool[WebSearchInput, WebSearchOutput, Any]):
    @property
    def name(self) -> str:
        return "WebSearch"

    @property
    def input_schema(self) -> type[WebSearchInput]:
        return WebSearchInput

    @property
    def max_result_size_chars(self) -> int:
        return 50000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "search the web for information"

    def is_concurrency_safe(self, input: WebSearchInput | None = None) -> bool:
        return True

    def is_read_only(self, input: WebSearchInput | None = None) -> bool:
        return True

    def is_destructive(self, input: WebSearchInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: WebSearchInput | None = None) -> bool:
        return True

    async def validate_input(self, input: WebSearchInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.query or len(input.query.strip()) < MIN_QUERY_LENGTH:
            errors.append(f"query must be at least {MIN_QUERY_LENGTH} characters")
        if input.allowed_domains and input.blocked_domains:
            errors.append("cannot set both allowed_domains and blocked_domains")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: WebSearchInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        start = time.time()
        placeholder_results = [
            SearchResultItem(
                title="Web search requires API key configuration",
                url="",
                snippet=(
                    "This is a placeholder. To enable real web search, configure a search API key "
                    "(e.g., Google Custom Search, Bing Search API, or Tavily). "
                    f"Query was: '{args.query}'"
                ),
            )
        ]
        elapsed = time.time() - start
        return ToolCallResult(
            data=WebSearchOutput(
                query=args.query,
                results=placeholder_results,
                duration_seconds=round(elapsed, 3),
            )
        )

    async def description(self, input: WebSearchInput, options: dict[str, Any]) -> str:
        return f"Web search: {input.query}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Search the web for information"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: WebSearchInput) -> Any:
        return input.query

    def map_tool_result_to_tool_result_block_param(
        self, content: WebSearchOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

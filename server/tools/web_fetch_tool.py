from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch")
    prompt: str = Field(description="The prompt describing what to extract from the page")


class WebFetchOutput(BaseModel):
    bytes: int = Field(default=0)
    code: int = Field(default=200)
    code_text: str = Field(default="OK")
    result: str = Field(default="")
    duration_ms: int = Field(default=0)
    url: str = Field(default="")


class WebFetchTool(Tool[WebFetchInput, WebFetchOutput, Any]):
    @property
    def name(self) -> str:
        return "WebFetch"

    @property
    def input_schema(self) -> type[WebFetchInput]:
        return WebFetchInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "fetch content from a URL"

    def is_concurrency_safe(self, input: WebFetchInput | None = None) -> bool:
        return True

    def is_read_only(self, input: WebFetchInput | None = None) -> bool:
        return True

    def is_destructive(self, input: WebFetchInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: WebFetchInput | None = None) -> bool:
        return True

    async def validate_input(self, input: WebFetchInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.url or not input.url.strip():
            errors.append("url is required")
        if not input.prompt or not input.prompt.strip():
            errors.append("prompt is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: WebFetchInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        start = time.time()
        normalized_url = args.url
        if not normalized_url.startswith(("http://", "https://")):
            normalized_url = f"https://{normalized_url}"
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": "ClaudeCode/1.0",
                    "Accept": "text/html,text/plain,*/*",
                },
            ) as client:
                response = await client.get(normalized_url)
                status_code = response.status_code
                status_text = (
                    httpx.codes.get_reason_phrase(status_code)
                    if hasattr(httpx, "codes")
                    else "Unknown"
                )
                content_bytes = response.content
                byte_count = len(content_bytes)
                try:
                    text = response.text[:100000]
                except Exception:
                    text = content_bytes.decode("utf-8", errors="replace")[:100000]
                elapsed = int((time.time() - start) * 1000)
                return ToolCallResult(
                    data=WebFetchOutput(
                        bytes=byte_count,
                        code=status_code,
                        code_text=str(status_text),
                        result=text,
                        duration_ms=elapsed,
                        url=normalized_url,
                    )
                )
        except httpx.TimeoutException:
            elapsed = int((time.time() - start) * 1000)
            return ToolCallResult(
                data=WebFetchOutput(
                    bytes=0,
                    code=408,
                    code_text="Request Timeout",
                    result="Error: Request timed out",
                    duration_ms=elapsed,
                    url=normalized_url,
                )
            )
        except httpx.ConnectError:
            elapsed = int((time.time() - start) * 1000)
            return ToolCallResult(
                data=WebFetchOutput(
                    bytes=0,
                    code=0,
                    code_text="Connection Error",
                    result=f"Error: Could not connect to {normalized_url}",
                    duration_ms=elapsed,
                    url=normalized_url,
                )
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            return ToolCallResult(
                data=WebFetchOutput(
                    bytes=0,
                    code=0,
                    code_text="Error",
                    result=f"Error fetching URL: {e}",
                    duration_ms=elapsed,
                    url=normalized_url,
                )
            )

    async def description(self, input: WebFetchInput, options: dict[str, Any]) -> str:
        return f"Fetch {input.url}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Fetch content from a URL"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: WebFetchInput) -> Any:
        return input.url

    def map_tool_result_to_tool_result_block_param(
        self, content: WebFetchOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

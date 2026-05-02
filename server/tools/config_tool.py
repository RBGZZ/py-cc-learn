from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class ConfigInput(BaseModel):
    key: str = Field(description="Configuration key to read or write")
    value: str | None = Field(
        default=None,
        description="Value to set (omit to read current value)",
    )


class ConfigOutput(BaseModel):
    key: str = Field(default="")
    value: str | None = Field(default=None)
    action: str = Field(default="read")


class ConfigTool(Tool[ConfigInput, ConfigOutput, Any]):
    @property
    def name(self) -> str:
        return "Config"

    @property
    def input_schema(self) -> type[ConfigInput]:
        return ConfigInput

    @property
    def max_result_size_chars(self) -> int:
        return 10000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "read or update agent configuration"

    def is_concurrency_safe(self, input: ConfigInput | None = None) -> bool:
        return True

    def is_read_only(self, input: ConfigInput | None = None) -> bool:
        return input.value is None if input else True

    def is_destructive(self, input: ConfigInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: ConfigInput | None = None) -> bool:
        return False

    def get_path(self, input: ConfigInput) -> str | None:
        return None

    async def validate_input(self, input: ConfigInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.key or not input.key.strip():
            errors.append("key is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: ConfigInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        if args.value is not None:
            return ToolCallResult(
                data=ConfigOutput(
                    key=args.key,
                    value=args.value,
                    action="write",
                ),
                new_messages=[
                    {
                        "type": "text",
                        "text": f"Config '{args.key}' set to: {args.value}",
                    }
                ],
            )
        else:
            return ToolCallResult(
                data=ConfigOutput(
                    key=args.key,
                    value="(not set)",
                    action="read",
                ),
                new_messages=[
                    {
                        "type": "text",
                        "text": f"Config '{args.key}': (not set)",
                    }
                ],
            )

    async def description(self, input: ConfigInput, options: dict[str, Any]) -> str:
        action = "Set" if input.value is not None else "Get"
        return f"{action} config: {input.key}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Read or update agent configuration"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return "Config"

    def to_auto_classifier_input(self, input: ConfigInput) -> Any:
        return input.key

    def map_tool_result_to_tool_result_block_param(
        self, content: ConfigOutput, tool_use_id: str
    ) -> Any:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content.model_dump(),
        }

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

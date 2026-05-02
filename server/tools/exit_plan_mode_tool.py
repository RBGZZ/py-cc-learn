from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class ExitPlanModeInput(BaseModel):
    confirm: bool = Field(default=True, description="Confirm exiting plan mode")


class ExitPlanModeOutput(BaseModel):
    status: str = Field(default="plan_mode_exited")


class ExitPlanModeTool(Tool[ExitPlanModeInput, ExitPlanModeOutput, Any]):
    @property
    def name(self) -> str:
        return "ExitPlanMode"

    @property
    def input_schema(self) -> type[ExitPlanModeInput]:
        return ExitPlanModeInput

    @property
    def max_result_size_chars(self) -> int:
        return 10000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "exit plan mode and return to normal execution"

    def is_concurrency_safe(self, input: ExitPlanModeInput | None = None) -> bool:
        return False

    def is_read_only(self, input: ExitPlanModeInput | None = None) -> bool:
        return True

    def is_destructive(self, input: ExitPlanModeInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: ExitPlanModeInput | None = None) -> bool:
        return False

    def get_path(self, input: ExitPlanModeInput) -> str | None:
        return None

    async def validate_input(self, input: ExitPlanModeInput, context: Any) -> ValidationResult:
        return ValidationResult(valid=True)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: ExitPlanModeInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        return ToolCallResult(
            data=ExitPlanModeOutput(
                status="plan_mode_exited",
            ),
            context_modifier={
                "permission_mode": "default",
            },
            new_messages=[
                {
                    "type": "text",
                    "text": "Plan mode exited. Returning to normal execution mode.",
                }
            ],
        )

    async def description(self, input: ExitPlanModeInput, options: dict[str, Any]) -> str:
        return "Exit plan mode"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Exit plan mode and return to normal execution"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return "Exit Plan"

    def to_auto_classifier_input(self, input: ExitPlanModeInput) -> Any:
        return "exit plan mode"

    def map_tool_result_to_tool_result_block_param(
        self, content: ExitPlanModeOutput, tool_use_id: str
    ) -> Any:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content.model_dump(),
        }

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

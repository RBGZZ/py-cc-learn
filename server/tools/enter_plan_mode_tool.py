from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class EnterPlanModeInput(BaseModel):
    plan: str = Field(description="The plan description")


class EnterPlanModeOutput(BaseModel):
    status: str = Field(default="plan_mode_entered")
    plan: str = Field(default="")


class EnterPlanModeTool(Tool[EnterPlanModeInput, EnterPlanModeOutput, Any]):
    @property
    def name(self) -> str:
        return "EnterPlanMode"

    @property
    def input_schema(self) -> type[EnterPlanModeInput]:
        return EnterPlanModeInput

    @property
    def max_result_size_chars(self) -> int:
        return 50000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "enter plan mode to formulate a plan before making changes"

    def is_concurrency_safe(self, input: EnterPlanModeInput | None = None) -> bool:
        return False

    def is_read_only(self, input: EnterPlanModeInput | None = None) -> bool:
        return True

    def is_destructive(self, input: EnterPlanModeInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: EnterPlanModeInput | None = None) -> bool:
        return False

    def get_path(self, input: EnterPlanModeInput) -> str | None:
        return None

    async def validate_input(self, input: EnterPlanModeInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.plan or not input.plan.strip():
            errors.append("plan is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: EnterPlanModeInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        return ToolCallResult(
            data=EnterPlanModeOutput(
                status="plan_mode_entered",
                plan=args.plan,
            ),
            context_modifier={
                "permission_mode": "plan",
                "plan_content": args.plan,
            },
            new_messages=[
                {
                    "type": "text",
                    "text": f"Plan mode entered. Plan summary: {args.plan[:200]}",
                }
            ],
        )

    async def description(self, input: EnterPlanModeInput, options: dict[str, Any]) -> str:
        return "Enter plan mode"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Enter plan mode to formulate a plan before making changes"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return "Plan Mode"

    def to_auto_classifier_input(self, input: EnterPlanModeInput) -> Any:
        return "enter plan mode"

    def map_tool_result_to_tool_result_block_param(
        self, content: EnterPlanModeOutput, tool_use_id: str
    ) -> Any:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content.model_dump(),
        }

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

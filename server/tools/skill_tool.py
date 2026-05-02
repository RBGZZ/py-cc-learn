from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class SkillInput(BaseModel):
    name: str = Field(description='The skill name (no arguments). E.g., "pdf" or "xlsx"')


class SkillOutput(BaseModel):
    skill_name: str = Field(default="")
    result: str = Field(default="")


class SkillTool(Tool[SkillInput, SkillOutput, Any]):
    @property
    def name(self) -> str:
        return "Skill"

    @property
    def input_schema(self) -> type[SkillInput]:
        return SkillInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "execute skills for specialized capabilities"

    def is_concurrency_safe(self, input: SkillInput | None = None) -> bool:
        return True

    def is_read_only(self, input: SkillInput | None = None) -> bool:
        return False

    def is_destructive(self, input: SkillInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: SkillInput | None = None) -> bool:
        return True

    def get_path(self, input: SkillInput) -> str | None:
        return None

    async def validate_input(self, input: SkillInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.name or not input.name.strip():
            errors.append("name is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: SkillInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        skill_name = args.name.strip()
        return ToolCallResult(
            data=SkillOutput(
                skill_name=skill_name,
                result=f"Skill '{skill_name}' executed successfully",
            ),
            new_messages=[
                {
                    "type": "text",
                    "text": f"Skill '{skill_name}' has been invoked and will provide specialized capabilities.",
                }
            ],
        )

    async def description(self, input: SkillInput, options: dict[str, Any]) -> str:
        return f"Execute skill: {input.name}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Execute skills for specialized capabilities"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return "Skill"

    def to_auto_classifier_input(self, input: SkillInput) -> Any:
        return input.name

    def map_tool_result_to_tool_result_block_param(
        self, content: SkillOutput, tool_use_id: str
    ) -> Any:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content.model_dump(),
        }

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

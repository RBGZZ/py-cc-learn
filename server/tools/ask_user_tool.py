from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class AskUserInput(BaseModel):
    questions: list[dict[str, Any]] = Field(description="Questions to ask the user (1-4 questions)")


class AskUserOutput(BaseModel):
    answers: list[dict[str, Any]] = Field(default_factory=list)
    status: str = Field(default="pending")


class AskUserQuestionTool(Tool[AskUserInput, AskUserOutput, Any]):
    @property
    def name(self) -> str:
        return "AskUserQuestion"

    @property
    def input_schema(self) -> type[AskUserInput]:
        return AskUserInput

    @property
    def max_result_size_chars(self) -> int:
        return 50000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "ask the user questions when clarification is needed"

    def is_concurrency_safe(self, input: AskUserInput | None = None) -> bool:
        return False

    def is_read_only(self, input: AskUserInput | None = None) -> bool:
        return True

    def is_destructive(self, input: AskUserInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return True

    def is_open_world(self, input: AskUserInput | None = None) -> bool:
        return False

    def get_path(self, input: AskUserInput) -> str | None:
        return None

    async def validate_input(self, input: AskUserInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.questions or len(input.questions) == 0:
            errors.append("questions is required (1-4 questions)")
        elif len(input.questions) > 4:
            errors.append("maximum 4 questions allowed")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: AskUserInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        formatted_questions: list[str] = []
        for q in args.questions:
            header = q.get("header", "")
            question = q.get("question", "")
            options = q.get("options", [])
            multi = q.get("multiSelect", False)

            lines = [f"**{header}**: {question}"]
            for opt in options:
                label = opt.get("label", "")
                desc = opt.get("description", "")
                lines.append(f"  - {label}: {desc}")
            if multi:
                lines.append("  (Multiple selections allowed)")
            formatted_questions.append("\n".join(lines))

        return ToolCallResult(
            data=AskUserOutput(
                answers=[],
                status="pending",
            ),
            new_messages=[
                {
                    "type": "text",
                    "text": "Please answer the following question(s):\n\n"
                    + "\n\n".join(formatted_questions),
                }
            ],
        )

    async def description(self, input: AskUserInput, options: dict[str, Any]) -> str:
        headers = [q.get("header", "") for q in input.questions[:2]]
        return f"Ask user: {'; '.join(headers)}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Ask user questions when you need clarification"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return "Ask User"

    def to_auto_classifier_input(self, input: AskUserInput) -> Any:
        return "ask user"

    def map_tool_result_to_tool_result_block_param(
        self, content: AskUserOutput, tool_use_id: str
    ) -> Any:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content.model_dump(),
        }

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)


class TaskStopInput(BaseModel):
    reason: str = Field(
        default="Not specified",
        description="The reason for stopping the task",
    )


class TaskStopOutput(BaseModel):
    stopped: bool = Field(default=True)
    reason: str = Field(default="")


class TaskStopTool(Tool[TaskStopInput, TaskStopOutput, Any]):
    @property
    def name(self) -> str:
        return "TaskStop"

    @property
    def input_schema(self) -> type[TaskStopInput]:
        return TaskStopInput

    @property
    def max_result_size_chars(self) -> int:
        return 10000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "stop a running task"

    def is_concurrency_safe(self, input: TaskStopInput | None = None) -> bool:
        return True

    def is_read_only(self, input: TaskStopInput | None = None) -> bool:
        return True

    def is_destructive(self, input: TaskStopInput | None = None) -> bool:
        return True

    def requires_user_interaction(self) -> bool:
        return False

    def is_open_world(self, input: TaskStopInput | None = None) -> bool:
        return False

    def get_path(self, input: TaskStopInput) -> str | None:
        return None

    async def validate_input(self, input: TaskStopInput, context: Any) -> ValidationResult:
        return ValidationResult(valid=True)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: TaskStopInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        return ToolCallResult(
            data=TaskStopOutput(
                stopped=True,
                reason=args.reason,
            ),
            new_messages=[
                {
                    "type": "text",
                    "text": f"Task stopped: {args.reason}",
                }
            ],
        )

    async def description(self, input: TaskStopInput, options: dict[str, Any]) -> str:
        return f"Stop task: {input.reason}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Stop a running task"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return "Stop Task"

    def to_auto_classifier_input(self, input: TaskStopInput) -> Any:
        return input.reason

    def map_tool_result_to_tool_result_block_param(
        self, content: TaskStopOutput, tool_use_id: str
    ) -> Any:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content.model_dump(),
        }

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

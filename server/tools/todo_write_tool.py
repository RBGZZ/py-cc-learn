from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)

VALID_STATUSES = {"pending", "in_progress", "completed"}
VALID_PRIORITIES = {"high", "medium", "low"}

_todos_state: list[dict[str, Any]] = []


class TodoItem(BaseModel):
    content: str = Field(description="The todo item content")
    id: str = Field(description="Unique identifier for the todo item")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="Status of the todo item"
    )
    priority: Literal["high", "medium", "low"] = Field(
        default="medium", description="Priority of the todo item"
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v


class TodoWriteInput(BaseModel):
    todos: list[TodoItem] = Field(description="The updated todo list")


class TodoWriteOutput(BaseModel):
    old_todos: list[dict[str, Any]] = Field(default_factory=list)
    new_todos: list[dict[str, Any]] = Field(default_factory=list)


class TodoWriteTool(Tool[TodoWriteInput, TodoWriteOutput, Any]):
    @property
    def name(self) -> str:
        return "TodoWrite"

    @property
    def input_schema(self) -> type[TodoWriteInput]:
        return TodoWriteInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return None

    @property
    def search_hint(self) -> str | None:
        return "manage structured task lists"

    def is_concurrency_safe(self, input: TodoWriteInput | None = None) -> bool:
        return False

    def is_read_only(self, input: TodoWriteInput | None = None) -> bool:
        return False

    def is_destructive(self, input: TodoWriteInput | None = None) -> bool:
        return False

    def requires_user_interaction(self) -> bool:
        return False

    async def validate_input(self, input: TodoWriteInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.todos:
            errors.append("todos is required and must not be empty")
        for i, todo in enumerate(input.todos):
            if todo.status not in VALID_STATUSES:
                errors.append(f"todo[{i}].status must be one of {VALID_STATUSES}")
            if todo.priority not in VALID_PRIORITIES:
                errors.append(f"todo[{i}].priority must be one of {VALID_PRIORITIES}")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(
        self, input: dict[str, Any], context: Any = None
    ) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self,
        args: TodoWriteInput,
        context: Any,
        can_use_tool: Any = None,
        parent_message: Any = None,
        on_progress: Any = None,
    ) -> ToolCallResult:
        global _todos_state
        old_todos = [dict(t) for t in _todos_state]
        new_todos = [item.model_dump() for item in args.todos]
        _todos_state = new_todos
        return ToolCallResult(
            data=TodoWriteOutput(
                old_todos=old_todos,
                new_todos=new_todos,
            )
        )

    async def description(self, input: TodoWriteInput, options: dict[str, Any]) -> str:
        return f"Update todo list with {len(input.todos)} items"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Manage structured task lists"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: TodoWriteInput) -> Any:
        return ""

    def map_tool_result_to_tool_result_block_param(
        self, content: TodoWriteOutput, tool_use_id: str
    ) -> Any:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content.model_dump()}

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

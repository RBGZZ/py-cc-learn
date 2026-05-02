from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    content: Any = None
    error: str | None = None
    interrupted: bool = False
    background_task_id: str | None = None
    structured_content: Any | None = None


class ToolProgressData(BaseModel):
    elapsed_time_seconds: float = 0.0


class ToolUseContext(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)
    abort_controller: Any = None
    read_file_state: Any = None
    messages: list[Any] = Field(default_factory=list)
    tool_use_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    user_modified: bool = False
    require_can_use_tool: bool = False
    preserve_tool_use_results: bool = False

    class Config:
        arbitrary_types_allowed = True


class ToolInputJSONSchema(BaseModel):
    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    valid: bool = True
    errors: list[str] = Field(default_factory=list)

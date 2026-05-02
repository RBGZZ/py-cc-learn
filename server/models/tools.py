from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    content: Any = None
    error: Optional[str] = None
    interrupted: bool = False
    background_task_id: Optional[str] = None
    structured_content: Optional[Any] = None


class ToolProgressData(BaseModel):
    elapsed_time_seconds: float = 0.0


class ToolUseContext(BaseModel):
    options: Dict[str, Any] = Field(default_factory=dict)
    abort_controller: Any = None
    read_file_state: Any = None
    messages: List[Any] = Field(default_factory=list)
    tool_use_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_type: Optional[str] = None
    user_modified: bool = False
    require_can_use_tool: bool = False
    preserve_tool_use_results: bool = False

    class Config:
        arbitrary_types_allowed = True


class ToolInputJSONSchema(BaseModel):
    type: str = "object"
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    valid: bool = True
    errors: List[str] = Field(default_factory=list)

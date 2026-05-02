from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import UUID4, BaseModel, Field


class TextBlock(BaseModel):
    type: str = "text"
    text: str


class ToolUseBlock(BaseModel):
    type: str = "tool_use"
    id: str
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    type: str = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]] = ""
    is_error: bool = False


class ImageSource(BaseModel):
    type: str = "base64"
    media_type: str
    data: str


class ImageBlock(BaseModel):
    type: str = "image"
    source: ImageSource


class ThinkingBlock(BaseModel):
    type: str = "thinking"
    thinking: str
    signature: str


class RedactedThinkingBlock(BaseModel):
    type: str = "redacted_thinking"
    data: str


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock, ImageBlock, ThinkingBlock, RedactedThinkingBlock, Dict[str, Any]]

ContentBlockParam = Union[TextBlock, ToolUseBlock, ToolResultBlock, ImageBlock, ThinkingBlock, RedactedThinkingBlock, Dict[str, Any]]


class Message(BaseModel):
    role: str
    content: Union[str, List[ContentBlock]]


class UserMessage(Message):
    role: str = "user"


class AssistantMessage(Message):
    role: str = "assistant"


class SystemMessage(BaseModel):
    role: str = "system"
    content: str


class ProgressMessage(BaseModel):
    type: str = "progress"
    tool_use_id: str
    tool_name: str
    elapsed_time_seconds: float
    task_id: Optional[str] = None


class AttachmentMessage(BaseModel):
    type: str = "attachment"
    attachment: Dict[str, Any]


class RequestStartEvent(BaseModel):
    type: str = "request_start"
    request_id: str


class StreamEvent(BaseModel):
    type: str = "stream_event"
    event: Dict[str, Any]


MessageOrigin = str


class ToolUseSummaryMessage(BaseModel):
    type: str = "tool_use_summary"
    summary: str
    preceding_tool_use_ids: List[str] = Field(default_factory=list)


class TombstoneMessage(BaseModel):
    type: str = "tombstone"
    original_uuid: str


class SystemCompactBoundaryMessage(BaseModel):
    type: str = "system"
    subtype: str = "compact_boundary"
    compact_metadata: Dict[str, Any] = Field(default_factory=dict)


class SystemMicrocompactBoundaryMessage(BaseModel):
    type: str = "system"
    subtype: str = "microcompact_boundary"


class SystemAPIErrorMessage(BaseModel):
    type: str = "system"
    subtype: str = "api_error"
    error: str


class SystemInformationalMessage(BaseModel):
    type: str = "system"
    subtype: str = "info"
    message: str


class SystemAgentsKilledMessage(BaseModel):
    type: str = "system"
    subtype: str = "agents_killed"
    count: int


class SystemStopHookSummaryMessage(BaseModel):
    type: str = "system"
    subtype: str = "stop_hook_summary"
    summary: str


class SystemApiMetricsMessage(BaseModel):
    type: str = "system"
    subtype: str = "api_metrics"
    metrics: Dict[str, Any]


class SystemTurnDurationMessage(BaseModel):
    type: str = "system"
    subtype: str = "turn_duration"
    duration_ms: int


class SystemMemorySavedMessage(BaseModel):
    type: str = "system"
    subtype: str = "memory_saved"
    memory: str


class SystemBridgeStatusMessage(BaseModel):
    type: str = "system"
    subtype: str = "bridge_status"
    status: str


class SystemAwaySummaryMessage(BaseModel):
    type: str = "system"
    subtype: str = "away_summary"
    summary: str


class SystemLocalCommandMessage(BaseModel):
    type: str = "system"
    subtype: str = "local_command_output"
    content: str


class SystemPermissionRetryMessage(BaseModel):
    type: str = "system"
    subtype: str = "permission_retry"
    tool_name: str


class SystemScheduledTaskFireMessage(BaseModel):
    type: str = "system"
    subtype: str = "scheduled_task_fire"
    task_id: str
    prompt: str


class StopHookInfo(BaseModel):
    hook_active: bool = False
    last_assistant_message: Optional[str] = None

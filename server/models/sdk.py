from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import UUID4, BaseModel, Field


class ApiKeySource(str, Enum):
    USER = "user"
    PROJECT = "project"
    ORG = "org"
    TEMPORARY = "temporary"
    OAUTH = "oauth"


class SDKAssistantMessageError(str, Enum):
    AUTHENTICATION_FAILED = "authentication_failed"
    BILLING_ERROR = "billing_error"
    RATE_LIMIT = "rate_limit"
    INVALID_REQUEST = "invalid_request"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"
    MAX_OUTPUT_TOKENS = "max_output_tokens"


class PermissionBehavior(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionUpdateDestination(str, Enum):
    USER_SETTINGS = "userSettings"
    PROJECT_SETTINGS = "projectSettings"
    LOCAL_SETTINGS = "localSettings"
    SESSION = "session"
    CLI_ARG = "cliArg"


class ExternalPermissionMode(str, Enum):
    ACCEPT_EDITS = "acceptEdits"
    BYPASS_PERMISSIONS = "bypassPermissions"
    DEFAULT = "default"
    DONT_ASK = "dontAsk"
    PLAN = "plan"


class FastModeState(str, Enum):
    OFF = "off"
    COOLDOWN = "cooldown"
    ON = "on"


class ModelUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    web_search_requests: int = 0
    cost_usd: float = 0.0
    context_window: int = 0
    max_output_tokens: int = 0


class SDKStatus(BaseModel):
    status: Optional[str] = None


class SDKPermissionDenial(BaseModel):
    tool_name: str
    tool_use_id: str
    tool_input: Dict[str, Any] = Field(default_factory=dict)


class SDKResultSuccess(BaseModel):
    type: Literal["result"]
    subtype: Literal["success"]
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    result: str
    stop_reason: Optional[str] = None
    total_cost_usd: float
    usage: Dict[str, Any] = Field(default_factory=dict)
    model_usage: Dict[str, ModelUsage] = Field(default_factory=dict)
    permission_denials: List[SDKPermissionDenial] = Field(default_factory=list)
    structured_output: Optional[Any] = None
    fast_mode_state: Optional[FastModeState] = None
    uuid: UUID4
    session_id: str


class SDKResultError(BaseModel):
    type: Literal["result"]
    subtype: Literal["error_during_execution", "error_max_turns", "error_max_budget_usd", "error_max_structured_output_retries"]
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    stop_reason: Optional[str] = None
    total_cost_usd: float
    usage: Dict[str, Any] = Field(default_factory=dict)
    model_usage: Dict[str, ModelUsage] = Field(default_factory=dict)
    permission_denials: List[SDKPermissionDenial] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    fast_mode_state: Optional[FastModeState] = None
    uuid: UUID4
    session_id: str


class SDKUserMessage(BaseModel):
    type: Literal["user"]
    message: Dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: Optional[str] = None
    is_synthetic: Optional[bool] = None
    tool_use_result: Optional[Any] = None
    priority: Optional[str] = None
    timestamp: Optional[str] = None
    uuid: Optional[UUID4] = None
    session_id: Optional[str] = None


class SDKAssistantMessage(BaseModel):
    type: Literal["assistant"]
    message: Dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: Optional[str] = None
    error: Optional[SDKAssistantMessageError] = None
    uuid: UUID4
    session_id: str


class SDKSystemMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["init"]
    agents: Optional[List[str]] = None
    api_key_source: ApiKeySource
    betas: Optional[List[str]] = None
    claude_code_version: str
    cwd: str
    tools: List[str] = Field(default_factory=list)
    mcp_servers: List[Dict[str, Any]] = Field(default_factory=list)
    model: str
    permission_mode: ExternalPermissionMode
    slash_commands: List[str] = Field(default_factory=list)
    output_style: str = ""
    skills: List[str] = Field(default_factory=list)
    plugins: List[Dict[str, Any]] = Field(default_factory=list)
    fast_mode_state: Optional[FastModeState] = None
    uuid: UUID4
    session_id: str


class SDKPartialAssistantMessage(BaseModel):
    type: Literal["stream_event"]
    event: Dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: Optional[str] = None
    uuid: UUID4
    session_id: str


class SDKCompactBoundaryMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["compact_boundary"]
    compact_metadata: Dict[str, Any] = Field(default_factory=dict)
    uuid: UUID4
    session_id: str


class SDKStatusMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["status"]
    status: Optional[str] = None
    permission_mode: Optional[ExternalPermissionMode] = None
    uuid: UUID4
    session_id: str


class SDKAPIRetryMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["api_retry"]
    attempt: int
    max_retries: int
    retry_delay_ms: int
    error_status: Optional[int] = None
    error: SDKAssistantMessageError
    uuid: UUID4
    session_id: str


class SDKToolProgressMessage(BaseModel):
    type: Literal["tool_progress"]
    tool_use_id: str
    tool_name: str
    parent_tool_use_id: Optional[str] = None
    elapsed_time_seconds: float
    task_id: Optional[str] = None
    uuid: UUID4
    session_id: str


SDKMessage = Union[
    SDKAssistantMessage,
    SDKUserMessage,
    SDKResultSuccess,
    SDKResultError,
    SDKSystemMessage,
    SDKPartialAssistantMessage,
    SDKCompactBoundaryMessage,
    SDKStatusMessage,
    SDKAPIRetryMessage,
    SDKToolProgressMessage,
    Dict[str, Any],
]

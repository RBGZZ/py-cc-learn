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


class SDKPermissionDenial(BaseModel):
    tool_name: str
    tool_use_id: str
    tool_input: Dict[str, Any] = Field(default_factory=dict)


class SDKRateLimitInfo(BaseModel):
    status: Literal["allowed", "allowed_warning", "rejected"]
    resets_at: Optional[int] = None
    rate_limit_type: Optional[
        Literal["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "overage"]
    ] = None
    utilization: Optional[float] = None
    overage_status: Optional[Literal["allowed", "allowed_warning", "rejected"]] = None
    overage_resets_at: Optional[int] = None
    overage_disabled_reason: Optional[str] = None
    is_using_overage: Optional[bool] = None
    surpassed_threshold: Optional[int] = None


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
    subtype: Literal[
        "error_during_execution",
        "error_max_turns",
        "error_max_budget_usd",
        "error_max_structured_output_retries",
    ]
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
    priority: Optional[Literal["now", "next", "later"]] = None
    timestamp: Optional[str] = None
    uuid: Optional[UUID4] = None
    session_id: Optional[str] = None


class SDKUserMessageReplay(BaseModel):
    type: Literal["user"]
    message: Dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: Optional[str] = None
    is_synthetic: Optional[bool] = None
    tool_use_result: Optional[Any] = None
    priority: Optional[Literal["now", "next", "later"]] = None
    timestamp: Optional[str] = None
    uuid: UUID4
    session_id: str
    is_replay: Literal[True] = True


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


class SDKLocalCommandOutputMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["local_command_output"]
    content: str
    uuid: UUID4
    session_id: str


class SDKHookStartedMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["hook_started"]
    hook_id: str
    hook_name: str
    hook_event: str
    uuid: UUID4
    session_id: str


class SDKHookProgressMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["hook_progress"]
    hook_id: str
    hook_name: str
    hook_event: str
    stdout: str
    stderr: str
    output: str
    uuid: UUID4
    session_id: str


class SDKHookResponseMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["hook_response"]
    hook_id: str
    hook_name: str
    hook_event: str
    output: str
    stdout: str
    stderr: str
    exit_code: Optional[int] = None
    outcome: Literal["success", "error", "cancelled"]
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


class SDKAuthStatusMessage(BaseModel):
    type: Literal["auth_status"]
    is_authenticating: bool
    output: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    uuid: UUID4
    session_id: str


class SDKTaskNotificationMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["task_notification"]
    task_id: str
    tool_use_id: Optional[str] = None
    status: Literal["completed", "failed", "stopped"]
    output_file: str
    summary: str
    usage: Optional[Dict[str, Any]] = None
    uuid: UUID4
    session_id: str


class SDKTaskStartedMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["task_started"]
    task_id: str
    tool_use_id: Optional[str] = None
    description: str
    task_type: Optional[str] = None
    workflow_name: Optional[str] = None
    prompt: Optional[str] = None
    uuid: UUID4
    session_id: str


class SDKTaskProgressMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["task_progress"]
    task_id: str
    tool_use_id: Optional[str] = None
    description: str
    usage: Dict[str, Any] = Field(default_factory=dict)
    last_tool_name: Optional[str] = None
    summary: Optional[str] = None
    uuid: UUID4
    session_id: str


class SDKSessionStateChangedMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["session_state_changed"]
    state: Literal["idle", "running", "requires_action"]
    uuid: UUID4
    session_id: str


class SDKFilesPersistedEvent(BaseModel):
    type: Literal["system"]
    subtype: Literal["files_persisted"]
    files: List[Dict[str, Any]] = Field(default_factory=list)
    failed: List[Dict[str, Any]] = Field(default_factory=list)
    processed_at: str
    uuid: UUID4
    session_id: str


class SDKToolUseSummaryMessage(BaseModel):
    type: Literal["tool_use_summary"]
    summary: str
    preceding_tool_use_ids: List[str] = Field(default_factory=list)
    uuid: UUID4
    session_id: str


class SDKRateLimitEvent(BaseModel):
    type: Literal["rate_limit_event"]
    rate_limit_info: SDKRateLimitInfo
    uuid: UUID4
    session_id: str


class SDKElicitationCompleteMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["elicitation_complete"]
    mcp_server_name: str
    elicitation_id: str
    uuid: UUID4
    session_id: str


class SDKPromptSuggestionMessage(BaseModel):
    type: Literal["prompt_suggestion"]
    suggestion: str
    uuid: UUID4
    session_id: str


class SDKSessionInfo(BaseModel):
    session_id: str = Field(alias="sessionId")
    summary: str
    last_modified: int = Field(alias="lastModified")
    file_size: Optional[int] = Field(default=None, alias="fileSize")
    custom_title: Optional[str] = Field(default=None, alias="customTitle")
    first_prompt: Optional[str] = Field(default=None, alias="firstPrompt")
    git_branch: Optional[str] = Field(default=None, alias="gitBranch")
    cwd: Optional[str] = None
    tag: Optional[str] = None
    created_at: Optional[int] = Field(default=None, alias="createdAt")

    class Config:
        populate_by_name = True


SDKMessage = Union[
    SDKAssistantMessage,
    SDKUserMessage,
    SDKUserMessageReplay,
    SDKResultSuccess,
    SDKResultError,
    SDKSystemMessage,
    SDKPartialAssistantMessage,
    SDKCompactBoundaryMessage,
    SDKStatusMessage,
    SDKAPIRetryMessage,
    SDKLocalCommandOutputMessage,
    SDKHookStartedMessage,
    SDKHookProgressMessage,
    SDKHookResponseMessage,
    SDKToolProgressMessage,
    SDKAuthStatusMessage,
    SDKTaskNotificationMessage,
    SDKTaskStartedMessage,
    SDKTaskProgressMessage,
    SDKSessionStateChangedMessage,
    SDKFilesPersistedEvent,
    SDKToolUseSummaryMessage,
    SDKRateLimitEvent,
    SDKElicitationCompleteMessage,
    SDKPromptSuggestionMessage,
    Dict[str, Any],
]

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union

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
    tool_input: dict[str, Any] = Field(default_factory=dict)


class SDKRateLimitInfo(BaseModel):
    status: Literal["allowed", "allowed_warning", "rejected"]
    resets_at: int | None = None
    rate_limit_type: (
        Literal["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "overage"] | None
    ) = None
    utilization: float | None = None
    overage_status: Literal["allowed", "allowed_warning", "rejected"] | None = None
    overage_resets_at: int | None = None
    overage_disabled_reason: str | None = None
    is_using_overage: bool | None = None
    surpassed_threshold: int | None = None


class SDKResultSuccess(BaseModel):
    type: Literal["result"]
    subtype: Literal["success"]
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    result: str
    stop_reason: str | None = None
    total_cost_usd: float
    usage: dict[str, Any] = Field(default_factory=dict)
    model_usage: dict[str, ModelUsage] = Field(default_factory=dict)
    permission_denials: list[SDKPermissionDenial] = Field(default_factory=list)
    structured_output: Any | None = None
    fast_mode_state: FastModeState | None = None
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
    stop_reason: str | None = None
    total_cost_usd: float
    usage: dict[str, Any] = Field(default_factory=dict)
    model_usage: dict[str, ModelUsage] = Field(default_factory=dict)
    permission_denials: list[SDKPermissionDenial] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    fast_mode_state: FastModeState | None = None
    uuid: UUID4
    session_id: str


class SDKUserMessage(BaseModel):
    type: Literal["user"]
    message: dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: str | None = None
    is_synthetic: bool | None = None
    tool_use_result: Any | None = None
    priority: Literal["now", "next", "later"] | None = None
    timestamp: str | None = None
    uuid: UUID4 | None = None
    session_id: str | None = None


class SDKUserMessageReplay(BaseModel):
    type: Literal["user"]
    message: dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: str | None = None
    is_synthetic: bool | None = None
    tool_use_result: Any | None = None
    priority: Literal["now", "next", "later"] | None = None
    timestamp: str | None = None
    uuid: UUID4
    session_id: str
    is_replay: Literal[True] = True


class SDKAssistantMessage(BaseModel):
    type: Literal["assistant"]
    message: dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: str | None = None
    error: SDKAssistantMessageError | None = None
    uuid: UUID4
    session_id: str


class SDKSystemMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["init"]
    agents: list[str] | None = None
    api_key_source: ApiKeySource
    betas: list[str] | None = None
    claude_code_version: str
    cwd: str
    tools: list[str] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    model: str
    permission_mode: ExternalPermissionMode
    slash_commands: list[str] = Field(default_factory=list)
    output_style: str = ""
    skills: list[str] = Field(default_factory=list)
    plugins: list[dict[str, Any]] = Field(default_factory=list)
    fast_mode_state: FastModeState | None = None
    uuid: UUID4
    session_id: str


class SDKPartialAssistantMessage(BaseModel):
    type: Literal["stream_event"]
    event: dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: str | None = None
    uuid: UUID4
    session_id: str


class SDKCompactBoundaryMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["compact_boundary"]
    compact_metadata: dict[str, Any] = Field(default_factory=dict)
    uuid: UUID4
    session_id: str


class SDKStatusMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["status"]
    status: str | None = None
    permission_mode: ExternalPermissionMode | None = None
    uuid: UUID4
    session_id: str


class SDKAPIRetryMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["api_retry"]
    attempt: int
    max_retries: int
    retry_delay_ms: int
    error_status: int | None = None
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
    exit_code: int | None = None
    outcome: Literal["success", "error", "cancelled"]
    uuid: UUID4
    session_id: str


class SDKToolProgressMessage(BaseModel):
    type: Literal["tool_progress"]
    tool_use_id: str
    tool_name: str
    parent_tool_use_id: str | None = None
    elapsed_time_seconds: float
    task_id: str | None = None
    uuid: UUID4
    session_id: str


class SDKAuthStatusMessage(BaseModel):
    type: Literal["auth_status"]
    is_authenticating: bool
    output: list[str] = Field(default_factory=list)
    error: str | None = None
    uuid: UUID4
    session_id: str


class SDKTaskNotificationMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["task_notification"]
    task_id: str
    tool_use_id: str | None = None
    status: Literal["completed", "failed", "stopped"]
    output_file: str
    summary: str
    usage: dict[str, Any] | None = None
    uuid: UUID4
    session_id: str


class SDKTaskStartedMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["task_started"]
    task_id: str
    tool_use_id: str | None = None
    description: str
    task_type: str | None = None
    workflow_name: str | None = None
    prompt: str | None = None
    uuid: UUID4
    session_id: str


class SDKTaskProgressMessage(BaseModel):
    type: Literal["system"]
    subtype: Literal["task_progress"]
    task_id: str
    tool_use_id: str | None = None
    description: str
    usage: dict[str, Any] = Field(default_factory=dict)
    last_tool_name: str | None = None
    summary: str | None = None
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
    files: list[dict[str, Any]] = Field(default_factory=list)
    failed: list[dict[str, Any]] = Field(default_factory=list)
    processed_at: str
    uuid: UUID4
    session_id: str


class SDKToolUseSummaryMessage(BaseModel):
    type: Literal["tool_use_summary"]
    summary: str
    preceding_tool_use_ids: list[str] = Field(default_factory=list)
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
    file_size: int | None = Field(default=None, alias="fileSize")
    custom_title: str | None = Field(default=None, alias="customTitle")
    first_prompt: str | None = Field(default=None, alias="firstPrompt")
    git_branch: str | None = Field(default=None, alias="gitBranch")
    cwd: str | None = None
    tag: str | None = None
    created_at: int | None = Field(default=None, alias="createdAt")

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
    dict[str, Any],
]

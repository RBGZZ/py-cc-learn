from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

EXTERNAL_PERMISSION_MODES = [
    "acceptEdits",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
]

INTERNAL_PERMISSION_MODES = [
    *EXTERNAL_PERMISSION_MODES,
    "auto",
    "bubble",
]


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    BYPASS_PERMISSIONS = "bypassPermissions"
    DONT_ASK = "dontAsk"
    PLAN = "plan"
    AUTO = "auto"
    BUBBLE = "bubble"


class ExternalPermissionMode(str, Enum):
    ACCEPT_EDITS = "acceptEdits"
    BYPASS_PERMISSIONS = "bypassPermissions"
    DEFAULT = "default"
    DONT_ASK = "dontAsk"
    PLAN = "plan"


class PermissionBehavior(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionRuleSource(str, Enum):
    USER_SETTINGS = "userSettings"
    PROJECT_SETTINGS = "projectSettings"
    LOCAL_SETTINGS = "localSettings"
    FLAG_SETTINGS = "flagSettings"
    POLICY_SETTINGS = "policySettings"
    CLI_ARG = "cliArg"
    COMMAND = "command"
    SESSION = "session"


class PermissionRuleValue(BaseModel):
    tool_name: str
    rule_content: Optional[str] = None


class PermissionRule(BaseModel):
    source: PermissionRuleSource
    rule_behavior: PermissionBehavior
    rule_value: PermissionRuleValue


class PermissionUpdateDestination(str, Enum):
    USER_SETTINGS = "userSettings"
    PROJECT_SETTINGS = "projectSettings"
    LOCAL_SETTINGS = "localSettings"
    SESSION = "session"
    CLI_ARG = "cliArg"


class PermissionUpdateAddRules(BaseModel):
    type: Literal["addRules"]
    destination: PermissionUpdateDestination
    rules: List[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateReplaceRules(BaseModel):
    type: Literal["replaceRules"]
    destination: PermissionUpdateDestination
    rules: List[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateRemoveRules(BaseModel):
    type: Literal["removeRules"]
    destination: PermissionUpdateDestination
    rules: List[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateSetMode(BaseModel):
    type: Literal["setMode"]
    destination: PermissionUpdateDestination
    mode: ExternalPermissionMode


class PermissionUpdateAddDirectories(BaseModel):
    type: Literal["addDirectories"]
    destination: PermissionUpdateDestination
    directories: List[str]


class PermissionUpdateRemoveDirectories(BaseModel):
    type: Literal["removeDirectories"]
    destination: PermissionUpdateDestination
    directories: List[str]


PermissionUpdate = Union[
    PermissionUpdateAddRules,
    PermissionUpdateReplaceRules,
    PermissionUpdateRemoveRules,
    PermissionUpdateSetMode,
    PermissionUpdateAddDirectories,
    PermissionUpdateRemoveDirectories,
]


class AdditionalWorkingDirectory(BaseModel):
    path: str
    source: PermissionRuleSource


class PermissionDecisionReasonRule(BaseModel):
    type: Literal["rule"]
    rule: PermissionRule


class PermissionDecisionReasonMode(BaseModel):
    type: Literal["mode"]
    mode: PermissionMode


class PermissionDecisionReasonOther(BaseModel):
    type: Literal["other"]
    reason: str


PermissionDecisionReason = Union[
    PermissionDecisionReasonRule,
    PermissionDecisionReasonMode,
    PermissionDecisionReasonOther,
    Dict[str, Any],
]


class PermissionAllowDecision(BaseModel):
    behavior: Literal["allow"]
    updated_input: Optional[Dict[str, Any]] = None
    user_modified: Optional[bool] = None
    decision_reason: Optional[PermissionDecisionReason] = None
    tool_use_id: Optional[str] = None
    accept_feedback: Optional[str] = None
    content_blocks: Optional[List[Dict[str, Any]]] = None


class PermissionAskDecision(BaseModel):
    behavior: Literal["ask"]
    message: str
    updated_input: Optional[Dict[str, Any]] = None
    decision_reason: Optional[PermissionDecisionReason] = None
    suggestions: Optional[List[PermissionUpdate]] = None
    blocked_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_bash_security_check_for_misparsing: Optional[bool] = None
    pending_classifier_check: Optional[Dict[str, Any]] = None
    content_blocks: Optional[List[Dict[str, Any]]] = None


class PermissionDenyDecision(BaseModel):
    behavior: Literal["deny"]
    message: str
    decision_reason: PermissionDecisionReason
    tool_use_id: Optional[str] = None


PermissionDecision = Union[PermissionAllowDecision, PermissionAskDecision, PermissionDenyDecision]


class PermissionPassthrough(BaseModel):
    behavior: Literal["passthrough"]
    message: str
    decision_reason: Optional[PermissionDecisionReason] = None
    suggestions: Optional[List[PermissionUpdate]] = None
    blocked_path: Optional[str] = None
    pending_classifier_check: Optional[Dict[str, Any]] = None


PermissionResult = Union[PermissionDecision, PermissionPassthrough]


class ToolPermissionRulesBySource(BaseModel):
    userSettings: Optional[List[str]] = None
    projectSettings: Optional[List[str]] = None
    localSettings: Optional[List[str]] = None
    flagSettings: Optional[List[str]] = None
    policySettings: Optional[List[str]] = None
    cliArg: Optional[List[str]] = None
    command: Optional[List[str]] = None
    session: Optional[List[str]] = None


class ToolPermissionContext(BaseModel):
    mode: PermissionMode
    additional_working_directories: Dict[str, AdditionalWorkingDirectory] = Field(default_factory=dict)
    always_allow_rules: ToolPermissionRulesBySource = Field(default_factory=ToolPermissionRulesBySource)
    always_deny_rules: ToolPermissionRulesBySource = Field(default_factory=ToolPermissionRulesBySource)
    always_ask_rules: ToolPermissionRulesBySource = Field(default_factory=ToolPermissionRulesBySource)
    is_bypass_permissions_mode_available: bool = False
    stripped_dangerous_rules: Optional[ToolPermissionRulesBySource] = None
    should_avoid_permission_prompts: Optional[bool] = None
    await_automated_checks_before_dialog: Optional[bool] = None
    pre_plan_mode: Optional[PermissionMode] = None

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union

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
    rule_content: str | None = None


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
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateReplaceRules(BaseModel):
    type: Literal["replaceRules"]
    destination: PermissionUpdateDestination
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateRemoveRules(BaseModel):
    type: Literal["removeRules"]
    destination: PermissionUpdateDestination
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateSetMode(BaseModel):
    type: Literal["setMode"]
    destination: PermissionUpdateDestination
    mode: ExternalPermissionMode


class PermissionUpdateAddDirectories(BaseModel):
    type: Literal["addDirectories"]
    destination: PermissionUpdateDestination
    directories: list[str]


class PermissionUpdateRemoveDirectories(BaseModel):
    type: Literal["removeDirectories"]
    destination: PermissionUpdateDestination
    directories: list[str]


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
    type: Literal["rule"] = "rule"
    rule: PermissionRule


class PermissionDecisionReasonMode(BaseModel):
    type: Literal["mode"] = "mode"
    mode: PermissionMode


class PermissionDecisionReasonSubcommandResults(BaseModel):
    type: Literal["subcommandResults"] = "subcommandResults"
    reasons: dict[str, "PermissionResult"] = Field(default_factory=dict)


class PermissionDecisionReasonPermissionPromptTool(BaseModel):
    type: Literal["permissionPromptTool"] = "permissionPromptTool"
    permission_prompt_tool_name: str
    tool_result: Any = None


class PermissionDecisionReasonHook(BaseModel):
    type: Literal["hook"] = "hook"
    hook_name: str
    hook_source: str | None = None
    reason: str | None = None


class PermissionDecisionReasonAsyncAgent(BaseModel):
    type: Literal["asyncAgent"] = "asyncAgent"
    reason: str


class PermissionDecisionReasonSandboxOverride(BaseModel):
    type: Literal["sandboxOverride"] = "sandboxOverride"
    reason: Literal["excludedCommand", "dangerouslyDisableSandbox"]


class PermissionDecisionReasonClassifier(BaseModel):
    type: Literal["classifier"] = "classifier"
    classifier: str
    reason: str


class PermissionDecisionReasonWorkingDir(BaseModel):
    type: Literal["workingDir"] = "workingDir"
    reason: str


class PermissionDecisionReasonSafetyCheck(BaseModel):
    type: Literal["safetyCheck"] = "safetyCheck"
    reason: str
    classifier_approvable: bool = False


class PermissionDecisionReasonOther(BaseModel):
    type: Literal["other"] = "other"
    reason: str


PermissionDecisionReason = Union[
    PermissionDecisionReasonRule,
    PermissionDecisionReasonMode,
    PermissionDecisionReasonSubcommandResults,
    PermissionDecisionReasonPermissionPromptTool,
    PermissionDecisionReasonHook,
    PermissionDecisionReasonAsyncAgent,
    PermissionDecisionReasonSandboxOverride,
    PermissionDecisionReasonClassifier,
    PermissionDecisionReasonWorkingDir,
    PermissionDecisionReasonSafetyCheck,
    PermissionDecisionReasonOther,
]


class PermissionAllowDecision(BaseModel):
    behavior: Literal["allow"]
    updated_input: dict[str, Any] | None = None
    user_modified: bool | None = None
    decision_reason: PermissionDecisionReason | None = None
    tool_use_id: str | None = None
    accept_feedback: str | None = None
    content_blocks: list[dict[str, Any]] | None = None


class PermissionAskDecision(BaseModel):
    behavior: Literal["ask"]
    message: str
    updated_input: dict[str, Any] | None = None
    decision_reason: PermissionDecisionReason | None = None
    suggestions: list[PermissionUpdate] | None = None
    blocked_path: str | None = None
    metadata: dict[str, Any] | None = None
    is_bash_security_check_for_misparsing: bool | None = None
    pending_classifier_check: dict[str, Any] | None = None
    content_blocks: list[dict[str, Any]] | None = None


class PermissionDenyDecision(BaseModel):
    behavior: Literal["deny"]
    message: str
    decision_reason: PermissionDecisionReason
    tool_use_id: str | None = None


PermissionDecision = Union[PermissionAllowDecision, PermissionAskDecision, PermissionDenyDecision]


class PermissionPassthrough(BaseModel):
    behavior: Literal["passthrough"]
    message: str
    decision_reason: PermissionDecisionReason | None = None
    suggestions: list[PermissionUpdate] | None = None
    blocked_path: str | None = None
    pending_classifier_check: dict[str, Any] | None = None


PermissionResult = Union[PermissionDecision, PermissionPassthrough]


class ToolPermissionRulesBySource(BaseModel):
    userSettings: list[str] | None = None
    projectSettings: list[str] | None = None
    localSettings: list[str] | None = None
    flagSettings: list[str] | None = None
    policySettings: list[str] | None = None
    cliArg: list[str] | None = None
    command: list[str] | None = None
    session: list[str] | None = None


class PendingClassifierCheck(BaseModel):
    command: str
    cwd: str
    descriptions: list[str] = Field(default_factory=list)


class ToolPermissionContext(BaseModel):
    mode: PermissionMode
    additional_working_directories: dict[str, AdditionalWorkingDirectory] = Field(
        default_factory=dict
    )
    always_allow_rules: ToolPermissionRulesBySource = Field(
        default_factory=ToolPermissionRulesBySource
    )
    always_deny_rules: ToolPermissionRulesBySource = Field(
        default_factory=ToolPermissionRulesBySource
    )
    always_ask_rules: ToolPermissionRulesBySource = Field(
        default_factory=ToolPermissionRulesBySource
    )
    is_bypass_permissions_mode_available: bool = False
    stripped_dangerous_rules: ToolPermissionRulesBySource | None = None
    should_avoid_permission_prompts: bool | None = None
    await_automated_checks_before_dialog: bool | None = None
    pre_plan_mode: PermissionMode | None = None


PROTECTED_NAMESPACES = [
    ".git",
    ".claude",
    ".vscode",
    ".cursor",
    ".windsurf",
    ".trae",
]

SENSITIVE_SHELL_FILES = [
    ".bashrc",
    ".bash_profile",
    ".profile",
    ".zshrc",
    ".config/fish/config.fish",
    "shell.nix",
]

PERMISSION_RULE_SOURCES: list[PermissionRuleSource] = [
    PermissionRuleSource.USER_SETTINGS,
    PermissionRuleSource.PROJECT_SETTINGS,
    PermissionRuleSource.LOCAL_SETTINGS,
    PermissionRuleSource.FLAG_SETTINGS,
    PermissionRuleSource.POLICY_SETTINGS,
    PermissionRuleSource.CLI_ARG,
    PermissionRuleSource.COMMAND,
    PermissionRuleSource.SESSION,
]

DENIAL_LIMITS = {
    "max_consecutive": 3,
    "max_total": 20,
}

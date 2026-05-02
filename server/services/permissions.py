from __future__ import annotations

from typing import Any

from server.models.permissions import (
    PERMISSION_RULE_SOURCES,
    PROTECTED_NAMESPACES,
    SENSITIVE_SHELL_FILES,
    PermissionAllowDecision,
    PermissionAskDecision,
    PermissionBehavior,
    PermissionDecision,
    PermissionDecisionReasonAsyncAgent,
    PermissionDecisionReasonMode,
    PermissionDecisionReasonRule,
    PermissionDecisionReasonSafetyCheck,
    PermissionDenyDecision,
    PermissionMode,
    PermissionPassthrough,
    PermissionResult,
    PermissionRule,
    PermissionRuleSource,
    PermissionRuleValue,
    PermissionUpdate,
    PermissionUpdateAddDirectories,
    PermissionUpdateAddRules,
    PermissionUpdateDestination,
    PermissionUpdateRemoveDirectories,
    PermissionUpdateRemoveRules,
    PermissionUpdateReplaceRules,
    PermissionUpdateSetMode,
    ToolPermissionContext,
    ToolPermissionRulesBySource,
)

BASH_TOOL_NAME = "Bash"
AGENT_TOOL_NAME = "Agent"
LEGACY_AGENT_TOOL_NAME = "Task"
REPL_TOOL_NAME = "REPL"
POWERSHELL_TOOL_NAME = "PowerShell"
TASK_STOP_TOOL_NAME = "TaskStop"
TASK_OUTPUT_TOOL_NAME = "TaskOutput"
BRIEF_TOOL_NAME = "Brief"

LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    LEGACY_AGENT_TOOL_NAME: AGENT_TOOL_NAME,
    "KillShell": TASK_STOP_TOOL_NAME,
    "AgentOutputTool": TASK_OUTPUT_TOOL_NAME,
    "BashOutputTool": TASK_OUTPUT_TOOL_NAME,
    BRIEF_TOOL_NAME: BRIEF_TOOL_NAME,
}


def normalize_legacy_tool_name(tool_name: str) -> str:
    return LEGACY_TOOL_NAME_ALIASES.get(tool_name, tool_name)


def get_legacy_tool_names(tool_name: str) -> list[str]:
    return [k for k, v in LEGACY_TOOL_NAME_ALIASES.items() if v == tool_name]


def escape_rule_content(content: str) -> str:
    content = content.replace("\\", "\\\\")
    content = content.replace("(", "\\(")
    content = content.replace(")", "\\)")
    return content


def unescape_rule_content(content: str) -> str:
    content = content.replace("\\)", ")")
    content = content.replace("\\(", "(")
    content = content.replace("\\\\", "\\")
    return content


def permission_rule_value_from_string(rule_string: str) -> PermissionRuleValue:
    raw = rule_string.strip()
    if raw.endswith("()"):
        return PermissionRuleValue(
            tool_name=raw[:-2],
            rule_content="",
        )
    paren_idx = -1
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "(":
            paren_idx = i
            break
        i += 1
    if paren_idx >= 0:
        tool_name = raw[:paren_idx]
        rest = raw[paren_idx:]
        if rest.startswith("(") and rest.endswith(")"):
            inner = rest[1:-1]
            if inner == "*":
                rule_content = "*"
            else:
                rule_content = unescape_rule_content(inner)
            return PermissionRuleValue(
                tool_name=normalize_legacy_tool_name(tool_name),
                rule_content=rule_content or None,
            )
    return PermissionRuleValue(
        tool_name=normalize_legacy_tool_name(raw),
        rule_content=None,
    )


def permission_rule_value_to_string(rule_value: PermissionRuleValue) -> str:
    if rule_value.rule_content:
        escaped = escape_rule_content(rule_value.rule_content)
        return f"{rule_value.tool_name}({escaped})"
    return rule_value.tool_name


def get_tool_name_for_permission_check(tool: Any) -> str:
    name = getattr(tool, "name", "")
    mcp_info = getattr(tool, "mcp_info", None)
    if mcp_info and hasattr(mcp_info, "server_name") and hasattr(mcp_info, "tool_name"):
        sn = mcp_info.server_name
        tn = mcp_info.tool_name
        if sn and tn:
            return f"mcp__{sn}__{tn}"
    return name


def _mcp_info_from_string(s: str) -> dict[str, str] | None:
    if s.startswith("mcp__"):
        parts = s.split("__", 2)
        if len(parts) >= 3:
            return {"server_name": parts[1], "tool_name": parts[2]}
        elif len(parts) == 2:
            return {"server_name": parts[1], "tool_name": ""}
    return None


def _get_rules_from_source(
    context: ToolPermissionContext,
    rules_by_source: ToolPermissionRulesBySource,
    behavior: PermissionBehavior,
) -> list[PermissionRule]:
    result: list[PermissionRule] = []
    for source in PERMISSION_RULE_SOURCES:
        source_key = source.value
        rule_strings = getattr(rules_by_source, source_key, None) or []
        for rs in rule_strings:
            result.append(
                PermissionRule(
                    source=source,
                    rule_behavior=behavior,
                    rule_value=permission_rule_value_from_string(rs),
                )
            )
    return result


def get_allow_rules(context: ToolPermissionContext) -> list[PermissionRule]:
    return _get_rules_from_source(context, context.always_allow_rules, PermissionBehavior.ALLOW)


def get_deny_rules(context: ToolPermissionContext) -> list[PermissionRule]:
    return _get_rules_from_source(context, context.always_deny_rules, PermissionBehavior.DENY)


def get_ask_rules(context: ToolPermissionContext) -> list[PermissionRule]:
    return _get_rules_from_source(context, context.always_ask_rules, PermissionBehavior.ASK)


def tool_matches_rule(tool: Any, rule: PermissionRule) -> bool:
    if rule.rule_value.rule_content is not None:
        return False

    name_for_match = get_tool_name_for_permission_check(tool)

    if rule.rule_value.tool_name == name_for_match:
        return True

    rule_info = _mcp_info_from_string(rule.rule_value.tool_name)
    tool_info = _mcp_info_from_string(name_for_match)

    return (
        rule_info is not None
        and tool_info is not None
        and (rule_info["tool_name"] == "" or rule_info["tool_name"] == "*")
        and rule_info["server_name"] == tool_info["server_name"]
    )


def tool_always_allowed_rule(context: ToolPermissionContext, tool: Any) -> PermissionRule | None:
    for rule in get_allow_rules(context):
        if tool_matches_rule(tool, rule):
            return rule
    return None


def get_deny_rule_for_tool(context: ToolPermissionContext, tool: Any) -> PermissionRule | None:
    for rule in get_deny_rules(context):
        if tool_matches_rule(tool, rule):
            return rule
    return None


def get_ask_rule_for_tool(context: ToolPermissionContext, tool: Any) -> PermissionRule | None:
    for rule in get_ask_rules(context):
        if tool_matches_rule(tool, rule):
            return rule
    return None


def get_deny_rule_for_agent(
    context: ToolPermissionContext, agent_tool_name: str, agent_type: str
) -> PermissionRule | None:
    for rule in get_deny_rules(context):
        if (
            rule.rule_value.tool_name == agent_tool_name
            and rule.rule_value.rule_content == agent_type
        ):
            return rule
    return None


def filter_denied_agents(
    agents: list[Any],
    context: ToolPermissionContext,
    agent_tool_name: str,
) -> list[Any]:
    denied_agent_types: set[str] = set()
    for rule in get_deny_rules(context):
        if (
            rule.rule_value.tool_name == agent_tool_name
            and rule.rule_value.rule_content is not None
        ):
            denied_agent_types.add(rule.rule_value.rule_content)
    return [a for a in agents if getattr(a, "agentType", None) not in denied_agent_types]


def get_rule_by_contents_for_tool(
    context: ToolPermissionContext, tool: Any, behavior: PermissionBehavior
) -> dict[str, PermissionRule]:
    return get_rule_by_contents_for_tool_name(
        context, get_tool_name_for_permission_check(tool), behavior
    )


def get_rule_by_contents_for_tool_name(
    context: ToolPermissionContext, tool_name: str, behavior: PermissionBehavior
) -> dict[str, PermissionRule]:
    rule_by_contents: dict[str, PermissionRule] = {}
    if behavior == PermissionBehavior.ALLOW:
        rules = get_allow_rules(context)
    elif behavior == PermissionBehavior.DENY:
        rules = get_deny_rules(context)
    else:
        rules = get_ask_rules(context)

    for rule in rules:
        if (
            rule.rule_value.tool_name == tool_name
            and rule.rule_value.rule_content is not None
            and rule.rule_behavior == behavior
        ):
            rule_by_contents[rule.rule_value.rule_content] = rule
    return rule_by_contents


def create_permission_request_message(
    tool_name: str,
    decision_reason: Any = None,
) -> str:
    if decision_reason is not None:
        reason_type = getattr(decision_reason, "type", None)

        if reason_type == "classifier":
            return (
                f"Classifier '{decision_reason.classifier}' requires approval "
                f"for this {tool_name} command: {decision_reason.reason}"
            )

        if reason_type == "hook":
            if decision_reason.reason:
                return (
                    f"Hook '{decision_reason.hook_name}' blocked this action: "
                    f"{decision_reason.reason}"
                )
            return (
                f"Hook '{decision_reason.hook_name}' requires approval for this {tool_name} command"
            )

        if reason_type == "rule":
            rule_str = permission_rule_value_to_string(decision_reason.rule.rule_value)
            source_str = decision_reason.rule.source.value
            return (
                f"Permission rule '{rule_str}' from {source_str} requires "
                f"approval for this {tool_name} command"
            )

        if reason_type == "subcommandResults":
            needs_approval: list[str] = []
            for cmd, result in decision_reason.reasons.items():
                behavior = getattr(result, "behavior", None)
                if behavior in ("ask", "passthrough"):
                    needs_approval.append(cmd)
            if needs_approval:
                n = len(needs_approval)
                verb = "requires" if n == 1 else "require"
                return (
                    f"This {tool_name} command contains multiple operations. "
                    f"The following {n} part{'s' if n > 1 else ''} {verb} "
                    f"approval: {', '.join(needs_approval)}"
                )
            return f"This {tool_name} command contains multiple operations that require approval"

        if reason_type == "permissionPromptTool":
            return (
                f"Tool '{decision_reason.permission_prompt_tool_name}' requires "
                f"approval for this {tool_name} command"
            )

        if reason_type == "sandboxOverride":
            return "Run outside of the sandbox"

        if reason_type in ("workingDir", "safetyCheck", "other"):
            return decision_reason.reason

        if reason_type == "mode":
            return (
                f"Current permission mode ({decision_reason.mode.value}) "
                f"requires approval for this {tool_name} command"
            )

        if reason_type == "asyncAgent":
            return decision_reason.reason

    return f"Claude requested permissions to use {tool_name}, but you haven't granted it yet."


def _is_in_protected_namespace(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    parts = normalized.strip("/").split("/")
    for ns in PROTECTED_NAMESPACES:
        if ns in parts:
            return True
    return False


def _is_sensitive_shell_file(path: str) -> bool:
    normalized = path.replace("\\", "/").lower().rstrip("/")
    for sensitive in SENSITIVE_SHELL_FILES:
        if normalized == sensitive or normalized.endswith("/" + sensitive):
            return True
    return False


def check_path_safety(file_path: str) -> PermissionResult | None:
    if _is_in_protected_namespace(file_path):
        return PermissionAskDecision(
            behavior="ask",
            message=(
                f"Access to '{file_path}' is in a protected namespace "
                f"({', '.join(PROTECTED_NAMESPACES)}). This may contain sensitive "
                f"configuration that should not be modified without review."
            ),
            decision_reason=PermissionDecisionReasonSafetyCheck(
                type="safetyCheck",
                reason=f"Path '{file_path}' is in a protected namespace",
                classifier_approvable=True,
            ),
        )
    if _is_sensitive_shell_file(file_path):
        return PermissionAskDecision(
            behavior="ask",
            message=(
                f"Access to '{file_path}' is a sensitive shell configuration file. "
                f"Modifying this could affect all shell sessions."
            ),
            decision_reason=PermissionDecisionReasonSafetyCheck(
                type="safetyCheck",
                reason=f"Path '{file_path}' is a sensitive shell configuration file",
                classifier_approvable=True,
            ),
        )
    return None


def _get_updated_input_or_fallback(
    permission_result: PermissionResult,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if hasattr(permission_result, "updated_input") and permission_result.updated_input is not None:
        return permission_result.updated_input
    return fallback


async def has_permissions_to_use_tool_inner(
    tool: Any,
    input_data: dict[str, Any],
    context: Any,
) -> PermissionDecision:
    app_state = context.getAppState()
    perm_ctx = app_state.toolPermissionContext

    deny_rule = get_deny_rule_for_tool(perm_ctx, tool)
    if deny_rule:
        return PermissionDenyDecision(
            behavior="deny",
            message=f"Permission to use {tool.name} has been denied.",
            decision_reason=PermissionDecisionReasonRule(
                type="rule",
                rule=deny_rule,
            ),
        )

    ask_rule = get_ask_rule_for_tool(perm_ctx, tool)
    if ask_rule:
        return PermissionAskDecision(
            behavior="ask",
            message=create_permission_request_message(tool.name),
            decision_reason=PermissionDecisionReasonRule(
                type="rule",
                rule=ask_rule,
            ),
        )

    tool_permission_result: PermissionResult = PermissionPassthrough(
        behavior="passthrough",
        message=create_permission_request_message(tool.name),
    )
    try:
        parsed_input = tool.inputSchema(input_data)
        if hasattr(tool, "checkPermissions"):
            tool_permission_result = await tool.checkPermissions(parsed_input, context)
    except Exception:
        pass

    if hasattr(tool_permission_result, "behavior") and tool_permission_result.behavior == "deny":
        return tool_permission_result

    if (
        hasattr(tool, "requiresUserInteraction")
        and tool.requiresUserInteraction()
        and getattr(tool_permission_result, "behavior", None) == "ask"
    ):
        return tool_permission_result

    if (
        getattr(tool_permission_result, "behavior", None) == "ask"
        and getattr(tool_permission_result, "decision_reason", None) is not None
        and tool_permission_result.decision_reason.type == "rule"
        and getattr(tool_permission_result.decision_reason.rule, "rule_behavior", None)
        == PermissionBehavior.ASK
    ):
        return tool_permission_result

    if (
        getattr(tool_permission_result, "behavior", None) == "ask"
        and getattr(tool_permission_result, "decision_reason", None) is not None
        and tool_permission_result.decision_reason.type == "safetyCheck"
    ):
        return tool_permission_result

    app_state = context.getAppState()
    perm_ctx = app_state.toolPermissionContext

    should_bypass = perm_ctx.mode == PermissionMode.BYPASS_PERMISSIONS or (
        perm_ctx.mode == PermissionMode.PLAN and perm_ctx.is_bypass_permissions_mode_available
    )
    if should_bypass:
        return PermissionAllowDecision(
            behavior="allow",
            updated_input=_get_updated_input_or_fallback(tool_permission_result, input_data),
            decision_reason=PermissionDecisionReasonMode(
                type="mode",
                mode=perm_ctx.mode,
            ),
        )

    always_allowed = tool_always_allowed_rule(perm_ctx, tool)
    if always_allowed:
        return PermissionAllowDecision(
            behavior="allow",
            updated_input=_get_updated_input_or_fallback(tool_permission_result, input_data),
            decision_reason=PermissionDecisionReasonRule(
                type="rule",
                rule=always_allowed,
            ),
        )

    if getattr(tool_permission_result, "behavior", None) == "passthrough":
        result: PermissionDecision = PermissionAskDecision(
            behavior="ask",
            message=create_permission_request_message(
                tool.name,
                getattr(tool_permission_result, "decision_reason", None),
            ),
            decision_reason=getattr(tool_permission_result, "decision_reason", None),
            suggestions=getattr(tool_permission_result, "suggestions", None),
            blocked_path=getattr(tool_permission_result, "blocked_path", None),
            pending_classifier_check=getattr(
                tool_permission_result, "pending_classifier_check", None
            ),
        )
    else:
        result = tool_permission_result

    return result


async def has_permissions_to_use_tool(
    tool: Any,
    input_data: dict[str, Any],
    context: Any,
) -> PermissionDecision:
    result = await has_permissions_to_use_tool_inner(tool, input_data, context)

    if result.behavior == "allow":
        return result

    app_state = context.getAppState()
    perm_ctx = app_state.toolPermissionContext

    if result.behavior == "ask" and perm_ctx.mode == PermissionMode.DONT_ASK:
        return PermissionDenyDecision(
            behavior="deny",
            message=(
                f"The tool {tool.name} cannot be used in Don't Ask mode. "
                f"Switch to Default mode to allow this tool, or add an allow rule."
            ),
            decision_reason=PermissionDecisionReasonMode(type="mode", mode=PermissionMode.DONT_ASK),
        )

    if result.behavior == "ask" and perm_ctx.mode == PermissionMode.BUBBLE:
        return result

    if result.behavior == "ask" and getattr(perm_ctx, "should_avoid_permission_prompts", None):
        return PermissionDenyDecision(
            behavior="deny",
            message=(
                f"The tool {tool.name} requires permission approval, "
                f"but permission prompts are not available in this context."
            ),
            decision_reason=PermissionDecisionReasonAsyncAgent(
                type="asyncAgent",
                reason="Permission prompts are not available in this context",
            ),
        )

    return result


async def check_rule_based_permissions(
    tool: Any,
    input_data: dict[str, Any],
    context: Any,
) -> PermissionAskDecision | PermissionDenyDecision | None:
    app_state = context.getAppState()
    perm_ctx = app_state.toolPermissionContext

    deny_rule = get_deny_rule_for_tool(perm_ctx, tool)
    if deny_rule:
        return PermissionDenyDecision(
            behavior="deny",
            message=f"Permission to use {tool.name} has been denied.",
            decision_reason=PermissionDecisionReasonRule(type="rule", rule=deny_rule),
        )

    ask_rule = get_ask_rule_for_tool(perm_ctx, tool)
    if ask_rule:
        return PermissionAskDecision(
            behavior="ask",
            message=create_permission_request_message(tool.name),
            decision_reason=PermissionDecisionReasonRule(type="rule", rule=ask_rule),
        )

    tool_permission_result: PermissionResult = PermissionPassthrough(
        behavior="passthrough",
        message=create_permission_request_message(tool.name),
    )
    try:
        parsed_input = tool.inputSchema(input_data)
        if hasattr(tool, "checkPermissions"):
            tool_permission_result = await tool.checkPermissions(parsed_input, context)
    except Exception:
        pass

    if getattr(tool_permission_result, "behavior", None) == "deny":
        return tool_permission_result

    if (
        getattr(tool_permission_result, "behavior", None) == "ask"
        and getattr(tool_permission_result, "decision_reason", None) is not None
        and tool_permission_result.decision_reason.type == "rule"
        and getattr(tool_permission_result.decision_reason.rule, "rule_behavior", None)
        == PermissionBehavior.ASK
    ):
        return tool_permission_result

    if (
        getattr(tool_permission_result, "behavior", None) == "ask"
        and getattr(tool_permission_result, "decision_reason", None) is not None
        and tool_permission_result.decision_reason.type == "safetyCheck"
    ):
        return tool_permission_result

    return None


def _convert_rules_to_updates(
    rules: list[PermissionRule],
    update_type: str,
) -> list[PermissionUpdate]:
    grouped: dict[str, list[PermissionRuleValue]] = {}
    for rule in rules:
        key = f"{rule.source.value}:{rule.rule_behavior.value}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(rule.rule_value)

    updates: list[PermissionUpdate] = []
    for key, rule_values in grouped.items():
        source_str, behavior_str = key.split(":")
        source = PermissionRuleSource(source_str)
        behavior = PermissionBehavior(behavior_str)
        if update_type == "addRules":
            updates.append(
                PermissionUpdateAddRules(
                    type="addRules",
                    destination=PermissionUpdateDestination(source_str),
                    rules=rule_values,
                    behavior=behavior,
                )
            )
        elif update_type == "replaceRules":
            updates.append(
                PermissionUpdateReplaceRules(
                    type="replaceRules",
                    destination=PermissionUpdateDestination(source_str),
                    rules=rule_values,
                    behavior=behavior,
                )
            )
    return updates


def apply_permission_update(
    context: ToolPermissionContext,
    update: PermissionUpdate,
) -> ToolPermissionContext:
    if isinstance(update, PermissionUpdateSetMode):
        return context.model_copy(update={"mode": update.mode})

    if isinstance(update, PermissionUpdateAddRules):
        behavior = update.behavior
        dest = update.destination.value
        rule_strings = [permission_rule_value_to_string(rv) for rv in update.rules]
        if behavior == PermissionBehavior.ALLOW:
            new_rules = context.always_allow_rules.model_copy(deep=True)
        elif behavior == PermissionBehavior.DENY:
            new_rules = context.always_deny_rules.model_copy(deep=True)
        else:
            new_rules = context.always_ask_rules.model_copy(deep=True)

        existing = list(getattr(new_rules, dest, None) or [])
        existing.extend(rule_strings)
        setattr(new_rules, dest, existing)

        if behavior == PermissionBehavior.ALLOW:
            return context.model_copy(update={"always_allow_rules": new_rules})
        elif behavior == PermissionBehavior.DENY:
            return context.model_copy(update={"always_deny_rules": new_rules})
        else:
            return context.model_copy(update={"always_ask_rules": new_rules})

    if isinstance(update, PermissionUpdateRemoveRules):
        behavior = update.behavior
        dest = update.destination.value
        remove_set = {permission_rule_value_to_string(rv) for rv in update.rules}
        if behavior == PermissionBehavior.ALLOW:
            new_rules = context.always_allow_rules.model_copy(deep=True)
        elif behavior == PermissionBehavior.DENY:
            new_rules = context.always_deny_rules.model_copy(deep=True)
        else:
            new_rules = context.always_ask_rules.model_copy(deep=True)

        existing = list(getattr(new_rules, dest, None) or [])
        existing = [rs for rs in existing if rs not in remove_set]
        setattr(new_rules, dest, existing if existing else None)

        if behavior == PermissionBehavior.ALLOW:
            return context.model_copy(update={"always_allow_rules": new_rules})
        elif behavior == PermissionBehavior.DENY:
            return context.model_copy(update={"always_deny_rules": new_rules})
        else:
            return context.model_copy(update={"always_ask_rules": new_rules})

    if isinstance(update, PermissionUpdateReplaceRules):
        behavior = update.behavior
        dest = update.destination.value
        rule_strings = [permission_rule_value_to_string(rv) for rv in update.rules]
        if behavior == PermissionBehavior.ALLOW:
            new_rules = context.always_allow_rules.model_copy(deep=True)
        elif behavior == PermissionBehavior.DENY:
            new_rules = context.always_deny_rules.model_copy(deep=True)
        else:
            new_rules = context.always_ask_rules.model_copy(deep=True)

        setattr(new_rules, dest, rule_strings if rule_strings else None)

        if behavior == PermissionBehavior.ALLOW:
            return context.model_copy(update={"always_allow_rules": new_rules})
        elif behavior == PermissionBehavior.DENY:
            return context.model_copy(update={"always_deny_rules": new_rules})
        else:
            return context.model_copy(update={"always_ask_rules": new_rules})

    if isinstance(update, PermissionUpdateAddDirectories):
        new_dirs = dict(context.additional_working_directories)
        from server.models.permissions import AdditionalWorkingDirectory

        target_source = PermissionRuleSource(update.destination.value)
        for d in update.directories:
            new_dirs[d] = AdditionalWorkingDirectory(path=d, source=target_source)
        return context.model_copy(update={"additional_working_directories": new_dirs})

    if isinstance(update, PermissionUpdateRemoveDirectories):
        new_dirs = dict(context.additional_working_directories)
        for d in update.directories:
            new_dirs.pop(d, None)
        return context.model_copy(update={"additional_working_directories": new_dirs})

    return context


def apply_permission_updates(
    context: ToolPermissionContext,
    updates: list[PermissionUpdate],
) -> ToolPermissionContext:
    for update in updates:
        context = apply_permission_update(context, update)
    return context


def apply_permission_rules_to_permission_context(
    tool_permission_context: ToolPermissionContext,
    rules: list[PermissionRule],
) -> ToolPermissionContext:
    updates = _convert_rules_to_updates(rules, "addRules")
    return apply_permission_updates(tool_permission_context, updates)


def sync_permission_rules_from_disk(
    tool_permission_context: ToolPermissionContext,
    rules: list[PermissionRule],
) -> ToolPermissionContext:
    context = tool_permission_context

    disk_sources: list[str] = ["userSettings", "projectSettings", "localSettings"]
    for disk_source in disk_sources:
        for behavior in [PermissionBehavior.ALLOW, PermissionBehavior.DENY, PermissionBehavior.ASK]:
            context = apply_permission_update(
                context,
                PermissionUpdateReplaceRules(
                    type="replaceRules",
                    destination=PermissionUpdateDestination(disk_source),
                    rules=[],
                    behavior=behavior,
                ),
            )

    updates = _convert_rules_to_updates(rules, "replaceRules")
    return apply_permission_updates(context, updates)


async def delete_permission_rule(
    rule: PermissionRule,
    initial_context: ToolPermissionContext,
    set_tool_permission_context: Any,
) -> None:
    if rule.source in (
        PermissionRuleSource.POLICY_SETTINGS,
        PermissionRuleSource.FLAG_SETTINGS,
        PermissionRuleSource.COMMAND,
    ):
        raise ValueError("Cannot delete permission rules from read-only settings")

    updated_context = apply_permission_update(
        initial_context,
        PermissionUpdateRemoveRules(
            type="removeRules",
            rules=[rule.rule_value],
            behavior=rule.rule_behavior,
            destination=PermissionUpdateDestination(rule.source.value),
        ),
    )

    if callable(set_tool_permission_context):
        set_tool_permission_context(updated_context)

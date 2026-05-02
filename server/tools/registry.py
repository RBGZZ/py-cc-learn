from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from server.tools.tool import Tool, Tools, find_tool_by_name, tool_matches_name

_BASH_TOOL_NAME = "Bash"
_FILE_READ_TOOL_NAME = "Read"
_FILE_EDIT_TOOL_NAME = "Edit"
_AGENT_TOOL_NAME = "Agent"
_TASK_STOP_TOOL_NAME = "TaskStop"
_SYNTHETIC_OUTPUT_TOOL_NAME = "SyntheticOutputTool"
_REPL_TOOL_NAME = "REPL"


def _get_deny_rule_for_tool(
    permission_context: Any, tool: Tool
) -> Optional[Dict[str, Any]]:
    """
    Check if a tool is covered by a blanket deny rule.
    Source: getDenyRuleForTool from permissions.ts.

    A tool is blanket-denied if there's a deny rule matching its name with no
    ruleContent. MCP server-prefix rules like 'mcp__server' strip all tools from
    that server.
    """
    always_deny_rules = getattr(permission_context, "always_deny_rules", None)
    if always_deny_rules is None:
        return None
    tool_name = tool.name
    for source_name in [
        "userSettings",
        "projectSettings",
        "localSettings",
        "flagSettings",
        "policySettings",
        "cliArg",
        "command",
        "session",
    ]:
        rules: Optional[List[str]] = getattr(always_deny_rules, source_name, None)
        if rules is None:
            continue
        for rule_str in rules:
            if not isinstance(rule_str, str):
                continue
            parts = rule_str.split("(", 1)
            rule_tool_name = parts[0].strip()
            rule_content = parts[1].rstrip(")") if len(parts) > 1 else ""
            if rule_content:
                continue
            if tool_matches_name(tool, rule_tool_name):
                return {
                    "source": source_name,
                    "rule_value": {"tool_name": rule_tool_name, "rule_content": None},
                }
            mcp_info = tool.mcp_info
            if mcp_info is not None:
                server_name = mcp_info.get("serverName", "")
                if rule_tool_name == f"mcp__{server_name}":
                    return {
                        "source": source_name,
                        "rule_value": {
                            "tool_name": rule_tool_name,
                            "rule_content": None,
                        },
                    }
    return None


def filter_tools_by_deny_rules(
    tools: List[Tool],
    permission_context: Any,
) -> List[Tool]:
    """
    Filters out tools that are blanket-denied by the permission context.
    Source: tools.ts L253-268.
    """
    return [t for t in tools if _get_deny_rule_for_tool(permission_context, t) is None]


def get_tools(
    permission_context: Any,
    all_base_tools: Optional[List[Tool]] = None,
) -> List[Tool]:
    """
    Get built-in tools filtered by permission context and isEnabled.
    Source: tools.ts L271-327.

    Args:
        permission_context: Permission context for filtering.
        all_base_tools: List of all base tools. If None, returns empty list.

    Returns:
        Filtered list of enabled tools.
    """
    if all_base_tools is None:
        return []

    tools = list(all_base_tools)

    allowed_tools = filter_tools_by_deny_rules(tools, permission_context)

    is_enabled = [t.is_enabled() for t in allowed_tools]
    return [allowed_tools[i] for i in range(len(allowed_tools)) if is_enabled[i]]


def assemble_tool_pool(
    permission_context: Any,
    mcp_tools: List[Tool],
    all_base_tools: Optional[List[Tool]] = None,
) -> List[Tool]:
    """
    Assemble the full tool pool for a given permission context and MCP tools.
    Source: tools.ts L345-367.

    This is the single source of truth for combining built-in tools with MCP tools.
    Both REPL.tsx (via useMergedTools hook) and runAgent.ts (for coordinator workers)
    use this function to ensure consistent tool pool assembly.

    The function:
    1. Gets built-in tools via getTools() (respects mode filtering)
    2. Filters MCP tools by deny rules
    3. Sorts each partition by name (localeCompare equivalent) for prompt-cache stability
    4. Deduplicates by tool name (built-in tools take precedence)

    Why partition-sort (not flat sort):
    The server's prompt cache policy places a global cache breakpoint after the last
    prefix-matched built-in tool. A flat sort would interleave MCP tools into built-ins
    and invalidate all downstream cache keys whenever an MCP tool sorts between
    existing built-ins. uniqBy preserves insertion order, so built-ins win on name
    conflict.

    Args:
        permission_context: Permission context for filtering built-in tools.
        mcp_tools: MCP tools list.
        all_base_tools: List of all base tools (from getAllBaseTools).

    Returns:
        Combined, deduplicated array of built-in and MCP tools.
    """
    built_in_tools = get_tools(permission_context, all_base_tools)

    allowed_mcp_tools = filter_tools_by_deny_rules(list(mcp_tools), permission_context)

    sorted_built_in = sorted(list(built_in_tools), key=lambda t: t.name)
    sorted_mcp = sorted(list(allowed_mcp_tools), key=lambda t: t.name)

    combined = sorted_built_in + sorted_mcp

    seen: set = set()
    result: List[Tool] = []
    for tool in combined:
        if tool.name not in seen:
            seen.add(tool.name)
            result.append(tool)

    return result


def get_merged_tools(
    permission_context: Any,
    mcp_tools: List[Tool],
    all_base_tools: Optional[List[Tool]] = None,
) -> List[Tool]:
    """
    Get all tools including both built-in tools and MCP tools.
    Source: tools.ts L383-389.

    This is the preferred function when you need the complete tools list for:
    - Tool search threshold calculations (isToolSearchEnabled)
    - Token counting that includes MCP tools
    - Any context where MCP tools should be considered
    """
    built_in_tools = get_tools(permission_context, all_base_tools)
    return built_in_tools + list(mcp_tools)


def assemble_tool_pool_from_callables(
    permission_context: Any,
    mcp_tools: List[Tool],
    built_in_tools_fn: Callable[[], List[Tool]],
) -> List[Tool]:
    """
    Convenience wrapper that calls built_in_tools_fn at assembly time
    to support lazy-loaded tools. This ensures the function is called
    fresh each time the pool is assembled (mirrors getTools() behavior).
    """
    return assemble_tool_pool(
        permission_context=permission_context,
        mcp_tools=mcp_tools,
        all_base_tools=built_in_tools_fn(),
    )

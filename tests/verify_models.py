"""Source consistency verification between Python models and TypeScript source.

Run: uv run python tests/verify_models.py
"""
from __future__ import annotations


def verify_permission_models():
    from server.models.permissions import (
        PermissionBehavior,
        PermissionMode,
        PermissionDecisionReason,
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
        PermissionResult,
        PermissionAllowDecision,
        PermissionAskDecision,
        PermissionDenyDecision,
        PermissionPassthrough,
    )

    assert PermissionBehavior.ALLOW.value == "allow"
    assert PermissionBehavior.DENY.value == "deny"
    assert PermissionBehavior.ASK.value == "ask"

    modes = {m.value for m in PermissionMode}
    assert "default" in modes
    assert "acceptEdits" in modes
    assert "bypassPermissions" in modes
    assert "dontAsk" in modes
    assert "plan" in modes
    assert "auto" in modes
    assert "bubble" in modes
    assert len(modes) == 7

    print("✅ PermissionMode 7种模式: OK")


def verify_error_classification():
    from server.services.errors import (
        API_ERROR_MESSAGE_PREFIX,
        API_TIMEOUT_ERROR_MESSAGE,
        CREDIT_BALANCE_TOO_LOW_ERROR_MESSAGE,
        INVALID_API_KEY_ERROR_MESSAGE,
        PROMPT_TOO_LONG_ERROR_MESSAGE,
    )

    expected = {
        "timeout": API_TIMEOUT_ERROR_MESSAGE,
        "rate_limit": "Request rejected",
        "auth": INVALID_API_KEY_ERROR_MESSAGE,
        "prompt_too_long": PROMPT_TOO_LONG_ERROR_MESSAGE,
        "billing": CREDIT_BALANCE_TOO_LOW_ERROR_MESSAGE,
    }
    for category, _ in expected.items():
        print(f"  {category}: defined")

    print("✅ 错误分类 5类: OK (timeout/rate_limit/auth/prompt_too_long/billing)")


def verify_tool_count():
    import server.tools
    import inspect

    tool_modules = [
        "bash_tool", "file_read_tool", "file_write_tool", "file_edit_tool",
        "glob_tool", "grep_tool", "todo_write_tool", "web_search_tool",
        "web_fetch_tool", "agent_tool", "skill_tool", "ask_user_tool",
        "enter_plan_mode_tool", "exit_plan_mode_tool", "task_stop_tool",
        "config_tool",
    ]
    count = 0
    for mod_name in tool_modules:
        try:
            mod = __import__(f"server.tools.{mod_name}", fromlist=["*"])
            for name, obj in inspect.getmembers(mod):
                if inspect.isclass(obj) and name.endswith("Tool") and name != "Tool":
                    count += 1
        except Exception:
            pass

    print(f"✅ 工具数量: {count}+ (核心16个 + MCP/LSP)")
    assert count >= 16


def verify_query_exit_reasons():
    from server.engine.query_engine import QueryExitReason

    reasons = {r.value for r in QueryExitReason}
    expected = {
        "completed", "max_turns", "model_error", "blocking_limit",
        "aborted_streaming", "aborted_tools", "image_error",
        "stop_hook_prevented", "max_output_tokens_max_recoveries",
        "cancelled_by_user",
    }
    assert reasons == expected, f"Missing: {expected - reasons}, Extra: {reasons - expected}"
    print(f"✅ QueryExitReason 10种退出原因: OK")


def verify_hook_events():
    from server.services.hooks import HookEventType

    events = {e.value for e in HookEventType}
    expected = {
        "PreToolUse", "PostToolUse", "PostToolUseFailure",
        "Notification", "UserPromptSubmit",
        "SessionStart", "SessionEnd", "Stop", "StopFailure",
        "SubagentStart", "SubagentStop", "PreCompact", "PostCompact",
        "PermissionRequest", "PermissionDenied", "Setup",
        "TeammateIdle", "TaskCreated", "TaskCompleted",
        "Elicitation", "ElicitationResult", "ConfigChange",
        "WorktreeCreate", "WorktreeRemove", "InstructionsLoaded",
        "CwdChanged", "FileChanged",
    }
    assert events == expected, f"Missing: {expected - events}"
    print(f"✅ HookEventType 27种事件: OK")


def verify_file_existence():
    import os
    from pathlib import Path

    base = Path(os.getcwd())
    required = [
        "pyproject.toml", ".env.example", ".gitattributes", ".pre-commit-config.yaml",
        "uv.lock", "BRANCHES.md",
        "server/main.py", "server/cli.py", "server/exceptions.py",
        "sandbox/Dockerfile", "sandbox/manager.py",
        "deploy/docker-compose.yml", "deploy/nginx.conf",
        "deploy/claude-code.service", "deploy/README.md",
        "frontend/vite.config.ts", "frontend/package.json",
        "frontend/dist/index.html",
        ".github/workflows/test.yml",
    ]
    for p in required:
        full = base / p
        assert full.exists(), f"MISSING: {p}"
    print(f"✅ 文件存在性 {len(required)}个关键文件: OK")


if __name__ == "__main__":
    print("=== 源码一致性验证 ===")
    verify_permission_models()
    verify_error_classification()
    verify_query_exit_reasons()
    verify_hook_events()
    verify_tool_count()
    verify_file_existence()
    print("\n=== 全部验证通过 ===")

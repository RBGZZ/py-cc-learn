from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookEventType(str, Enum):
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    NOTIFICATION = "Notification"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    STOP = "Stop"
    STOP_FAILURE = "StopFailure"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    PERMISSION_REQUEST = "PermissionRequest"
    PERMISSION_DENIED = "PermissionDenied"
    SETUP = "Setup"
    TEAMMATE_IDLE = "TeammateIdle"
    TASK_CREATED = "TaskCreated"
    TASK_COMPLETED = "TaskCompleted"
    ELICITATION = "Elicitation"
    ELICITATION_RESULT = "ElicitationResult"
    CONFIG_CHANGE = "ConfigChange"
    WORKTREE_CREATE = "WorktreeCreate"
    WORKTREE_REMOVE = "WorktreeRemove"
    INSTRUCTIONS_LOADED = "InstructionsLoaded"
    CWD_CHANGED = "CwdChanged"
    FILE_CHANGED = "FileChanged"


HOOK_EVENTS: list[HookEventType] = list(HookEventType)


class HookExecutionType(str, Enum):
    COMMAND = "command"
    PROMPT = "prompt"
    HTTP = "http"
    CALLBACK = "callback"


@dataclass
class HookMatcher:
    matcher: str
    hooks: list[HookDefinition] = field(default_factory=list)
    plugin_name: str | None = None


@dataclass
class HookDefinition:
    type: HookExecutionType = HookExecutionType.COMMAND
    command: str = ""
    timeout: float = 60.0
    matcher: str = ""
    event: HookEventType = HookEventType.NOTIFICATION
    internal: bool = False


@dataclass
class HookInput:
    hook_event: HookEventType
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    session_id: str = ""
    cwd: str = ""
    permission_mode: str = ""


@dataclass
class HookResult:
    outcome: str = "success"
    message: str | None = None
    system_message: str | None = None
    blocking_error: str | None = None
    prevent_continuation: bool = False
    stop_reason: str | None = None
    permission_behavior: str | None = None
    permission_decision_reason: str | None = None
    additional_context: str | None = None
    updated_input: dict[str, Any] | None = None
    retry: bool = False


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[HookEventType, list[HookDefinition]] = {
            event: [] for event in HOOK_EVENTS
        }
        self._callbacks: dict[HookEventType, list[HookCallback]] = {
            event: [] for event in HOOK_EVENTS
        }
        self._matchers: list[HookMatcher] = []

    def register(self, hook: HookDefinition) -> None:
        self._hooks.setdefault(hook.event, []).append(hook)

    def register_callback(self, event: HookEventType, cb: HookCallback) -> None:
        self._callbacks.setdefault(event, []).append(cb)

    def register_matcher(self, matcher: HookMatcher) -> None:
        self._matchers.append(matcher)

    def get_hooks(self, event: HookEventType) -> list[HookDefinition]:
        return self._hooks.get(event, [])

    def get_matched_hooks(
        self, event: HookEventType, tool_name: str | None = None
    ) -> list[HookDefinition]:
        hooks = list(self.get_hooks(event))
        if tool_name:
            for matcher_entry in self._matchers:
                if _match_pattern(matcher_entry.matcher, tool_name):
                    hooks.extend(matcher_entry.hooks)
        return hooks

    def get_callbacks(self, event: HookEventType) -> list[HookCallback]:
        return self._callbacks.get(event, [])


HookCallback = Callable[..., Any]


TOOL_HOOK_EXECUTION_TIMEOUT_MS = 10 * 60 * 1000
SESSION_END_HOOK_TIMEOUT_MS_DEFAULT = 1500


def get_session_end_hook_timeout_ms() -> int:
    env_val = os.environ.get("CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS")
    if env_val:
        try:
            parsed = int(env_val)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return SESSION_END_HOOK_TIMEOUT_MS_DEFAULT


def is_hook_event(value: str) -> bool:
    try:
        HookEventType(value)
        return True
    except ValueError:
        return False


def _match_pattern(pattern: str, target: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("*"):
        return target.startswith(pattern[:-1])
    return pattern == target


class HookExecutor:
    def __init__(self, registry: HookRegistry) -> None:
        self.registry = registry

    async def execute_event_hooks(
        self,
        event: HookEventType,
        input_data: HookInput,
        tool_name: str | None = None,
        signal: Any = None,
    ) -> list[HookResult]:
        hooks = self.registry.get_matched_hooks(event, tool_name)
        callbacks = self.registry.get_callbacks(event)
        results: list[HookResult] = []

        for hook in hooks:
            result = await self._execute_single_hook(hook, input_data, signal)
            results.append(result)

        for cb in callbacks:
            try:
                cb_result = await cb(input_data)
                if cb_result:
                    results.append(HookResult(outcome="success", message=str(cb_result)))
            except Exception as exc:
                results.append(
                    HookResult(
                        outcome="non_blocking_error",
                        message=str(exc),
                    )
                )

        return results

    async def _execute_single_hook(
        self,
        hook: HookDefinition,
        input_data: HookInput,
        signal: Any = None,
    ) -> HookResult:
        if hook.type == HookExecutionType.COMMAND:
            return await self._execute_command_hook(hook, input_data)
        elif hook.type == HookExecutionType.CALLBACK:
            return HookResult(outcome="success")
        elif hook.type == HookExecutionType.HTTP:
            return await self._execute_http_hook(hook, input_data)
        elif hook.type == HookExecutionType.PROMPT:
            return HookResult(outcome="success")
        return HookResult(outcome="success")

    async def _execute_command_hook(
        self,
        hook: HookDefinition,
        input_data: HookInput,
    ) -> HookResult:
        try:
            env = os.environ.copy()
            env["CLAUDE_HOOK_EVENT"] = input_data.hook_event.value
            env["CLAUDE_SESSION_ID"] = input_data.session_id
            env["CLAUDE_CWD"] = input_data.cwd

            if input_data.tool_input:
                env["CLAUDE_TOOL_INPUT"] = json.dumps(input_data.tool_input)
            if input_data.tool_name:
                env["CLAUDE_TOOL_NAME"] = input_data.tool_name

            process = await asyncio.create_subprocess_shell(
                hook.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=input_data.cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=hook.timeout,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return HookResult(
                    outcome="non_blocking_error",
                    message=f"Hook timed out after {hook.timeout}s",
                )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                stderr_str = stderr.decode("utf-8", errors="replace").strip()
                return HookResult(
                    outcome="non_blocking_error",
                    message=stderr_str or f"Hook exited with code {process.returncode}",
                )

            hook_output = self._parse_hook_output(stdout_str)
            result = HookResult(outcome="success", message=stdout_str)

            if hook_output:
                if "continue" in hook_output and hook_output["continue"] is False:
                    result.prevent_continuation = True
                    result.stop_reason = hook_output.get("stopReason")
                if "decision" in hook_output:
                    result.permission_behavior = hook_output["decision"]
                if "reason" in hook_output:
                    result.permission_decision_reason = hook_output["reason"]
                if "systemMessage" in hook_output:
                    result.system_message = hook_output["systemMessage"]

            return result

        except Exception as exc:
            return HookResult(
                outcome="non_blocking_error",
                message=str(exc),
            )

    async def _execute_http_hook(
        self,
        hook: HookDefinition,
        input_data: HookInput,
    ) -> HookResult:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=hook.timeout) as client:
                resp = await client.post(
                    hook.command,
                    json={
                        "event": input_data.hook_event.value,
                        "tool_name": input_data.tool_name,
                        "tool_input": input_data.tool_input,
                        "session_id": input_data.session_id,
                        "cwd": input_data.cwd,
                    },
                )
                data = resp.json() if resp.text else {}
                result = HookResult(
                    outcome="success" if resp.status_code < 400 else "non_blocking_error"
                )
                if isinstance(data, dict):
                    if data.get("continue") is False:
                        result.prevent_continuation = True
                        result.stop_reason = data.get("stopReason")
                    result.message = data.get("message", "")
                return result
        except Exception as exc:
            return HookResult(outcome="non_blocking_error", message=str(exc))

    def _parse_hook_output(self, output: str) -> dict[str, Any] | None:
        try:
            for line in output.strip().split("\n"):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    return json.loads(line)
        except json.JSONDecodeError:
            pass
        return None

    def aggregate_results(self, results: list[HookResult]) -> HookResult:
        if not results:
            return HookResult(outcome="success")

        aggregated = HookResult(outcome="success")
        errors: list[str] = []
        contexts: list[str] = []

        for r in results:
            if r.outcome == "blocking":
                aggregated.outcome = "blocking"
                aggregated.blocking_error = r.blocking_error or r.message
                break
            if r.prevent_continuation:
                aggregated.prevent_continuation = True
                aggregated.stop_reason = r.stop_reason
            if r.permission_behavior:
                aggregated.permission_behavior = r.permission_behavior
            if r.permission_decision_reason:
                aggregated.permission_decision_reason = r.permission_decision_reason
            if r.additional_context:
                contexts.append(r.additional_context)
            if r.updated_input:
                aggregated.updated_input = r.updated_input
            if r.outcome == "non_blocking_error":
                errors.append(r.message or "Unknown error")
            if r.retry:
                aggregated.retry = True

        if errors and aggregated.outcome != "blocking":
            aggregated.system_message = "; ".join(errors)
        if contexts:
            aggregated.additional_context = "\n".join(contexts)

        return aggregated


_global_registry: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = HookRegistry()
    return _global_registry


def reset_hook_registry() -> None:
    global _global_registry
    _global_registry = None

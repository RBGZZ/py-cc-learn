from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Generator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from server.services.compact import AUTOCOMPACT_BUFFER_TOKENS, COMPACT_MAX_OUTPUT_TOKENS, _get_context_window_for_model
from server.services.provider import Provider, StreamEvent
from server.state.session import SessionStorage
from server.tools.streaming import (
    AssistantMessage,
    StreamingToolExecutor,
    ToolUseBlock,
)


class QueryExitReason(str, Enum):
    COMPLETED = "completed"
    MAX_TURNS = "max_turns"
    MODEL_ERROR = "model_error"
    BLOCKING_LIMIT = "blocking_limit"
    ABORTED_STREAMING = "aborted_streaming"
    ABORTED_TOOLS = "aborted_tools"
    IMAGE_ERROR = "image_error"
    STOP_HOOK_PREVENTED = "stop_hook_prevented"
    MAX_OUTPUT_TOKENS_RECOVERIES = "max_output_tokens_max_recoveries"
    CANCELLED_BY_USER = "cancelled_by_user"
    PROMPT_TOO_LONG = "prompt_too_long"
    HOOK_STOPPED = "hook_stopped"


class ContinueReason(str, Enum):
    NEXT_TURN = "next_turn"
    MAX_OUTPUT_TOKENS_ESCALATE = "max_output_tokens_escalate"
    MAX_OUTPUT_TOKENS_RECOVERY = "max_output_tokens_recovery"
    TOKEN_BUDGET_CONTINUATION = "token_budget_continuation"
    COLLAPSE_DRAIN_RETRY = "collapse_drain_retry"
    REACTIVE_COMPACT_RETRY = "reactive_compact_retry"
    STOP_HOOK_BLOCKING = "stop_hook_blocking"


MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3
DEFAULT_MAX_TURNS = 50
MAX_OUTPUT_TOKENS_DEFAULT = 32000
MAX_OUTPUT_TOKENS_FLOOR = 3000
TOKEN_BUDGET_RATIO = 0.9
DIMINISHING_RETURNS_DELTA_THRESHOLD = 500
DIMINISHING_RETURNS_CONSECUTIVE = 3
ESCALATED_MAX_TOKENS = 64000
CAPPED_DEFAULT_MAX_TOKENS = 8000


def get_auto_compact_threshold(context_window: int) -> int:
    return context_window - AUTOCOMPACT_BUFFER_TOKENS


AUTO_COMPACT_TOKEN_THRESHOLD = get_auto_compact_threshold(200_000)


def get_current_turn_token_budget(model: str, state) -> int:
    from server.services.compact import _get_context_window_for_model
    context_window = _get_context_window_for_model(model)
    used = state.total_usage.get("input_tokens", 0) if state else 0
    available = context_window - used
    return max(available, COMPACT_MAX_OUTPUT_TOKENS)


class DynamicAbortController:
    def __init__(self, event: asyncio.Event, reason: str | None = None):
        self._event = event
        self._reason = reason

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    @property
    def signal(self) -> asyncio.Event:
        return self._event

    @property
    def reason(self) -> str | None:
        return self._reason


@dataclass
class QueryEngineConfig:
    cwd: str = ""
    tools: list[Any] = field(default_factory=list)
    provider: Provider | None = None
    system_prompt: str = ""
    max_turns: int = DEFAULT_MAX_TURNS
    fallback_model: str | None = None
    session_storage: SessionStorage | None = None
    abort_signal: asyncio.Event | None = None
    on_stream_event: Callable[[StreamEvent], Any] | None = None
    is_auto_compact_enabled: bool = True
    feature_gates: dict[str, bool] = field(default_factory=dict)
    user_context: dict[str, str] = field(default_factory=dict)


@dataclass
class QueryState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    max_output_tokens_recovery_count: int = 0
    max_output_tokens_override: int | None = None
    consecutive_low_output_count: int = 0
    total_usage: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    )
    last_turn_output_tokens: int = 0
    last_turn_delta: int = 0
    _compact_boundary_index: int = 0
    _has_attempted_collapse_drain: bool = False
    _has_attempted_reactive_compact: bool = False


class QueryEngine:
    def __init__(self, config: QueryEngineConfig) -> None:
        self.config = config
        self.state = QueryState()
        self._abort = config.abort_signal or asyncio.Event()
        self._system_prompt = config.system_prompt
        self._tools = config.tools
        self._tool_map: dict[str, Any] = {}
        for t in config.tools:
            if hasattr(t, "name"):
                self._tool_map[t.name] = t
            if hasattr(t, "aliases") and t.aliases:
                for alias in t.aliases:
                    self._tool_map[alias] = t
        self._hooks: list[Callable[..., Any]] = []
        self._task_hooks: list[Callable[..., Any]] = []
        self._teammate_hooks: list[Callable[..., Any]] = []

    def register_hook(self, hook: Callable[..., Any]) -> None:
        self._hooks.append(hook)

    def register_task_hook(self, hook: Callable[..., Any]) -> None:
        self._task_hooks.append(hook)

    def register_teammate_hook(self, hook: Callable[..., Any]) -> None:
        self._teammate_hooks.append(hook)

    async def submit_message(self, prompt: str | list[dict[str, Any]], is_meta: bool = False) -> AsyncGenerator[dict[str, Any], None]:
        if self._abort.is_set():
            yield {"type": "result", "subtype": "error_during_execution", "stop_reason": QueryExitReason.CANCELLED_BY_USER.value}
            return

        user_msg: dict[str, Any] = {
            "type": "user", "uuid": str(uuid.uuid4()),
            "message": {"role": "user", "content": prompt if isinstance(prompt, str) else prompt},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
        self.state.messages.append(user_msg)

        if self.config.session_storage and not is_meta:
            await self.config.session_storage.insert_message_chain([{
                "type": "user", "uuid": user_msg["uuid"], "message": user_msg["message"], "timestamp": user_msg["timestamp"],
            }])

        yield {"type": "system_init", "model": self.config.provider.get_default_model() if self.config.provider else "unknown", "tools": [t.name for t in self._tools if hasattr(t, "name")]}

        stop_reason: str | None = None
        async for event in self._query_loop():
            event_type = event.get("type", "")
            if event_type == "assistant":
                msg = event.get("data", event)
                self.state.messages.append(msg)
                if self.config.session_storage and not is_meta:
                    await self.config.session_storage.insert_message_chain([{"type": "assistant", "uuid": msg.get("uuid", str(uuid.uuid4())), "message": msg.get("message", msg), "timestamp": msg.get("timestamp")}])
                yield msg
            elif event_type == "stream_event":
                if self.config.on_stream_event:
                    self.config.on_stream_event(StreamEvent(type="stream_event", data=event.get("data", event)))
                yield event
            elif event_type == "text_delta":
                yield {"type": "text_delta", "text": event.get("data", {}).get("text", "")}
            elif event_type == "error":
                yield event
                return
            elif event_type == "exit":
                stop_reason = event.get("data", {}).get("reason", QueryExitReason.COMPLETED.value)
                break
            elif event_type == "tool_result":
                yield event

        yield {"type": "result", "subtype": "success" if stop_reason == QueryExitReason.COMPLETED.value else "error_during_execution", "stop_reason": stop_reason, "turn_count": self.state.turn_count, "usage": self.state.total_usage}

    async def _query_loop(self) -> AsyncGenerator[dict[str, Any], None]:
        while self.state.turn_count < self.config.max_turns:
            if self._abort.is_set():
                yield {"type": "exit", "data": {"reason": QueryExitReason.ABORTED_STREAMING.value}}
                return

            if self.state.turn_count > 0:
                compact_result = self._check_auto_compact()
                if compact_result:
                    yield {"type": "exit", "data": {"reason": compact_result}}
                    return

            yield {"type": "stream_request_start", "data": {}}

            streaming_fallback_occurred = False
            self.state._has_attempted_collapse_drain = False
            self.state._has_attempted_reactive_compact = False
            assistant_msgs: list[dict[str, Any]] = []
            tool_use_blocks: list[dict[str, Any]] = []
            needs_follow_up = False
            current_model = self.config.fallback_model or ""

            abort_controller = DynamicAbortController(self._abort)

            def _make_executor() -> StreamingToolExecutor:
                tool_use_context = type("ToolUseContext", (), {"options": type("Options", (), {"tools": self._tools})(), "abort_controller": abort_controller, "get_app_state": lambda: None, "set_app_state": lambda f: None})()
                def _can_use_tool(*args: Any, **kwargs: Any) -> dict[str, str]: return {"behavior": "allow"}
                return StreamingToolExecutor(tool_definitions=self._tools, can_use_tool=_can_use_tool, tool_use_context=tool_use_context)

            executor = _make_executor()

            async def _run_single_tool(block: ToolUseBlock, assistant_msg_obj: AssistantMessage, can_use: Callable, ctx: Any) -> AsyncGenerator[dict[str, Any], None]:
                tool = self._tool_map.get(block.name)
                if tool is None:
                    yield {"message": _make_user_message_dict([_make_tool_result_block(block.id, f"Tool '{block.name}' not found", is_error=True)], f"Error: Tool '{block.name}' not found", assistant_msg_obj.uuid)}
                    return
                try:
                    result = await tool.call(block.input, ctx)
                    content_str = json.dumps(result, default=str) if isinstance(result, dict) else str(result)
                    yield {"message": _make_user_message_dict([_make_tool_result_block(block.id, content_str)], content_str[:500], assistant_msg_obj.uuid)}
                except Exception as exc:
                    yield {"message": _make_user_message_dict([_make_tool_result_block(block.id, str(exc), is_error=True)], str(exc)[:500], assistant_msg_obj.uuid)}

            executor.set_run_tool_use_fn(_run_single_tool)

            _retry_count = 0
            while True:
                _retry_count += 1
                if _retry_count > 2:
                    break

                try:
                    async for event in self._call_model():
                        event_type = event.get("type", "")
                        if event_type in ("assistant", "stream_event", "text_delta", "error"):
                            yield event

                        if event_type == "assistant":
                            msg = event.get("data", event)
                            self._update_usage_from_msg(msg)
                            assistant_msgs.append(msg)
                            if self._has_tool_use(msg):
                                needs_follow_up = True
                                tb = self._extract_tool_blocks(msg)
                                tool_use_blocks.extend(tb)
                                if not self._abort.is_set():
                                    for tool_block in tb:
                                        executor.add_tool(ToolUseBlock(id=tool_block.get("id", ""), name=tool_block.get("name", ""), input=self._parse_tool_input(tool_block.get("input", {}))), AssistantMessage(uuid=msg.get("uuid", str(uuid.uuid4()))))

                        if not self._abort.is_set():
                            for completed in executor.get_completed_results():
                                update_msg = completed.get("message")
                                if update_msg is not None:
                                    for ev in self._handle_tool_update(update_msg):
                                        yield ev

                        if event_type == "error":
                            yield {"type": "exit", "data": {"reason": QueryExitReason.MODEL_ERROR.value}}
                            return

                    break  # success — exit retry loop

                except asyncio.CancelledError:
                    for ev in self._yield_missing_tool_results(assistant_msgs, "Interrupted by user", None): yield ev
                    yield _make_interruption_message()
                    yield {"type": "exit", "data": {"reason": QueryExitReason.CANCELLED_BY_USER.value}}
                    return
                except StreamingFallbackError:
                    if not self.config.fallback_model:
                        yield {"type": "error", "data": {"message": "Streaming failed, no fallback model configured"}}
                        yield {"type": "exit", "data": {"reason": QueryExitReason.MODEL_ERROR.value}}
                        return
                    streaming_fallback_occurred = True
                    executor.discard()
                    current_model = self.config.fallback_model
                    self.config.provider.config.model = current_model
                    assistant_msgs.clear()
                    tool_use_blocks.clear()
                    needs_follow_up = False
                    executor = _make_executor()
                    executor.set_run_tool_use_fn(_run_single_tool)
                    yield {"type": "stream_event", "data": {"type": "system", "subtype": "streaming_fallback", "message": "Streaming connection lost — retrying..."}}
                    continue
                except Exception as exc:
                    if not needs_follow_up and self.config.fallback_model:
                        yield {"type": "stream_event", "data": {"type": "system", "subtype": "model_fallback", "fallback_model": self.config.fallback_model}}
                        needs_follow_up = True
                        break
                    else:
                        for ev in self._yield_missing_tool_results(assistant_msgs, f"Model error: {exc}", None): yield ev
                        yield {"type": "error", "data": {"message": f"Model invocation failed: {exc}"}}
                        yield {"type": "exit", "data": {"reason": QueryExitReason.MODEL_ERROR.value}}
                        return

            if streaming_fallback_occurred and not needs_follow_up:
                needs_follow_up = True

            if assistant_msgs:
                self._execute_post_sampling_hooks(assistant_msgs)

            if self._abort.is_set():
                executor.discard()
                async for update in executor.get_remaining_results():
                    if update.get("message") is not None:
                        for ev in self._handle_tool_update(update["message"]): yield ev
                for ev in self._yield_missing_tool_results(assistant_msgs, "Interrupted by user", None): yield ev
                yield _make_interruption_message()
                yield {"type": "exit", "data": {"reason": QueryExitReason.ABORTED_STREAMING.value}}
                return

            if needs_follow_up and tool_use_blocks:
                async for update in executor.get_remaining_results():
                    if update.get("message") is not None:
                        for ev in self._handle_tool_update(update["message"]): yield ev

            self._execute_task_completed_hooks()
            self._execute_teammate_idle_hooks()

            if not needs_follow_up:
                ptl_result = self._try_prompt_too_long_recovery(assistant_msgs)
                if ptl_result == "retry":
                    needs_follow_up = True
                    assistant_msgs.clear()
                    tool_use_blocks.clear()
                    executor = _make_executor()
                    executor.set_run_tool_use_fn(_run_single_tool)
                elif ptl_result == "surface":
                    yield {"type": "exit", "data": {"reason": QueryExitReason.PROMPT_TOO_LONG.value}}
                    return

            if not needs_follow_up:
                if self._check_token_budget_on_state():
                    needs_follow_up = True
                if self._is_max_output_tokens_from_msgs(assistant_msgs):
                    handled = self._handle_max_output_tokens_recovery()
                    if handled:
                        needs_follow_up = True
                    else:
                        yield {"type": "exit", "data": {"reason": QueryExitReason.MAX_OUTPUT_TOKENS_RECOVERIES.value}}
                        return

                stop_result = self._execute_stop_hooks()
                if stop_result.get("prevent_continuation"):
                    yield {"type": "exit", "data": {"reason": QueryExitReason.STOP_HOOK_PREVENTED.value}}
                    return
                if stop_result.get("blocking_errors"):
                    needs_follow_up = True

            if not needs_follow_up:
                yield {"type": "exit", "data": {"reason": QueryExitReason.COMPLETED.value}}
                return

            self.state.turn_count += 1

        yield {"type": "exit", "data": {"reason": QueryExitReason.MAX_TURNS.value, "turn_count": self.state.turn_count}}

    def _handle_tool_update(self, update_msg: Any) -> Generator[dict[str, Any], None, None]:
        msg_type = update_msg.get("type") if isinstance(update_msg, dict) else getattr(update_msg, "type", None)
        if msg_type == "user":
            msg_inner = update_msg.get("message") if isinstance(update_msg, dict) else getattr(update_msg, "message", None)
            if msg_inner is not None:
                inner_content = msg_inner.get("content") if isinstance(msg_inner, dict) else getattr(msg_inner, "content", None)
                if inner_content is not None:
                    user_result_msg: dict[str, Any] = {"type": "user", "uuid": str(uuid.uuid4()), "message": {"role": "user", "content": inner_content}, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}
                    self.state.messages.append(user_result_msg)
                    if isinstance(inner_content, list):
                        for result_block in inner_content:
                            yield {"type": "tool_result", "data": result_block}
                    elif isinstance(inner_content, dict):
                        yield {"type": "tool_result", "data": inner_content}

    async def _call_model(self) -> AsyncGenerator[dict[str, Any], None]:
        if not self.config.provider:
            yield {"type": "error", "data": {"message": "No provider configured"}}
            return
        messages_for_api = self._build_messages_for_api()
        tool_schemas = self._build_tool_schemas()
        max_tokens = self.state.max_output_tokens_override or getattr(self.config.provider.config, "max_tokens", MAX_OUTPUT_TOKENS_DEFAULT)
        self.config.provider.config.max_tokens = max_tokens
        async for event in self.config.provider.stream_chat(messages=messages_for_api, system_prompt=self._system_prompt, tools=tool_schemas):
            yield {"type": event.type, "data": event.data}

    def _build_messages_for_api(self) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []
        start_idx = self.state._compact_boundary_index
        for msg in self.state.messages[start_idx:]:
            if msg.get("is_meta") or msg.get("is_virtual"):
                continue
            if msg.get("type", "") in ("user", "assistant"):
                api_messages.append(self._normalize_api_message(msg))
        return self._merge_consecutive_user_messages(api_messages)

    @staticmethod
    def _merge_consecutive_user_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("type") == "user" and result and result[-1].get("type") == "user":
                prev = result[-1]
                prev_content = prev.get("message", prev).get("content", [])
                cur_content = msg.get("message", msg).get("content", [])
                if isinstance(prev_content, list) and isinstance(cur_content, list):
                    merged = prev_content + cur_content
                elif isinstance(prev_content, list):
                    merged = prev_content + [cur_content]
                elif isinstance(cur_content, list):
                    merged = [prev_content] + cur_content
                else:
                    merged = [prev_content, cur_content]
                prev["message"] = {**prev.get("message", prev), "content": merged}
            else:
                result.append(msg)
        return result

    @staticmethod
    def _normalize_api_message(msg: dict[str, Any]) -> dict[str, Any]:
        msg_data = msg.get("message", msg)
        content = msg_data.get("content", [])
        if not isinstance(content, list):
            return msg
        cleaned = [b for b in content if isinstance(b, dict) and b.get("type", "") in ("text", "tool_use", "tool_result", "thinking")]
        if not cleaned:
            cleaned = [{"type": "text", "text": ""}]
        return {**msg, "message": {**msg_data, "content": cleaned}}

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for tool in self._tools:
            schema: dict[str, Any] = {"name": getattr(tool, "name", ""), "description": getattr(tool, "search_hint", "") or ""}
            input_schema = getattr(tool, "input_schema", None)
            if input_schema:
                try:
                    schema["input_schema"] = input_schema.model_json_schema() if hasattr(input_schema, "model_json_schema") else None
                except Exception:
                    schema["input_schema"] = None
            schemas.append(schema)
        return schemas

    def _has_tool_use(self, msg: dict[str, Any]) -> bool:
        content = msg.get("message", msg).get("content", [])
        return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content)

    @staticmethod
    def _extract_tool_blocks(msg: dict[str, Any]) -> list[dict[str, Any]]:
        content = msg.get("message", msg).get("content", [])
        return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"] if isinstance(content, list) else []

    @staticmethod
    def _is_max_output_tokens_from_msgs(msgs: list[dict[str, Any]]) -> bool:
        return any(msg.get("message", msg).get("stop_reason", "") in ("max_tokens", "length") for msg in msgs)

    def _handle_max_output_tokens_recovery(self) -> bool:
        if self.state.max_output_tokens_recovery_count >= MAX_OUTPUT_TOKENS_RECOVERY_LIMIT:
            return False
        if self.state.max_output_tokens_override is None and self.state.max_output_tokens_recovery_count == 0:
            cap_enabled = self.config.feature_gates.get("tengu_otk_slot_v1", False)
            if cap_enabled:
                self.state.max_output_tokens_override = ESCALATED_MAX_TOKENS
                self.state.max_output_tokens_recovery_count = 1
                return True
        self.state.max_output_tokens_recovery_count += 1
        self.state.messages.append({"type": "user", "uuid": str(uuid.uuid4()), "message": {"role": "user", "content": "Output token limit hit. Resume directly — no apology, no recap of what you were doing. Pick up mid-thought if that is where the cut happened. Break remaining work into smaller pieces."}, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()), "is_meta": True})
        return True

    def _yield_missing_tool_results(self, assistant_msgs: list[dict[str, Any]], error_message: str, _executor: Any) -> Generator[dict[str, Any], None, None]:
        for assistant_msg in assistant_msgs:
            for tb in self._extract_tool_blocks(assistant_msg):
                error_block = _make_tool_result_block(tb.get("id", ""), error_message, is_error=True)
                self.state.messages.append({"type": "user", "uuid": str(uuid.uuid4()), "message": {"role": "user", "content": [error_block]}, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())})
                yield {"type": "tool_result", "data": error_block}

    def _try_prompt_too_long_recovery(self, assistant_msgs: list[dict[str, Any]]) -> str | None:
        withheld = self._is_withheld_prompt_too_long(assistant_msgs)
        if not withheld:
            return None
        if not self.state._has_attempted_collapse_drain:
            self.state._has_attempted_collapse_drain = True
            return "retry"
        if not self.state._has_attempted_reactive_compact:
            self.state._has_attempted_reactive_compact = True
            self._try_reactive_compact()
            return "retry"
        return "surface"

    @staticmethod
    def _is_withheld_prompt_too_long(assistant_msgs: list[dict[str, Any]]) -> bool:
        for msg in assistant_msgs:
            inner = msg.get("message", msg)
            if inner.get("type") == "assistant" and inner.get("is_api_error_message"):
                content = inner.get("content", [])
                if isinstance(content, list) and content and isinstance(content[0], dict):
                    if "prompt too long" in str(content[0].get("text", "")).lower():
                        return True
        return False

    def _try_reactive_compact(self) -> None:
        try:
            self.state._compact_boundary_index = max(0, len(self.state.messages) // 2)
        except Exception:
            pass

    def _execute_post_sampling_hooks(self, assistant_msgs: list[dict[str, Any]]) -> None:
        for hook in self._hooks:
            with contextlib.suppress(Exception):
                hook("post_sampling", {"assistant_msgs": assistant_msgs, "system_prompt": self._system_prompt, "user_context": self.config.user_context})

    def _execute_stop_hooks(self) -> dict[str, Any]:
        result: dict[str, Any] = {"prevent_continuation": False, "blocking_errors": []}
        for hook in self._hooks:
            with contextlib.suppress(Exception):
                hook_result = hook("stop", {"turn_count": self.state.turn_count})
                if isinstance(hook_result, dict):
                    if hook_result.get("prevent_continuation"): result["prevent_continuation"] = True
                    blocking = hook_result.get("blocking_errors")
                    if blocking: result["blocking_errors"].extend(blocking if isinstance(blocking, list) else [blocking])
        return result

    def _execute_task_completed_hooks(self) -> None:
        for hook in self._task_hooks:
            with contextlib.suppress(Exception):
                hook("task_completed", {"turn_count": self.state.turn_count})

    def _execute_teammate_idle_hooks(self) -> None:
        for hook in self._teammate_hooks:
            with contextlib.suppress(Exception):
                hook("teammate_idle", {"turn_count": self.state.turn_count})

    @staticmethod
    def _parse_tool_input(raw_input: Any) -> dict[str, Any]:
        if isinstance(raw_input, dict): return raw_input
        if isinstance(raw_input, str):
            try: return json.loads(raw_input)
            except json.JSONDecodeError: return {}
        return {}

    def _check_auto_compact(self) -> str | None:
        if not self.config.is_auto_compact_enabled: return None
        model = self.config.provider.config.model if self.config.provider else ""
        context_window = _get_context_window_for_model(model)
        threshold = get_auto_compact_threshold(context_window)
        estimated_tokens = self._compute_estimated_tokens()
        if estimated_tokens < threshold: return None
        tokens_freed = self._try_snip_compact() + self._try_microcompact()
        if tokens_freed > 0:
            self.state._compact_boundary_index = max(0, len(self.state.messages) - 20)
        if self._compute_estimated_tokens() >= threshold:
            return QueryExitReason.BLOCKING_LIMIT.value
        return None

    def _try_snip_compact(self) -> int:
        msgs = self.state.messages
        if len(msgs) <= 30: return 0
        removed = 0
        for i in range(len(msgs) - 20):
            if msgs[i].get("type") in ("user", "assistant"):
                msgs[i] = {**msgs[i], "_snipped": True}
                removed += 1
        return removed

    def _try_microcompact(self) -> int:
        try:
            from server.services.compact import microcompact_messages
            return int(microcompact_messages(self.state.messages).get("tokens_saved", 0))
        except Exception:
            return 0

    def _compute_estimated_tokens(self) -> int:
        usage = self.state.total_usage
        api_estimate = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        if api_estimate > 0: return api_estimate
        total_chars = 0
        for msg in self.state.messages:
            content = msg.get("message", msg).get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                total_chars += sum(len(str(b.get("text", b.get("content", "")))) for b in content if isinstance(b, dict))
        return max(1, int(total_chars * 0.25))

    def _check_token_budget_on_state(self) -> bool:
        return self._check_token_budget(self.state.total_usage)

    def _check_token_budget(self, usage: dict) -> bool:
        model = getattr(self.config.provider, "config", None)
        model_name = getattr(model, "model", "claude-sonnet-4-20250514") if model else "claude-sonnet-4-20250514"
        budget = get_current_turn_token_budget(model_name, self.state)

        output_tokens = usage.get("output_tokens", 0)
        threshold = int(budget * TOKEN_BUDGET_RATIO)

        if output_tokens >= threshold:
            delta = output_tokens - self.state.last_turn_output_tokens
            if delta < DIMINISHING_RETURNS_DELTA_THRESHOLD:
                if self.state.last_turn_delta < DIMINISHING_RETURNS_DELTA_THRESHOLD:
                    return True
                self.state.last_turn_delta = delta
            else:
                self.state.last_turn_delta = delta
        else:
            self.state.last_turn_delta = 0

        self.state.last_turn_output_tokens = output_tokens
        return False

    def interrupt(self) -> None:
        self._abort.set()

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self.state.messages)

    def get_total_usage(self) -> dict[str, int]:
        return dict(self.state.total_usage)

    def _update_usage(self, usage: dict[str, Any]) -> None:
        for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            if usage.get(k):
                self.state.total_usage[k] += usage[k]

    def _update_usage_from_msg(self, msg: dict[str, Any]) -> None:
        usage = msg.get("message", msg).get("usage", {})
        if usage: self._update_usage(usage)


class StreamingFallbackError(RuntimeError):
    """Raised when the streaming connection fails and needs fallback. Source: query.ts L678-741."""


def _make_tool_result_block(tool_use_id: str, content: str, is_error: bool = False) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}

def _make_user_message_dict(content: list[dict[str, Any]], tool_use_result: str, source_uuid: str) -> dict[str, Any]:
    return {"type": "user", "message": {"type": "user", "content": content}, "tool_use_result": tool_use_result, "source_tool_assistant_uuid": source_uuid}

def _make_interruption_message() -> dict[str, Any]:
    return {"type": "user", "uuid": str(uuid.uuid4()), "message": {"role": "user", "content": [{"type": "text", "text": "Interrupted by user"}]}, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()), "is_meta": True}

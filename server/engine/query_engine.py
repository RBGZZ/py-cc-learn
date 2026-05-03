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
AUTO_COMPACT_TOKEN_THRESHOLD = 180_000
TOKEN_BUDGET_RATIO = 0.9
DIMINISHING_RETURNS_DELTA_THRESHOLD = 500
DIMINISHING_RETURNS_CONSECUTIVE = 3
ESCALATED_MAX_TOKENS = 64000


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
    _compact_boundary_index: int = 0


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

    def register_hook(self, hook: Callable[..., Any]) -> None:
        self._hooks.append(hook)

    async def submit_message(
        self,
        prompt: str | list[dict[str, Any]],
        is_meta: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if self._abort.is_set():
            yield {
                "type": "result",
                "subtype": "error_during_execution",
                "stop_reason": QueryExitReason.CANCELLED_BY_USER.value,
            }
            return

        user_msg: dict[str, Any] = {
            "type": "user",
            "uuid": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "content": prompt if isinstance(prompt, str) else prompt,
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
        self.state.messages.append(user_msg)

        if self.config.session_storage and not is_meta:
            await self.config.session_storage.insert_message_chain(
                [
                    {
                        "type": "user",
                        "uuid": user_msg["uuid"],
                        "message": user_msg["message"],
                        "timestamp": user_msg["timestamp"],
                    },
                ]
            )

        yield {
            "type": "system_init",
            "model": self.config.provider.get_default_model()
            if self.config.provider
            else "unknown",
            "tools": [t.name for t in self._tools if hasattr(t, "name")],
        }

        stop_reason: str | None = None

        async for event in self._query_loop():
            event_type = event.get("type", "")

            if event_type == "assistant":
                msg = event.get("data", event)
                self.state.messages.append(msg)

                if self.config.session_storage and not is_meta:
                    await self.config.session_storage.insert_message_chain(
                        [
                            {
                                "type": "assistant",
                                "uuid": msg.get("uuid", str(uuid.uuid4())),
                                "message": msg.get("message", msg),
                                "timestamp": msg.get("timestamp"),
                            },
                        ]
                    )

                yield msg

            elif event_type == "stream_event":
                if self.config.on_stream_event:
                    self.config.on_stream_event(
                        StreamEvent(
                            type="stream_event",
                            data=event.get("data", event),
                        )
                    )
                yield event

            elif event_type == "text_delta":
                delta = event.get("data", {}).get("text", "")
                yield {"type": "text_delta", "text": delta}

            elif event_type == "error":
                yield event
                return

            elif event_type == "exit":
                stop_reason = event.get("data", {}).get(
                    "reason", QueryExitReason.COMPLETED.value
                )
                break

            elif event_type == "tool_result":
                yield event

        yield {
            "type": "result",
            "subtype": "success"
            if stop_reason == QueryExitReason.COMPLETED.value
            else "error_during_execution",
            "stop_reason": stop_reason,
            "turn_count": self.state.turn_count,
            "usage": self.state.total_usage,
        }

    async def _query_loop(self) -> AsyncGenerator[dict[str, Any], None]:
        while self.state.turn_count < self.config.max_turns:
            if self._abort.is_set():
                yield {
                    "type": "exit",
                    "data": {"reason": QueryExitReason.ABORTED_STREAMING.value},
                }
                return

            if self.state.turn_count > 0:
                compact_result = self._check_auto_compact()
                if compact_result:
                    yield {"type": "exit", "data": {"reason": compact_result}}
                    return

            yield {"type": "stream_request_start", "data": {}}

            assistant_msgs: list[dict[str, Any]] = []
            tool_use_blocks: list[dict[str, Any]] = []
            needs_follow_up = False

            abort_controller = DynamicAbortController(self._abort)
            tool_use_context = type(
                "ToolUseContext",
                (),
                {
                    "options": type("Options", (), {"tools": self._tools})(),
                    "abort_controller": abort_controller,
                    "get_app_state": lambda: None,
                    "set_app_state": lambda f: None,
                },
            )()

            def _can_use_tool(*args: Any, **kwargs: Any) -> dict[str, str]:
                return {"behavior": "allow"}

            executor = StreamingToolExecutor(
                tool_definitions=self._tools,
                can_use_tool=_can_use_tool,
                tool_use_context=tool_use_context,
            )

            async def _run_single_tool(
                block: ToolUseBlock,
                assistant_msg_obj: AssistantMessage,
                can_use: Callable,
                ctx: Any,
            ) -> AsyncGenerator[dict[str, Any], None]:
                tool = self._tool_map.get(block.name)
                if tool is None:
                    error_block = _make_tool_result_block(
                        block.id, f"Tool '{block.name}' not found", is_error=True
                    )
                    yield {
                        "message": _make_user_message_dict(
                            [error_block],
                            f"Error: Tool '{block.name}' not found",
                            assistant_msg_obj.uuid,
                        ),
                    }
                    return

                try:
                    result = await tool.call(block.input, ctx)
                    if isinstance(result, dict):
                        content_str = json.dumps(result, default=str)
                    else:
                        content_str = str(result)
                    result_block = _make_tool_result_block(block.id, content_str)
                    yield {
                        "message": _make_user_message_dict(
                            [result_block],
                            content_str[:500],
                            assistant_msg_obj.uuid,
                        ),
                    }
                except Exception as exc:
                    error_block = _make_tool_result_block(
                        block.id, str(exc), is_error=True
                    )
                    yield {
                        "message": _make_user_message_dict(
                            [error_block],
                            str(exc)[:500],
                            assistant_msg_obj.uuid,
                        ),
                    }

            executor.set_run_tool_use_fn(_run_single_tool)

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

                            msg_uuid = msg.get("uuid", str(uuid.uuid4()))
                            if not self._abort.is_set():
                                for tool_block in tb:
                                    executor.add_tool(
                                        ToolUseBlock(
                                            id=tool_block.get("id", ""),
                                            name=tool_block.get("name", ""),
                                            input=self._parse_tool_input(
                                                tool_block.get("input", {})
                                            ),
                                        ),
                                        AssistantMessage(uuid=msg_uuid),
                                    )

                    if not self._abort.is_set() and (
                        event_type == "assistant" or event_type == "text_delta"
                    ):
                        for completed in executor.get_completed_results():
                            update_msg = completed.get("message")
                            if update_msg is not None:
                                for ev in self._handle_tool_update(update_msg):
                                    yield ev

                    if event_type == "error":
                        yield {
                            "type": "exit",
                            "data": {"reason": QueryExitReason.MODEL_ERROR.value},
                        }
                        return

            except asyncio.CancelledError:
                for ev in self._yield_missing_tool_results(assistant_msgs, "Interrupted by user", None):
                    yield ev
                yield _make_interruption_message()
                yield {
                    "type": "exit",
                    "data": {"reason": QueryExitReason.CANCELLED_BY_USER.value},
                }
                return
            except Exception as exc:
                if not needs_follow_up and self.config.fallback_model:
                    yield {
                        "type": "stream_event",
                        "data": {
                            "type": "system",
                            "subtype": "model_fallback",
                            "fallback_model": self.config.fallback_model,
                        },
                    }
                    needs_follow_up = True
                else:
                    for ev in self._yield_missing_tool_results(
                        assistant_msgs, f"Model error: {exc}", None
                    ):
                        yield ev
                    yield {"type": "error", "data": {"message": f"Model invocation failed: {exc}"}}
                    yield {"type": "exit", "data": {"reason": QueryExitReason.MODEL_ERROR.value}}
                    return

            if assistant_msgs:
                self._execute_post_sampling_hooks(assistant_msgs)

            if self._abort.is_set():
                executor.discard()
                async for update in executor.get_remaining_results():
                    update_msg = update.get("message")
                    if update_msg is not None:
                        for ev in self._handle_tool_update(update_msg):
                            yield ev
                for ev in self._yield_missing_tool_results(assistant_msgs, "Interrupted by user", None):
                    yield ev
                yield _make_interruption_message()
                yield {
                    "type": "exit",
                    "data": {"reason": QueryExitReason.ABORTED_STREAMING.value},
                }
                return

            if needs_follow_up and tool_use_blocks:
                async for update in executor.get_remaining_results():
                    update_msg = update.get("message")
                    if update_msg is not None:
                        for ev in self._handle_tool_update(update_msg):
                            yield ev

            if not needs_follow_up:
                if self._check_token_budget_on_state():
                    needs_follow_up = True
                if self._is_max_output_tokens_from_msgs(assistant_msgs):
                    handled = self._handle_max_output_tokens_recovery()
                    if handled:
                        needs_follow_up = True
                    else:
                        yield {
                            "type": "exit",
                            "data": {
                                "reason": QueryExitReason.MAX_OUTPUT_TOKENS_RECOVERIES.value,
                            },
                        }
                        return

                stop_result = self._execute_stop_hooks()
                if stop_result.get("prevent_continuation"):
                    yield {
                        "type": "exit",
                        "data": {"reason": QueryExitReason.STOP_HOOK_PREVENTED.value},
                    }
                    return
                if stop_result.get("blocking_errors"):
                    needs_follow_up = True

            if not needs_follow_up:
                yield {
                    "type": "exit",
                    "data": {"reason": QueryExitReason.COMPLETED.value},
                }
                return

            self.state.turn_count += 1

        yield {
            "type": "exit",
            "data": {
                "reason": QueryExitReason.MAX_TURNS.value,
                "turn_count": self.state.turn_count,
            },
        }

    def _handle_tool_update(self, update_msg: Any) -> Generator[dict[str, Any], None, None]:
        msg_type = (
            update_msg.get("type")
            if isinstance(update_msg, dict)
            else getattr(update_msg, "type", None)
        )

        if msg_type == "user":
            msg_inner = (
                update_msg.get("message")
                if isinstance(update_msg, dict)
                else getattr(update_msg, "message", None)
            )

            if msg_inner is not None:
                inner_content = (
                    msg_inner.get("content")
                    if isinstance(msg_inner, dict)
                    else getattr(msg_inner, "content", None)
                )
                if inner_content is not None:
                    user_result_msg: dict[str, Any] = {
                        "type": "user",
                        "uuid": str(uuid.uuid4()),
                        "message": {
                            "role": "user",
                            "content": inner_content,
                        },
                        "timestamp": time.strftime(
                            "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                        ),
                    }
                    self.state.messages.append(user_result_msg)

                    if isinstance(inner_content, list):
                        for result_block in inner_content:
                            yield {
                                "type": "tool_result",
                                "data": result_block,
                            }
                    elif isinstance(inner_content, dict):
                        yield {
                            "type": "tool_result",
                            "data": inner_content,
                        }

    async def _call_model(self) -> AsyncGenerator[dict[str, Any], None]:
        if not self.config.provider:
            yield {"type": "error", "data": {"message": "No provider configured"}}
            return

        messages_for_api = self._build_messages_for_api()
        tool_schemas = self._build_tool_schemas()
        max_tokens = (
            self.state.max_output_tokens_override
            or getattr(self.config.provider.config, "max_tokens", 4096)
        )
        self.config.provider.config.max_tokens = max_tokens

        async for event in self.config.provider.stream_chat(
            messages=messages_for_api,
            system_prompt=self._system_prompt,
            tools=tool_schemas,
        ):
            yield {"type": event.type, "data": event.data}

    def _build_messages_for_api(self) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []
        start_idx = self.state._compact_boundary_index
        for msg in self.state.messages[start_idx:]:
            if msg.get("is_meta"):
                continue
            if msg.get("is_virtual"):
                continue
            msg_type = msg.get("type", "")
            if msg_type in ("user", "assistant"):
                api_messages.append(self._normalize_api_message(msg))
        return self._merge_consecutive_user_messages(api_messages)

    @staticmethod
    def _merge_consecutive_user_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("type") == "user" and result and result[-1].get("type") == "user":
                prev = result[-1]
                prev_content = prev.get("message", prev).get("content", [])
                cur_content = msg.get("message", msg).get("content", [])
                if isinstance(prev_content, list) and isinstance(cur_content, list):
                    merged_content = prev_content + cur_content
                elif isinstance(prev_content, list):
                    merged_content = prev_content + [cur_content]
                elif isinstance(cur_content, list):
                    merged_content = [prev_content] + cur_content
                else:
                    merged_content = [prev_content, cur_content]
                prev_msg_data = prev.get("message", prev)
                prev["message"] = {**prev_msg_data, "content": merged_content}
            else:
                result.append(msg)
        return result

    @staticmethod
    def _normalize_api_message(msg: dict[str, Any]) -> dict[str, Any]:
        msg_data = msg.get("message", msg)
        content = msg_data.get("content", [])
        if not isinstance(content, list):
            return msg
        cleaned: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type in ("text", "tool_use", "tool_result", "thinking"):
                cleaned.append(block)
        if not cleaned:
            cleaned.append({"type": "text", "text": ""})
        result = dict(msg)
        result["message"] = {
            **msg_data,
            "content": cleaned,
        }
        return result

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for tool in self._tools:
            schema: dict[str, Any] = {
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "search_hint", "") or "",
            }
            input_schema = getattr(tool, "input_schema", None)
            if input_schema:
                try:
                    if hasattr(input_schema, "model_json_schema"):
                        schema["input_schema"] = input_schema.model_json_schema()
                    else:
                        schema["input_schema"] = None
                except Exception:
                    schema["input_schema"] = None
            schemas.append(schema)
        return schemas

    def _has_tool_use(self, msg: dict[str, Any]) -> bool:
        msg_data = msg.get("message", msg)
        content = msg_data.get("content", [])
        if isinstance(content, list):
            return any(
                block.get("type") == "tool_use"
                for block in content
                if isinstance(block, dict)
            )
        return False

    @staticmethod
    def _extract_tool_blocks(msg: dict[str, Any]) -> list[dict[str, Any]]:
        msg_data = msg.get("message", msg)
        content = msg_data.get("content", [])
        if not isinstance(content, list):
            return []
        return [
            b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
        ]

    @staticmethod
    def _is_max_output_tokens_from_msgs(assistant_msgs: list[dict[str, Any]]) -> bool:
        for msg in assistant_msgs:
            msg_data = msg.get("message", msg)
            stop_reason = msg_data.get("stop_reason", "")
            if stop_reason in ("max_tokens", "length"):
                return True
        return False

    def _handle_max_output_tokens_recovery(self) -> bool:
        if self.state.max_output_tokens_recovery_count >= MAX_OUTPUT_TOKENS_RECOVERY_LIMIT:
            return False

        if (
            self.state.max_output_tokens_override is None
            and self.state.max_output_tokens_recovery_count == 0
        ):
            self.state.max_output_tokens_override = ESCALATED_MAX_TOKENS
            self.state.max_output_tokens_recovery_count = 1
            return True

        self.state.max_output_tokens_recovery_count += 1
        recovery_msg: dict[str, Any] = {
            "type": "user",
            "uuid": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "content": (
                    "Output token limit hit. Resume directly — no apology, "
                    "no recap of what you were doing. Pick up mid-thought if "
                    "that is where the cut happened. Break remaining work "
                    "into smaller pieces."
                ),
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "is_meta": True,
        }
        self.state.messages.append(recovery_msg)
        return True

    def _yield_missing_tool_results(
        self,
        assistant_msgs: list[dict[str, Any]],
        error_message: str,
        _executor: Any,
    ) -> Generator[dict[str, Any], None, None]:
        for assistant_msg in assistant_msgs:
            tool_blocks = self._extract_tool_blocks(assistant_msg)
            for tb in tool_blocks:
                error_block = _make_tool_result_block(
                    tb.get("id", ""), error_message, is_error=True
                )
                user_result_msg: dict[str, Any] = {
                    "type": "user",
                    "uuid": str(uuid.uuid4()),
                    "message": {
                        "role": "user",
                        "content": [error_block],
                    },
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                }
                self.state.messages.append(user_result_msg)
                yield {
                    "type": "tool_result",
                    "data": error_block,
                }

    def _execute_post_sampling_hooks(self, assistant_msgs: list[dict[str, Any]]) -> None:
        for hook in self._hooks:
            with contextlib.suppress(Exception):
                hook("post_sampling", {"assistant_msgs": assistant_msgs})

    def _execute_stop_hooks(self) -> dict[str, Any]:
        result: dict[str, Any] = {"prevent_continuation": False, "blocking_errors": []}
        for hook in self._hooks:
            with contextlib.suppress(Exception):
                hook_result = hook("stop", {"turn_count": self.state.turn_count})
                if isinstance(hook_result, dict):
                    if hook_result.get("prevent_continuation"):
                        result["prevent_continuation"] = True
                    blocking = hook_result.get("blocking_errors")
                    if blocking:
                        result["blocking_errors"].extend(
                            blocking if isinstance(blocking, list) else [blocking]
                        )
        return result

    @staticmethod
    def _parse_tool_input(raw_input: Any) -> dict[str, Any]:
        if isinstance(raw_input, dict):
            return raw_input
        if isinstance(raw_input, str):
            try:
                return json.loads(raw_input)
            except json.JSONDecodeError:
                return {}
        return {}

    def _check_auto_compact(self) -> str | None:
        if not self.config.is_auto_compact_enabled:
            return None

        estimated_tokens = self._compute_estimated_tokens()

        if estimated_tokens < AUTO_COMPACT_TOKEN_THRESHOLD:
            return None

        snip_result = self._try_snip_compact()
        mc_result = self._try_microcompact()
        tokens_freed = snip_result + mc_result
        if tokens_freed > 0:
            self.state._compact_boundary_index = max(0, len(self.state.messages) - 20)

        new_estimate = self._compute_estimated_tokens()
        if new_estimate >= AUTO_COMPACT_TOKEN_THRESHOLD:
            return QueryExitReason.BLOCKING_LIMIT.value

        return None

    def _try_snip_compact(self) -> int:
        msgs = self.state.messages
        if len(msgs) <= 30:
            return 0
        keep_turns = 20
        removed = 0
        for i in range(len(msgs) - keep_turns):
            if msgs[i].get("type") in ("user", "assistant"):
                msgs[i] = {**msgs[i], "_snipped": True}
                removed += 1
        return removed

    def _try_microcompact(self) -> int:
        try:
            from server.services.compact import microcompact_messages
            result = microcompact_messages(self.state.messages)
            tokens_saved = result.get("tokens_saved", 0)
            return int(tokens_saved)
        except Exception:
            return 0

    def _compute_estimated_tokens(self) -> int:
        usage = self.state.total_usage
        api_estimate = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        if api_estimate > 0:
            return api_estimate

        total_chars = 0
        for msg in self.state.messages:
            msg_data = msg.get("message", msg)
            content = msg_data.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                total_chars += sum(
                    len(str(block.get("text", block.get("content", ""))))
                    for block in content
                    if isinstance(block, dict)
                )
        return max(1, int(total_chars * 0.25))

    def _check_token_budget_on_state(self) -> bool:
        usage = self.state.total_usage
        return self._check_token_budget(usage)

    def _check_token_budget(self, usage: dict[str, Any]) -> bool:
        total_context = usage.get("input_tokens", 0)
        max_context = 200_000

        if total_context >= max_context * TOKEN_BUDGET_RATIO:
            output_tokens = usage.get("output_tokens", 0)
            if output_tokens < DIMINISHING_RETURNS_DELTA_THRESHOLD:
                self.state.consecutive_low_output_count += 1
            else:
                self.state.consecutive_low_output_count = 0

            if self.state.consecutive_low_output_count >= DIMINISHING_RETURNS_CONSECUTIVE:
                return True

        return False

    def interrupt(self) -> None:
        self._abort.set()

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self.state.messages)

    def get_total_usage(self) -> dict[str, int]:
        return dict(self.state.total_usage)

    def _update_usage(self, usage: dict[str, Any]) -> None:
        if usage.get("input_tokens"):
            self.state.total_usage["input_tokens"] += usage["input_tokens"]
        if usage.get("output_tokens"):
            self.state.total_usage["output_tokens"] += usage["output_tokens"]
        if usage.get("cache_creation_input_tokens"):
            self.state.total_usage["cache_creation_input_tokens"] += usage[
                "cache_creation_input_tokens"
            ]
        if usage.get("cache_read_input_tokens"):
            self.state.total_usage["cache_read_input_tokens"] += usage["cache_read_input_tokens"]

    def _update_usage_from_msg(self, msg: dict[str, Any]) -> None:
        msg_data = msg.get("message", msg)
        usage = msg_data.get("usage", {})
        if usage:
            self._update_usage(usage)


def _make_tool_result_block(
    tool_use_id: str, content: str, is_error: bool = False
) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }


def _make_user_message_dict(
    content: list[dict[str, Any]], tool_use_result: str, source_uuid: str
) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {"type": "user", "content": content},
        "tool_use_result": tool_use_result,
        "source_tool_assistant_uuid": source_uuid,
    }


def _make_interruption_message() -> dict[str, Any]:
    return {
        "type": "user",
        "uuid": str(uuid.uuid4()),
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Interrupted by user"}],
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "is_meta": True,
    }

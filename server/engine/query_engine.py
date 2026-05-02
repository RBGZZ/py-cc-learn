from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from server.services.provider import Provider, StreamEvent
from server.state.session import SessionStorage


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

        assistant_blocks: list[dict[str, Any]] = []
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
                stop_reason = event.get("data", {}).get("reason", QueryExitReason.COMPLETED.value)
                break

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
                yield {"type": "exit", "data": {"reason": QueryExitReason.ABORTED_STREAMING.value}}
                return

            if self.state.turn_count > 0:
                compact_result = self._check_auto_compact()
                if compact_result:
                    yield {"type": "exit", "data": {"reason": compact_result}}
                    return

            try:
                async for event in self._call_model():
                    event_type = event.get("type", "")

                    if event_type in ("assistant", "stream_event", "text_delta", "error"):
                        yield event

                    if event_type == "assistant":
                        msg = event.get("data", event)
                        if self._has_tool_use(msg):
                            async for tool_event in self._execute_tools(msg):
                                yield tool_event
                        else:
                            yield {
                                "type": "exit",
                                "data": {"reason": QueryExitReason.COMPLETED.value},
                            }
                            return

                    if event_type == "error":
                        yield {
                            "type": "exit",
                            "data": {"reason": QueryExitReason.MODEL_ERROR.value},
                        }
                        return

            except asyncio.CancelledError:
                yield {"type": "exit", "data": {"reason": QueryExitReason.CANCELLED_BY_USER.value}}
                return
            except Exception:
                yield {"type": "error", "data": {"message": "Model invocation failed"}}
                yield {"type": "exit", "data": {"reason": QueryExitReason.MODEL_ERROR.value}}
                return

            self.state.turn_count += 1

        yield {
            "type": "exit",
            "data": {
                "reason": QueryExitReason.MAX_TURNS.value,
                "turn_count": self.state.turn_count,
            },
        }

    async def _call_model(self) -> AsyncGenerator[dict[str, Any], None]:
        if not self.config.provider:
            yield {"type": "error", "data": {"message": "No provider configured"}}
            return

        messages_for_api = self._build_messages_for_api()
        tool_schemas = self._build_tool_schemas()

        async for event in self.config.provider.stream_chat(
            messages=messages_for_api,
            system_prompt=self._system_prompt,
            tools=tool_schemas,
        ):
            yield {"type": event.type, "data": event.data}

    def _build_messages_for_api(self) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []
        for msg in self.state.messages:
            msg_type = msg.get("type", "")
            if msg_type in ("user", "assistant"):
                api_messages.append(msg)
        return api_messages

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
                block.get("type") == "tool_use" for block in content if isinstance(block, dict)
            )
        return False

    async def _execute_tools(
        self, assistant_msg: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        msg_data = assistant_msg.get("message", assistant_msg)
        content = msg_data.get("content", [])

        tool_blocks = [
            block
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]

        for block in tool_blocks:
            tool_name = block.get("name", "")
            tool_input: dict[str, Any] = block.get("input", {})
            if isinstance(tool_input, str):
                import json

                try:
                    tool_input = json.loads(tool_input)
                except json.JSONDecodeError:
                    tool_input = {}

            tool = self._tool_map.get(tool_name)
            if tool is None:
                yield {
                    "type": "tool_result",
                    "data": {
                        "tool_use_id": block.get("id", ""),
                        "content": f"Tool '{tool_name}' not found",
                        "is_error": True,
                    },
                }
                continue

            try:
                result = await tool.call(tool_input, None)
                result_block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": block.get("id", ""),
                    "content": str(result) if not isinstance(result, dict) else result,
                    "is_error": False,
                }
                user_result_msg: dict[str, Any] = {
                    "type": "user",
                    "uuid": str(uuid.uuid4()),
                    "message": {"role": "user", "content": [result_block]},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                }
                self.state.messages.append(user_result_msg)
                yield {"type": "tool_result", "data": result_block}

            except Exception as exc:
                error_block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": block.get("id", ""),
                    "content": str(exc),
                    "is_error": True,
                }
                user_error_msg: dict[str, Any] = {
                    "type": "user",
                    "uuid": str(uuid.uuid4()),
                    "message": {"role": "user", "content": [error_block]},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                }
                self.state.messages.append(user_error_msg)
                yield {"type": "tool_result", "data": error_block}

    def _check_auto_compact(self) -> str | None:
        estimated_tokens = self._compute_estimated_tokens()

        if estimated_tokens >= AUTO_COMPACT_TOKEN_THRESHOLD:
            return QueryExitReason.BLOCKING_LIMIT.value

        return None

    def _compute_estimated_tokens(self) -> int:
        estimated_tokens = sum(
            len(str(msg.get("message", msg.get("content", "")))) for msg in self.state.messages
        )
        return int(estimated_tokens / 4)

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

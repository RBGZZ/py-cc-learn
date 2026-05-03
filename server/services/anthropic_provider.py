from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from server.services.errors import (
    CannotRetryError,
    classify_api_error,
)
from server.services.provider import (
    ExtendedThinkingConfig,
    Provider,
    ProviderConfig,
    ProviderType,
    StreamEvent,
)
from server.services.retry import (
    CannotRetryError as RetryCannotRetryError,
)
from server.services.retry import (
    FallbackTriggeredError,
    RetryConfig,
    with_retry,
)

EMPTY_USAGE: dict[str, int] = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
}

MAX_NON_STREAMING_TOKENS = 64_000


def _safe_parse_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize_usage(usage: dict[str, Any] | None) -> dict[str, int]:
    if not usage:
        return dict(EMPTY_USAGE)
    return {
        "input_tokens": usage.get("input_tokens", 0) or 0,
        "output_tokens": usage.get("output_tokens", 0) or 0,
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0) or 0,
    }


def _update_usage(existing: dict[str, int], new: dict[str, Any] | None) -> dict[str, int]:
    if not new:
        return dict(existing)
    result = dict(existing)
    if new.get("input_tokens"):
        result["input_tokens"] = new["input_tokens"]
    if new.get("cache_creation_input_tokens"):
        result["cache_creation_input_tokens"] = new["cache_creation_input_tokens"]
    if new.get("cache_read_input_tokens"):
        result["cache_read_input_tokens"] = new["cache_read_input_tokens"]
    if new.get("output_tokens") is not None:
        result["output_tokens"] = new["output_tokens"]
    return result


def _get_anthropic_error_from_response(status_code: int, body: dict[str, Any]) -> Exception:
    error_msg = ""
    if "error" in body:
        error_msg = body["error"].get("message", "")
    elif "message" in body:
        error_msg = body["message"]
    else:
        error_msg = str(body)

    class AnthropicAPIError(Exception):
        def __init__(self, message: str, status: int, headers: dict | None = None):
            super().__init__(message)
            self.status_code = status
            self.status = status
            self.headers = headers or {}

    return AnthropicAPIError(error_msg, status_code)


class AnthropicProvider(Provider):
    _ANTHROPIC_VERSION = "2023-06-01"
    _MAX_MEDIA_PER_REQUEST = 100

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.name = ProviderType.ANTHROPIC.value
        if not config.base_url:
            self.config.base_url = "https://api.anthropic.com"
        if not config.model:
            self.config.model = "claude-sonnet-4-20250514"

    def supports_thinking(self) -> bool:
        return True

    def get_default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        signal: Any = None,
        thinking_config: ExtendedThinkingConfig | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        normalized_messages = self._normalize_messages_for_api(messages)
        api_messages = self._convert_messages(normalized_messages)

        if os.environ.get("CLAUDE_CODE_PROMPT_CACHING_ENABLED", "").lower() in ("1", "true"):
            for i in range(len(api_messages) - 2):
                msg = api_messages[i]
                content = msg.get("content", [])
                if isinstance(content, list) and content:
                    last_block = content[-1]
                    if isinstance(last_block, dict) and "cache_control" not in last_block:
                        last_block = {**last_block, "cache_control": {"type": "ephemeral"}}
                        content[-1] = last_block

        system_blocks: list[dict[str, Any]] = []
        if system_prompt:
            caching = os.environ.get(
                "CLAUDE_CODE_PROMPT_CACHING_ENABLED", ""
            ).lower() in ("1", "true")
            if caching:
                system_blocks = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                system_blocks = [{"type": "text", "text": system_prompt}]

        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": True,
        }
        if system_blocks:
            body["system"] = system_blocks
        if tools:
            body["tools"] = tools

        if os.environ.get("EXTENDED_THINKING_ENABLED", "").lower() not in ("1", "true"):
            thinking_config = None
        if thinking_config and thinking_config.type == "enabled":
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_config.budget_tokens,
            }

        betas = []
        if os.environ.get("CLAUDE_CODE_PROMPT_CACHING_ENABLED", "").lower() in ("1", "true"):
            betas.append("prompt-caching-2024-07-31")
        if self.config.betas:
            betas.extend(self.config.betas)

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self._ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        if betas:
            headers["anthropic-beta"] = ",".join(betas)

        retry_config = RetryConfig(
            max_retries=self.config.max_retries,
            model=self.config.model,
            fallback_model=self.config.fallback_model,
            signal=signal,
        )

        async def _attempt(attempt: int) -> Any:
            if self._http_client is not None:
                client = self._http_client
                response = await client.post(
                    f"{self.config.base_url}/v1/messages",
                    json=body,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(600.0),
                    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
                ) as client:
                    response = await client.post(
                        f"{self.config.base_url}/v1/messages",
                        json=body,
                        headers=headers,
                    )
            if response.status_code != 200:
                raise _get_anthropic_error_from_response(
                    response.status_code,
                    response.json() if response.text else {},
                )
            return response

        try:
            response = await with_retry(_attempt, retry_config)
        except FallbackTriggeredError:
            raise
        except CannotRetryError as e:
            yield StreamEvent(
                type="error",
                data={"message": str(e), "error_type": classify_api_error(e)},
            )
            return
        except RetryCannotRetryError as e:
            yield StreamEvent(
                type="error",
                data={"message": str(e), "error_type": classify_api_error(e.original_error)},
            )
            return

        async for event in self._process_sse_stream(response):
            yield event

    async def _process_sse_stream(
        self, response: httpx.Response
    ) -> AsyncGenerator[StreamEvent, None]:
        partial_message: dict[str, Any] | None = None
        content_blocks: list[dict[str, Any]] = []
        usage: dict[str, int] = dict(EMPTY_USAGE)
        stop_reason: str | None = None
        ttft_ms = 0
        start = time.time()
        is_first_chunk = True

        buffer = ""
        _timeout = int(os.environ.get("SSE_IDLE_TIMEOUT_SECONDS", "120"))
        it = response.aiter_bytes().__aiter__()
        while True:
            try:
                chunk = await asyncio.wait_for(it.__anext__(), timeout=_timeout)
            except StopAsyncIteration:
                break
            except TimeoutError:
                yield StreamEvent(type="error", data={"message": "idle_timeout"})
                return
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                if not line.startswith("data: "):
                    continue
                data_str = line[6:]

                if data_str == "[DONE]":
                    yield StreamEvent(type="message_stop", data={})
                    continue

                parsed = _safe_parse_json(data_str)
                if parsed is None:
                    continue

                event_type = parsed.get("type", "")

                if is_first_chunk:
                    ttft_ms = int((time.time() - start) * 1000)
                    is_first_chunk = False

                if event_type == "message_start":
                    partial_message = parsed.get("message", {})
                    usage = _normalize_usage(partial_message.get("usage"))
                    yield StreamEvent(
                        type="stream_event",
                        data={"event": parsed, "event_type": "message_start", "ttft_ms": ttft_ms},
                    )

                elif event_type == "content_block_start":
                    content_block = parsed.get("content_block", {})
                    index = parsed.get("index", len(content_blocks))
                    block_type = content_block.get("type", "")

                    if block_type == "tool_use":
                        content_block = dict(content_block)
                        content_block["input"] = ""
                    elif block_type == "text":
                        content_block = dict(content_block)
                        content_block["text"] = ""
                    elif block_type == "thinking":
                        thinking_block: dict[str, Any] = dict(content_block)
                        thinking_block["thinking"] = ""
                        thinking_block["signature"] = ""
                        content_block = thinking_block
                    else:
                        content_block = dict(content_block)

                    while len(content_blocks) <= index:
                        content_blocks.append({})
                    content_blocks[index] = content_block

                    yield StreamEvent(
                        type="stream_event",
                        data={"event": parsed, "event_type": "content_block_start"},
                    )

                    if block_type == "thinking":
                        yield StreamEvent(
                            type="thinking_delta",
                            data={"thinking": "", "signature": ""},
                        )

                elif event_type == "content_block_delta":
                    delta = parsed.get("delta", {})
                    index = parsed.get("index", 0)
                    delta_type = delta.get("type", "")

                    if index < len(content_blocks):
                        block = content_blocks[index]

                        if delta_type == "input_json_delta":
                            if block.get("type") in ("tool_use", "server_tool_use"):
                                block["input"] = block.get("input", "") + delta.get(
                                    "partial_json", ""
                                )
                        elif delta_type == "text_delta":
                            if block.get("type") == "text":
                                block["text"] = block.get("text", "") + delta.get("text", "")
                        elif delta_type == "thinking_delta":
                            if block.get("type") == "thinking":
                                block["thinking"] = block.get("thinking", "") + delta.get(
                                    "thinking", ""
                                )
                                yield StreamEvent(
                                    type="thinking_delta",
                                    data={"thinking": delta.get("thinking", "")},
                                )
                        elif (
                            delta_type == "signature_delta"
                            and block.get("type") == "thinking"
                        ):
                            block["signature"] = delta.get("signature", "")

                    yield StreamEvent(
                        type="stream_event",
                        data={"event": parsed, "event_type": "content_block_delta"},
                    )

                elif event_type == "content_block_stop":
                    index = parsed.get("index", 0)
                    if index < len(content_blocks) and partial_message:
                        block = content_blocks[index]
                        normalized_content = self._normalize_content_block(block)
                        assistant_message: dict[str, Any] = {
                            "message": {
                                "role": "assistant",
                                "content": [normalized_content],
                                "model": partial_message.get("model", self.config.model),
                                "stop_reason": stop_reason,
                                "usage": usage,
                            },
                            "type": "assistant",
                            "uuid": str(uuid.uuid4()),
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                        }
                        yield StreamEvent(
                            type="assistant",
                            data=assistant_message,
                        )

                        if block.get("type") == "thinking":
                            yield StreamEvent(
                                type="thinking_delta",
                                data={
                                    "thinking": block.get("thinking", ""),
                                    "signature": block.get("signature", ""),
                                },
                            )

                elif event_type == "message_delta":
                    delta = parsed.get("delta", {})
                    usage = _update_usage(usage, parsed.get("usage"))
                    stop_reason = delta.get("stop_reason")
                    yield StreamEvent(
                        type="stream_event",
                        data={
                            "event": parsed,
                            "event_type": "message_delta",
                            "stop_reason": stop_reason,
                            "usage": usage,
                        },
                    )

                elif event_type == "message_stop":
                    yield StreamEvent(
                        type="stream_event",
                        data={"event": parsed, "event_type": "message_stop"},
                    )

                elif event_type == "ping":
                    yield StreamEvent(
                        type="stream_event",
                        data={"event": parsed, "event_type": "ping"},
                    )

                elif event_type == "error":
                    error_data = parsed.get("error", {})
                    yield StreamEvent(
                        type="error",
                        data={
                            "message": error_data.get("message", "Unknown API error"),
                            "error_type": error_data.get("type", "unknown"),
                        },
                    )
                    return

    def _normalize_content_block(self, block: dict[str, Any]) -> dict[str, Any]:
        block_type = block.get("type", "")
        result = {"type": block_type}

        if block_type == "text":
            result["text"] = block.get("text", "")
        elif block_type in ("tool_use", "server_tool_use"):
            result["id"] = block.get("id", "")
            result["name"] = block.get("name", "")
            raw_input = block.get("input", "")
            if isinstance(raw_input, str) and raw_input:
                try:
                    result["input"] = json.loads(raw_input)
                except json.JSONDecodeError:
                    result["input"] = {}
            else:
                result["input"] = raw_input if raw_input else {}
        elif block_type == "thinking":
            result["thinking"] = block.get("thinking", "")
            result["signature"] = block.get("signature", "")
        else:
            result.update({k: v for k, v in block.items() if k != "type"})

        return result

    def _normalize_messages_for_api(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            msg_type = msg.get("type", "")
            if msg_type in ("user", "assistant"):
                result.append(msg)
        return result

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []
        for msg in messages:
            msg_type = msg.get("type", "")
            content = msg.get("message", {}).get("content", msg.get("content", ""))

            if msg_type == "user":
                if isinstance(content, str):
                    api_messages.append(
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": content}],
                        }
                    )
                elif isinstance(content, list):
                    api_messages.append({"role": "user", "content": content})
            elif msg_type == "assistant":
                if isinstance(content, str):
                    api_messages.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": content}],
                        }
                    )
                elif isinstance(content, list):
                    api_messages.append({"role": "assistant", "content": content})

        return api_messages

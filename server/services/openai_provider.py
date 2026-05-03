from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from server.services.errors import CannotRetryError, classify_api_error
from server.services.provider import (
    Provider,
    ProviderConfig,
    ProviderType,
    StreamEvent,
)
from server.services.retry import (
    RetryConfig,
    with_retry,
)


class OpenAIProvider(Provider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.name = ProviderType.OPENAI.value
        if not config.base_url:
            self.config.base_url = "https://api.openai.com"
        if not config.model:
            self.config.model = "gpt-4o"
        # Cap max_tokens to reasonable default; OpenAI completion_tokens is output only
        if config.max_tokens == 4096:
            self.config.max_tokens = 4096  # Keep configured value
        elif config.max_tokens > 16000:
            self.config.max_tokens = 16000  # Cap for OpenAI compatibility

    def supports_thinking(self) -> bool:
        return False

    def get_default_model(self) -> str:
        return "gpt-4o"

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        signal: Any = None,
        thinking_config=None,
    ) -> AsyncGenerator[StreamEvent, None]:
        api_messages = self._convert_messages(messages, system_prompt)

        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            body["tools"] = self._convert_tools(tools)

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

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
                    f"{self.config.base_url}/v1/chat/completions",
                    json=body,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(600.0),
                    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
                ) as client:
                    response = await client.post(
                        f"{self.config.base_url}/v1/chat/completions",
                        json=body,
                        headers=headers,
                    )
            if response.status_code != 200:
                error_msg = response.text
                try:
                    error_body = response.json()
                    error_msg = error_body.get("error", {}).get("message", error_msg)
                except Exception:
                    pass

                class OpenAIAPIError(Exception):
                    def __init__(self, message: str, status: int):
                        super().__init__(message)
                        self.status_code = status
                        self.status = status

                raise OpenAIAPIError(error_msg, response.status_code)
            return response

        try:
            response = await with_retry(_attempt, retry_config)
        except CannotRetryError as e:
            yield StreamEvent(
                type="error",
                data={"message": str(e), "error_type": classify_api_error(e)},
            )
            return

        async for event in self._process_sse_stream(response):
            yield event

    def _convert_messages(
        self, messages: list[dict[str, Any]], system_prompt: str | None
    ) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []

        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            msg_type = msg.get("type", "")
            msg_data = msg.get("message", msg)
            content = msg_data.get("content", msg.get("content", ""))

            if msg_type == "user":
                api_messages.append(self._convert_user_message(content))
            elif msg_type == "assistant":
                api_messages.append(self._convert_assistant_message(content))

        return api_messages

    def _convert_user_message(self, content: Any) -> dict[str, Any]:
        if isinstance(content, str):
            return {"role": "user", "content": content}

        if isinstance(content, list):
            text_parts: list[str] = []
            image_parts: list[dict[str, Any]] = []

            for block in content:
                block_type = block.get("type", "")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "image":
                    source = block.get("source", {})
                    image_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
                            },
                        }
                    )
                elif block_type == "tool_result":
                    text_parts.append(f"[Tool Result: {json.dumps(block.get('content', ''))}]")

            user_content: list[dict[str, Any]] = []
            if text_parts:
                combined = "\n".join(text_parts)
                user_content.append({"type": "text", "text": combined})
            user_content.extend(image_parts)

            if not user_content:
                user_content.append({"type": "text", "text": ""})

            return {"role": "user", "content": user_content}

        return {"role": "user", "content": str(content)}

    def _convert_assistant_message(self, content: Any) -> dict[str, Any]:
        if isinstance(content, str):
            return {"role": "assistant", "content": content}

        if isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []

            for block in content:
                block_type = block.get("type", "")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "thinking":
                    text_parts.append(f"[Thinking: {block.get('thinking', '')}]")
                elif block_type == "tool_use":
                    tool_input = block.get("input", {})
                    if isinstance(tool_input, dict):
                        tool_input_str = json.dumps(tool_input)
                    else:
                        tool_input_str = str(tool_input)

                    tool_calls.append(
                        {
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": tool_input_str,
                            },
                        }
                    )

            result: dict[str, Any] = {"role": "assistant"}
            if text_parts:
                result["content"] = "\n".join(text_parts)
            if tool_calls:
                result["tool_calls"] = tool_calls

            return result

        return {"role": "assistant", "content": str(content)}

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        openai_tools: list[dict[str, Any]] = []
        for tool in tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            openai_tools.append(openai_tool)
        return openai_tools

    async def _process_sse_stream(
        self, response: httpx.Response
    ) -> AsyncGenerator[StreamEvent, None]:
        content_buffer = ""
        tool_call_buffers: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage: dict[str, int] = {}

        buffer = ""
        async for chunk in response.aiter_bytes():
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    yield StreamEvent(type="message_stop", data={})
                    continue

                parsed = json.loads(data_str)
                choices = parsed.get("choices", [])

                for choice in choices:
                    delta = choice.get("delta", {})

                    if "content" in delta and delta["content"]:
                        content_buffer += delta["content"]
                        yield StreamEvent(
                            type="text_delta",
                            data={"text": delta["content"]},
                        )

                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": "",
                                }
                            if "function" in tc:
                                func = tc["function"]
                                if "name" in func:
                                    tool_call_buffers[idx]["name"] = func["name"]
                                if "arguments" in func:
                                    tool_call_buffers[idx]["arguments"] += func["arguments"]

                    finish_reason = choice.get("finish_reason")

                if "usage" in parsed and parsed["usage"]:
                    usage = {
                        "input_tokens": parsed["usage"].get("prompt_tokens", 0),
                        "output_tokens": parsed["usage"].get("completion_tokens", 0),
                    }

        content_list: list[dict[str, Any]] = []
        if content_buffer:
            content_list.append({"type": "text", "text": content_buffer})

        tool_results: list[dict[str, Any]] = []
        for idx in sorted(tool_call_buffers.keys()):
            tb = tool_call_buffers[idx]
            try:
                args = json.loads(tb["arguments"]) if tb["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            tool_results.append(
                {
                    "type": "tool_use",
                    "id": tb["id"],
                    "name": tb["name"],
                    "input": args,
                }
            )

        content_list.extend(tool_results)

        # Yield individual tool_use events for compatibility with event-based consumers
        for tr in tool_results:
            yield StreamEvent(type="tool_use", data=tr)

        assistant_msg = {
            "message": {
                "role": "assistant",
                "content": content_list,
                "model": self.config.model,
                "stop_reason": finish_reason,
                "usage": usage,
            },
            "type": "assistant",
        }
        yield StreamEvent(type="assistant", data=assistant_msg)

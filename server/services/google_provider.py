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


class GoogleProvider(Provider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.name = ProviderType.GOOGLE.value
        if not config.base_url:
            self.config.base_url = "https://generativelanguage.googleapis.com"
        if not config.model:
            self.config.model = "gemini-2.0-flash"

    def supports_thinking(self) -> bool:
        return False

    def get_default_model(self) -> str:
        return "gemini-2.0-flash"

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        signal: Any = None,
        thinking_config=None,
    ) -> AsyncGenerator[StreamEvent, None]:
        gemini_contents = self._convert_messages(messages)

        generation_config: dict[str, Any] = {
            "maxOutputTokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        system_instruction: dict[str, Any] | None = None
        if system_prompt:
            system_instruction = {"parts": [{"text": system_prompt}]}

        body: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": generation_config,
        }
        if system_instruction:
            body["systemInstruction"] = system_instruction
        if tools:
            body["tools"] = self._convert_tools(tools)

        url = (
            f"{self.config.base_url}/v1beta/models/"
            f"{self.config.model}:streamGenerateContent"
        )

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.config.api_key,
        }

        retry_config = RetryConfig(
            max_retries=self.config.max_retries,
            model=self.config.model,
            fallback_model=self.config.fallback_model,
            signal=signal,
        )

        async def _attempt(attempt: int) -> Any:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(600.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            ) as client:
                response = await client.post(url, json=body, headers=headers)
                if response.status_code != 200:

                    class GoogleAPIError(Exception):
                        def __init__(self, message: str, status: int):
                            super().__init__(message)
                            self.status_code = status
                            self.status = status

                    raise GoogleAPIError(response.text, response.status_code)
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

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        gemini_contents: list[dict[str, Any]] = []
        for msg in messages:
            msg_type = msg.get("type", "")
            msg_data = msg.get("message", msg)
            content = msg_data.get("content", msg.get("content", ""))

            parts: list[dict[str, Any]] = []

            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for block in content:
                    block_type = block.get("type", "")
                    if block_type == "text":
                        parts.append({"text": block.get("text", "")})
                    elif block_type == "tool_use":
                        parts.append(
                            {
                                "functionCall": {
                                    "name": block.get("name", ""),
                                    "args": block.get("input", {}),
                                }
                            }
                        )
                    elif block_type == "tool_result":
                        parts.append(
                            {
                                "functionResponse": {
                                    "name": block.get("tool_use_id", ""),
                                    "response": {"content": str(block.get("content", ""))},
                                }
                            }
                        )

            if msg_type == "user":
                gemini_contents.append({"role": "user", "parts": parts})
            elif msg_type == "assistant":
                gemini_contents.append({"role": "model", "parts": parts})

        return gemini_contents

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        function_declarations: list[dict[str, Any]] = []
        for tool in tools:
            func_decl: dict[str, Any] = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
            }
            input_schema = tool.get("input_schema", {})
            if input_schema:
                func_decl["parameters"] = input_schema
            function_declarations.append(func_decl)

        return [{"functionDeclarations": function_declarations}]

    async def _process_sse_stream(
        self, response: httpx.Response
    ) -> AsyncGenerator[StreamEvent, None]:
        text_buffer = ""
        tool_calls: list[dict[str, Any]] = []
        finish_reason: str | None = None
        usage: dict[str, int] = {}

        buffer = ""
        async for chunk in response.aiter_bytes():
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                if line.startswith("data: "):
                    data_str = line[6:]
                elif line.startswith("["):
                    data_str = line
                else:
                    continue

                try:
                    parsed = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                candidates = parsed.get("candidates", [])
                for candidate in candidates:
                    cand_content = candidate.get("content", {})
                    cand_parts = cand_content.get("parts", [])

                    for part in cand_parts:
                        if "text" in part:
                            text_buffer += part["text"]
                            yield StreamEvent(
                                type="text_delta",
                                data={"text": part["text"]},
                            )
                        if "functionCall" in part:
                            fc = part["functionCall"]
                            tool_calls.append(
                                {
                                    "type": "tool_use",
                                    "id": fc.get("name", ""),
                                    "name": fc.get("name", ""),
                                    "input": fc.get("args", {}),
                                }
                            )

                    finish_reason = candidate.get("finishReason")

                usage_meta = parsed.get("usageMetadata", {})
                if usage_meta:
                    usage = {
                        "input_tokens": usage_meta.get("promptTokenCount", 0),
                        "output_tokens": usage_meta.get("candidatesTokenCount", 0)
                        + usage_meta.get("thoughtsTokenCount", 0),
                    }

        content_list: list[dict[str, Any]] = []
        if text_buffer:
            content_list.append({"type": "text", "text": text_buffer})
        content_list.extend(tool_calls)

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

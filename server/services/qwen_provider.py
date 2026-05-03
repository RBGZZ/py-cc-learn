from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from server.services.openai_provider import OpenAIProvider
from server.services.provider import ProviderConfig, ProviderType, StreamEvent


class QwenProvider(OpenAIProvider):
    """Qwen provider using Alibaba DashScope OpenAI-compatible API."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.name = ProviderType.QWEN.value
        if not config.base_url:
            self.config.base_url = "https://dashscope.aliyuncs.com/compatible-mode"
        if not config.model:
            self.config.model = "qwen-plus"

    def get_default_model(self) -> str:
        return "qwen-plus"

    async def stream_chat(
        self,
        messages: list,
        system_prompt: str | None = None,
        tools: list | None = None,
        signal=None,
    ) -> AsyncGenerator[StreamEvent, None]:
        api_messages = self._convert_messages(messages, system_prompt)
        body = {
            "model": self.config.model,
            "messages": api_messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = self._convert_tools(tools)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
                response = await client.post(
                    f"{self.config.base_url}/v1/chat/completions",
                    json=body, headers=headers,
                )
                if response.status_code != 200:
                    yield StreamEvent(type="error", data={"message": f"HTTP {response.status_code}: {response.text[:200]}"})
                    return
                async for event in self._process_sse_stream(response):
                    yield event
        except Exception as exc:
            yield StreamEvent(type="error", data={"message": str(exc)})

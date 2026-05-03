from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx


class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    QWEN = "qwen"


@dataclass
class StreamEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantContent:
    content: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    stop_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    role: str = "assistant"


@dataclass
class ProviderConfig:
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 1.0
    max_retries: int = 3
    fallback_model: str | None = None
    betas: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.max_retries < 0:
            self.max_retries = 3


@dataclass
class ExtendedThinkingConfig:
    type: str = "enabled"
    budget_tokens: int = 4000


class Provider(ABC):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.name = ""
        self._http_client: httpx.AsyncClient | None = None

    def set_http_client(self, client: httpx.AsyncClient | None) -> None:
        self._http_client = client

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        signal: Any = None,
        thinking_config: ExtendedThinkingConfig | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        yield StreamEvent(type="error", data={"message": "Not implemented"})

    @abstractmethod
    def supports_thinking(self) -> bool:
        return False

    @abstractmethod
    def get_default_model(self) -> str:
        return ""

    async def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        return 0

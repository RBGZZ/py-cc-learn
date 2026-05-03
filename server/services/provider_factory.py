from __future__ import annotations

import asyncio
import contextlib
import os

import httpx

from server.services.anthropic_provider import AnthropicProvider
from server.services.deepseek_provider import DeepSeekProvider
from server.services.google_provider import GoogleProvider
from server.services.openai_provider import OpenAIProvider
from server.services.provider import (
    Provider,
    ProviderConfig,
    ProviderType,
)
from server.services.qwen_provider import QwenProvider
from server.services.retry import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from server.utils.settings import Settings, get_settings


class ProviderFactory:
    _instances: dict[str, Provider] = {}
    _circuit_breakers: dict[str, CircuitBreaker] = {}
    _http_client: httpx.AsyncClient | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def _get_http_client(cls) -> httpx.AsyncClient:
        if cls._http_client is None:
            async with cls._lock:
                if cls._http_client is None:
                    cls._http_client = httpx.AsyncClient(
                        timeout=httpx.Timeout(600.0),
                        limits=httpx.Limits(
                            max_keepalive_connections=20,
                            max_connections=100,
                            keepalive_expiry=30,
                        ),
                    )
        return cls._http_client

    @classmethod
    async def close_http_client(cls) -> None:
        if cls._http_client is not None:
            await cls._http_client.aclose()
            cls._http_client = None

    @classmethod
    def _get_circuit_breaker(cls, provider_name: str) -> CircuitBreaker:
        if provider_name not in cls._circuit_breakers:
            cls._circuit_breakers[provider_name] = CircuitBreaker(
                CircuitBreakerConfig(
                    failure_threshold=5,
                    recovery_timeout_seconds=30.0,
                )
            )
        return cls._circuit_breakers[provider_name]

    @classmethod
    def _ensure_sync_client(cls) -> httpx.AsyncClient:
        if cls._http_client is None:
            cls._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(600.0),
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
                    keepalive_expiry=30,
                ),
            )
        return cls._http_client

    @classmethod
    async def _preconnect(cls) -> None:
        client = await cls._get_http_client()
        if client is None:
            return
        try:
            base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
            await asyncio.wait_for(
                client.options(base_url + "/v1/messages"),
                timeout=5.0,
            )
        except Exception:
            pass

    @classmethod
    def get_provider(
        cls,
        provider_type: ProviderType | None = None,
        config: ProviderConfig | None = None,
    ) -> Provider:
        settings = get_settings()

        if provider_type is None:
            provider_type = cls._auto_detect_provider(settings)

        effective_config = cls._build_config(provider_type, config, settings)
        key = f"{provider_type.value}:{effective_config.model}"

        if key in cls._instances:
            return cls._instances[key]

        provider = cls._create_provider(provider_type, effective_config)
        provider.set_http_client(cls._ensure_sync_client())
        cls._instances[key] = provider
        with contextlib.suppress(RuntimeError):
            asyncio.create_task(cls._preconnect())
        return provider

    @classmethod
    def _auto_detect_provider(cls, settings: Settings) -> ProviderType:
        if settings.anthropic_api_key and settings.anthropic_api_key not in ("your_token_here", ""):
            return ProviderType.ANTHROPIC
        if settings.openai_api_key and settings.openai_api_key not in ("your_key_here", ""):
            return ProviderType.OPENAI
        if settings.deepseek_api_key and settings.deepseek_api_key not in ("your_key_here", ""):
            return ProviderType.DEEPSEEK
        if settings.qwen_api_key and settings.qwen_api_key not in ("your_qwen_key_here", ""):
            return ProviderType.QWEN
        if settings.google_api_key and settings.google_api_key not in ("your_key_here", ""):
            return ProviderType.GOOGLE
        return ProviderType.ANTHROPIC

    @classmethod
    def _build_config(
        cls,
        provider_type: ProviderType,
        override: ProviderConfig | None,
        settings: Settings,
    ) -> ProviderConfig:
        config = ProviderConfig()

        if provider_type == ProviderType.ANTHROPIC:
            config.api_key = settings.anthropic_api_key or ""
            config.base_url = settings.anthropic_base_url
            config.model = settings.anthropic_model
        elif provider_type == ProviderType.OPENAI:
            config.api_key = settings.openai_api_key or ""
            config.model = settings.openai_model
            config.base_url = "https://api.openai.com"
        elif provider_type == ProviderType.DEEPSEEK:
            config.api_key = settings.deepseek_api_key or ""
            config.model = settings.deepseek_model
            config.base_url = "https://api.deepseek.com"
        elif provider_type == ProviderType.GOOGLE:
            config.api_key = settings.google_api_key or ""
            config.model = settings.google_model
            config.base_url = "https://generativelanguage.googleapis.com"
        elif provider_type == ProviderType.QWEN:
            config.api_key = settings.qwen_api_key or ""
            config.model = settings.qwen_model or "qwen-plus"
            config.base_url = "https://dashscope.aliyuncs.com/compatible-mode"

        if override:
            if override.api_key:
                config.api_key = override.api_key
            if override.model:
                config.model = override.model
            if override.base_url:
                config.base_url = override.base_url
            if override.max_tokens:
                config.max_tokens = override.max_tokens
            if override.temperature:
                config.temperature = override.temperature
            if override.max_retries:
                config.max_retries = override.max_retries
            if override.fallback_model:
                config.fallback_model = override.fallback_model

        return config

    @classmethod
    def _create_provider(cls, provider_type: ProviderType, config: ProviderConfig) -> Provider:
        if provider_type == ProviderType.ANTHROPIC:
            return AnthropicProvider(config)
        elif provider_type == ProviderType.OPENAI:
            return OpenAIProvider(config)
        elif provider_type == ProviderType.DEEPSEEK:
            return DeepSeekProvider(config)
        elif provider_type == ProviderType.GOOGLE:
            return GoogleProvider(config)
        elif provider_type == ProviderType.QWEN:
            return QwenProvider(config)
        else:
            return AnthropicProvider(config)

    @classmethod
    def get_circuit_breaker(cls, provider_type: ProviderType) -> CircuitBreaker:
        return cls._get_circuit_breaker(provider_type.value)

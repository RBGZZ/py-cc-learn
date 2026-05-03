from __future__ import annotations

import pytest
from server.services.provider import ProviderConfig, ProviderType
from server.services.provider_factory import ProviderFactory


class TestProviderFactory:
    def test_create_qwen_provider(self):
        config = ProviderConfig(api_key="sk-test", model="qwen-plus")
        provider = ProviderFactory._create_provider(ProviderType.QWEN, config)
        assert provider.name == "qwen"
        assert provider.config.base_url == "https://dashscope.aliyuncs.com/compatible-mode"
        assert provider.get_default_model() == "qwen-plus"

    def test_circuit_breaker_is_singleton_per_type(self):
        cb1 = ProviderFactory.get_circuit_breaker(ProviderType.QWEN)
        cb2 = ProviderFactory.get_circuit_breaker(ProviderType.QWEN)
        assert cb1 is cb2

    def test_provider_type_values(self):
        assert ProviderType.QWEN.value == "qwen"
        assert ProviderType.OPENAI.value == "openai"
        assert ProviderType.DEEPSEEK.value == "deepseek"

    def test_get_provider_with_explicit_config(self):
        import os
        has_key = bool(os.environ.get("QWEN_API_KEY"))
        if has_key:
            provider = ProviderFactory.get_provider(
                provider_type=ProviderType.QWEN,
                config=ProviderConfig(api_key=os.environ["QWEN_API_KEY"], model="qwen-plus"),
            )
            assert provider.name == "qwen"
            assert "dashscope" in provider.config.base_url
        else:
            pytest.skip("QWEN_API_KEY not configured")

from __future__ import annotations

import pytest
from server.services.qwen_provider import QwenProvider
from server.services.provider import ProviderConfig, ProviderType


class TestQwenProvider:
    def test_defaults(self):
        config = ProviderConfig(api_key="test-key")
        p = QwenProvider(config)
        assert p.name == "qwen"
        assert p.config.base_url == "https://dashscope.aliyuncs.com/compatible-mode"
        assert p.config.model == "qwen-plus"
        assert p.get_default_model() == "qwen-plus"

    def test_config_override(self):
        config = ProviderConfig(model="qwen-max", api_key="k", base_url="http://custom")
        p = QwenProvider(config)
        assert p.config.base_url == "http://custom"
        assert p.config.model == "qwen-max"

    def test_environ_override(self, monkeypatch):
        monkeypatch.setenv("QWEN_API_KEY", "env-key")
        monkeypatch.setenv("QWEN_MODEL", "qwen-turbo")
        from server.utils.settings import Settings
        s = Settings()
        assert s.qwen_api_key == "env-key"
        assert s.qwen_model == "qwen-turbo"

    def test_supports_thinking(self):
        p = QwenProvider(ProviderConfig(api_key="k"))
        assert p.supports_thinking() is False

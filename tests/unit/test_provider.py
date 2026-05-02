from __future__ import annotations

import pytest

from server.services.provider import Provider, ProviderConfig, StreamEvent


class TestStreamEvent:
    def test_create(self):
        event = StreamEvent(type="text_delta", data={"text": "hello"})
        assert event.type == "text_delta"
        assert event.data["text"] == "hello"

    def test_empty_data(self):
        event = StreamEvent(type="ping", data={})
        assert event.type == "ping"


class TestProviderConfig:
    def test_config_fields(self):
        config = ProviderConfig(
            model="test-model",
            api_key="test-key",
        )
        assert config.model == "test-model"
        assert config.api_key == "test-key"

    def test_default_values(self):
        config = ProviderConfig()
        assert config.model == ""
        assert config.api_key == ""


class TestErrorHandling:
    def test_stream_event_types(self):
        valid_types = [
            "content_block_start",
            "content_block_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
            "ping",
            "error",
        ]
        for t in valid_types:
            event = StreamEvent(type=t, data={})
            assert event.type == t

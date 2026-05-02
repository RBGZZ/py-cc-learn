from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest

from server.models.messages import (
    AssistantMessage,
    ContentBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from server.services.provider import Provider, ProviderConfig, StreamEvent


class MockProvider(Provider):
    def __init__(self, responses: list[StreamEvent] | None = None):
        self.config = ProviderConfig(model="mock-model", api_key="test-key")
        self.responses: list[StreamEvent] = responses or []
        self._call_count = 0

    def get_default_model(self) -> str:
        return "mock-model"

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        for event in self.responses:
            self._call_count += 1
            yield event

    def get_call_count(self) -> int:
        return self._call_count


def mock_stream_event(
    text: str = "",
    event_type: str = "content_block_delta",
    stop_reason: str | None = None,
) -> StreamEvent:
    data: dict[str, Any] = {"type": "content_block_delta"}
    if text:
        data["delta"] = {"type": "text_delta", "text": text}
    return StreamEvent(type=event_type, data=data)


def mock_text_event(text: str) -> StreamEvent:
    return mock_stream_event(text=text, event_type="content_block_delta")


def mock_tool_use_event(tool_name: str, tool_input: dict[str, Any]) -> StreamEvent:
    return StreamEvent(
        type="content_block_start",
        data={
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": tool_name,
                "input": tool_input,
                "id": "tool_01",
            },
        },
    )


def mock_message_stop(stop_reason: str = "end_turn") -> StreamEvent:
    return StreamEvent(
        type="message_stop",
        data={"type": "message_delta", "delta": {"stop_reason": stop_reason}},
    )


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
def simple_text_provider() -> MockProvider:
    return MockProvider([
        mock_text_event("Hello, "),
        mock_text_event("world!"),
        mock_message_stop("end_turn"),
    ])


@pytest.fixture
def temp_dir() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def temp_cwd(temp_dir: str) -> str:
    old = os.getcwd()
    os.chdir(temp_dir)
    yield temp_dir
    os.chdir(old)


@pytest.fixture
def sample_dir(temp_dir: str) -> str:
    base = Path(temp_dir)
    (base / "src").mkdir(exist_ok=True)
    (base / "src" / "main.py").write_text("print('hello')\n")
    (base / "src" / "utils.py").write_text("def foo(): pass\n")
    (base / "README.md").write_text("# Sample\n")
    return temp_dir


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

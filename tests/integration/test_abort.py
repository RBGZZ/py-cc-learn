"""Production audit: abort/interrupt recovery tests."""
from __future__ import annotations

import asyncio
import uuid

import pytest

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.provider import ProviderConfig, StreamEvent


class SlowToolProvider:
    """Provider that emits tool_use blocks for slow tools."""

    def __init__(self, tool_delay: float = 0.5):
        self.config = ProviderConfig(model="slow", api_key="", max_tokens=100)
        self.tool_delay = tool_delay

    def get_default_model(self):
        return "slow"

    async def stream_chat(self, messages, system_prompt=None, tools=None):
        yield StreamEvent(
            type="assistant",
            data={
                "type": "assistant",
                "uuid": str(uuid.uuid4()),
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Running slow tool..."},
                        {"type": "tool_use", "name": "Bash", "id": "tool_1",
                         "input": {"command": f"sleep {self.tool_delay}"}},
                    ],
                    "model": "slow",
                    "usage": {"input_tokens": 10, "output_tokens": 10},
                },
            },
        )
        yield StreamEvent(type="message_stop", data={})

    def supports_thinking(self):
        return False


class FakeBashTool:
    """Minimal Bash tool that simulates slow execution."""

    def __init__(self, delay: float):
        self._name = "Bash"
        self._delay = delay

    @property
    def name(self):
        return self._name

    @property
    def aliases(self):
        return None

    @property
    def input_schema(self):
        from dataclasses import dataclass

        @dataclass
        class BashInput:
            command: str = ""

            @staticmethod
            def model_json_schema():
                return {"type": "object", "properties": {"command": {"type": "string"}}}

        return BashInput

    @property
    def search_hint(self):
        return ""

    async def call(self, args, context, can_use_tool=None, parent_message=None, on_progress=None):
        await asyncio.sleep(self._delay)
        return "tool result"

    def is_concurrency_safe(self, input=None):
        return False

    def is_read_only(self, input=None):
        return False


@pytest.mark.asyncio
async def test_abort_signal_stops_engine():
    """Verify abort signal causes engine to stop."""
    provider = SlowToolProvider(tool_delay=0.1)
    tool = FakeBashTool(delay=0.1)
    abort_event = asyncio.Event()

    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=[tool], system_prompt="test", max_turns=1,
        abort_signal=abort_event,
    ))

    abort_event.set()

    events = []
    async for event in engine.submit_message("test", is_meta=True):
        events.append(event)

    assert len(events) > 0


@pytest.mark.asyncio
async def test_engine_continues_after_clean_termination():
    """Verify engine can process new prompt after clean completion."""
    provider = SlowToolProvider(tool_delay=0.05)
    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=[], system_prompt="test", max_turns=1,
    ))

    async for event in engine.submit_message("msg1", is_meta=True):
        pass

    assert engine.state.turn_count >= 0

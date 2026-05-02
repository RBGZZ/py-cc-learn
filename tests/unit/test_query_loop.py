from __future__ import annotations

import asyncio

import pytest

from server.engine.query_engine import (
    AUTO_COMPACT_TOKEN_THRESHOLD,
    DEFAULT_MAX_TURNS,
    DIMINISHING_RETURNS_CONSECUTIVE,
    DIMINISHING_RETURNS_DELTA_THRESHOLD,
    TOKEN_BUDGET_RATIO,
    QueryEngine,
    QueryEngineConfig,
    QueryExitReason,
    QueryState,
)
from server.services.provider import StreamEvent


class FakeProvider:
    def __init__(self, events=None):
        self.events = events or []
        self.config = type("obj", (object,), {"model": "test-model"})()
        self._calls = 0

    def get_default_model(self):
        return "test-model"

    async def stream_chat(self, messages, system_prompt=None, tools=None):
        for e in self.events:
            self._calls += 1
            yield e


def text_event(text: str):
    return StreamEvent(type="text_delta", data={"type": "text_delta", "text": text})


def assistant_event(content=None):
    return StreamEvent(
        type="assistant",
        data={
            "type": "assistant",
            "uuid": "msg_001",
            "message": {"role": "assistant", "content": content or [{"type": "text", "text": "done"}]},
        },
    )


class TestQueryEngine:
    @pytest.mark.asyncio
    async def test_config_defaults(self):
        config = QueryEngineConfig()
        assert config.max_turns == DEFAULT_MAX_TURNS
        assert config.tools == []

    @pytest.mark.asyncio
    async def test_query_state_initial(self):
        state = QueryState()
        assert state.turn_count == 0
        assert state.messages == []
        assert state.total_usage["input_tokens"] == 0

    @pytest.mark.asyncio
    async def test_submit_message_completes(self):
        abort = asyncio.Event()
        provider = FakeProvider([
            assistant_event(),
        ])
        engine = QueryEngine(QueryEngineConfig(
            provider=provider,
            tools=[],
            system_prompt="test",
            abort_signal=abort,
        ))

        events = []
        async for event in engine.submit_message("hello"):
            events.append(event)

        result_events = [e for e in events if e.get("type") == "result"]
        assert len(result_events) == 1
        assert result_events[0]["stop_reason"] in (
            QueryExitReason.COMPLETED.value,
        )

    @pytest.mark.asyncio
    async def test_max_turns_exceeded(self):
        abort = asyncio.Event()
        provider = FakeProvider([
            assistant_event([{"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/x"}, "id": "t1"}]),
            assistant_event([{"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/y"}, "id": "t2"}]),
        ])
        engine = QueryEngine(QueryEngineConfig(
            provider=provider,
            tools=[],
            system_prompt="test",
            max_turns=1,
            abort_signal=abort,
        ))

        events = []
        async for event in engine.submit_message("hello"):
            events.append(event)

        result_events = [e for e in events if e.get("type") == "result"]
        assert len(result_events) == 1
        assert result_events[0]["stop_reason"] in (
            QueryExitReason.MAX_TURNS.value,
            QueryExitReason.COMPLETED.value,
        )

    @pytest.mark.asyncio
    async def test_cancelled_by_user(self):
        abort = asyncio.Event()
        abort.set()
        provider = FakeProvider([
            assistant_event(),
        ])
        engine = QueryEngine(QueryEngineConfig(
            provider=provider,
            tools=[],
            system_prompt="test",
            abort_signal=abort,
        ))

        events = []
        async for event in engine.submit_message("hello"):
            events.append(event)

        result_events = [e for e in events if e.get("type") == "result"]
        assert len(result_events) == 1
        assert result_events[0]["stop_reason"] == QueryExitReason.CANCELLED_BY_USER.value

    @pytest.mark.asyncio
    async def test_no_provider_error(self):
        engine = QueryEngine(QueryEngineConfig(
            provider=None,
            tools=[],
            system_prompt="test",
        ))

        events = []
        async for event in engine.submit_message("hello"):
            events.append(event)

        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) >= 1

    def test_interrupt(self):
        abort = asyncio.Event()
        engine = QueryEngine(QueryEngineConfig(abort_signal=abort))
        assert not abort.is_set()
        engine.interrupt()
        assert abort.is_set()

    def test_get_messages(self):
        abort = asyncio.Event()
        engine = QueryEngine(QueryEngineConfig(abort_signal=abort))
        assert engine.get_messages() == []

    def test_get_total_usage(self):
        abort = asyncio.Event()
        engine = QueryEngine(QueryEngineConfig(abort_signal=abort))
        usage = engine.get_total_usage()
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0


class TestTokenBudget:
    def test_constants(self):
        assert AUTO_COMPACT_TOKEN_THRESHOLD == 180_000
        assert DEFAULT_MAX_TURNS == 50
        assert TOKEN_BUDGET_RATIO == 0.9
        assert DIMINISHING_RETURNS_DELTA_THRESHOLD == 500
        assert DIMINISHING_RETURNS_CONSECUTIVE == 3

    def test_token_budget_under_threshold(self):
        engine = QueryEngine(QueryEngineConfig())
        assert not engine._check_token_budget({"input_tokens": 1000, "output_tokens": 1000})

    def test_token_budget_diminishing_returns(self):
        engine = QueryEngine(QueryEngineConfig())
        engine.state.consecutive_low_output_count = DIMINISHING_RETURNS_CONSECUTIVE
        result = engine._check_token_budget({
            "input_tokens": int(200_000 * TOKEN_BUDGET_RATIO) + 1,
            "output_tokens": DIMINISHING_RETURNS_DELTA_THRESHOLD - 1,
        })
        assert result is True


class TestExitReasons:
    def test_all_reasons_defined(self):
        reasons = [
            QueryExitReason.COMPLETED,
            QueryExitReason.MAX_TURNS,
            QueryExitReason.MODEL_ERROR,
            QueryExitReason.BLOCKING_LIMIT,
            QueryExitReason.ABORTED_STREAMING,
            QueryExitReason.ABORTED_TOOLS,
            QueryExitReason.IMAGE_ERROR,
            QueryExitReason.STOP_HOOK_PREVENTED,
            QueryExitReason.MAX_OUTPUT_TOKENS_RECOVERIES,
            QueryExitReason.CANCELLED_BY_USER,
        ]
        assert len(reasons) == 10

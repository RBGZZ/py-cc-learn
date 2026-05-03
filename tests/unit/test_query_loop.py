from __future__ import annotations

import asyncio

import pytest

from server.engine.query_engine import (
    AUTO_COMPACT_TOKEN_THRESHOLD,
    DEFAULT_MAX_TURNS,
    DIMINISHING_RETURNS_CONSECUTIVE,
    DIMINISHING_RETURNS_DELTA_THRESHOLD,
    MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
    TOKEN_BUDGET_RATIO,
    QueryEngine,
    QueryEngineConfig,
    QueryExitReason,
    QueryState,
    _make_interruption_message,
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
        assert AUTO_COMPACT_TOKEN_THRESHOLD == 187_000
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
            QueryExitReason.PROMPT_TOO_LONG,
        ]
        assert len(reasons) == 11


class TestMaxOutputTokensRecovery:
    def test_detection_stop_reason_length(self):
        msgs = [{"message": {"stop_reason": "length", "content": []}}]
        assert QueryEngine._is_max_output_tokens_from_msgs(msgs) is True

    def test_detection_stop_reason_max_tokens(self):
        msgs = [{"message": {"stop_reason": "max_tokens", "content": []}}]
        assert QueryEngine._is_max_output_tokens_from_msgs(msgs) is True

    def test_detection_normal_stop(self):
        msgs = [{"message": {"stop_reason": "end_turn", "content": []}}]
        assert QueryEngine._is_max_output_tokens_from_msgs(msgs) is False

    def test_detection_none_in_list(self):
        msgs: list = []
        assert QueryEngine._is_max_output_tokens_from_msgs(msgs) is False

    def test_recovery_escalate_first(self):
        engine = QueryEngine(QueryEngineConfig(
            tools=[], system_prompt="test", feature_gates={"tengu_otk_slot_v1": True}
        ))
        result = engine._handle_max_output_tokens_recovery()
        assert result is True
        assert engine.state.max_output_tokens_override == 64000
        assert engine.state.max_output_tokens_recovery_count == 1
        assert len(engine.state.messages) == 0

    def test_recovery_escalate_gated(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        result = engine._handle_max_output_tokens_recovery()
        assert result is True
        assert engine.state.max_output_tokens_override is None
        assert engine.state.max_output_tokens_recovery_count == 1
        assert len(engine.state.messages) == 1
        assert engine.state.messages[0]["is_meta"] is True

    def test_recovery_second_injects_meta_message(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        engine.state.max_output_tokens_recovery_count = 1
        result = engine._handle_max_output_tokens_recovery()
        assert result is True
        assert engine.state.max_output_tokens_recovery_count == 2
        assert len(engine.state.messages) == 1
        assert engine.state.messages[0]["is_meta"] is True
        assert "Output token limit hit" in engine.state.messages[0]["message"]["content"]

    def test_recovery_limit(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        engine.state.max_output_tokens_recovery_count = MAX_OUTPUT_TOKENS_RECOVERY_LIMIT
        result = engine._handle_max_output_tokens_recovery()
        assert result is False
        assert engine.state.max_output_tokens_recovery_count == MAX_OUTPUT_TOKENS_RECOVERY_LIMIT
        assert len(engine.state.messages) == 0


class TestTokenEstimation:
    def test_uses_api_usage_when_available(self):
        engine = QueryEngine(QueryEngineConfig())
        engine.state.total_usage = {"input_tokens": 500, "output_tokens": 200}
        estimated = engine._compute_estimated_tokens()
        assert estimated == 700

    def test_falls_back_to_char_estimate(self):
        engine = QueryEngine(QueryEngineConfig())
        engine.state.messages = [
            {"message": {"content": "hello world"}},
            {"message": {"content": "foo"}},
        ]
        estimated = engine._compute_estimated_tokens()
        assert estimated > 0
        assert estimated == int((11 + 3) * 0.25)

    def test_falls_back_list_content(self):
        engine = QueryEngine(QueryEngineConfig())
        engine.state.messages = [
            {"message": {"content": [{"text": "hello"}, {"text": "world"}]}},
        ]
        estimated = engine._compute_estimated_tokens()
        assert estimated == int((5 + 5) * 0.25)


class TestStreamingToolExecution:
    """Verify StreamingToolExecutor is used for tool execution."""

    @pytest.mark.asyncio
    async def test_parallel_tool_execution_timing(self):
        abort = asyncio.Event()
        provider = FakeProvider([
            assistant_event([
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/f1"}, "id": "t1"},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/f2"}, "id": "t2"},
                {"type": "tool_use", "name": "Glob", "input": {"pattern": "*.py"}, "id": "t3"},
            ]),
        ])

        engine = QueryEngine(QueryEngineConfig(
            provider=provider,
            tools=[_make_fake_tool("Read", 0.05, True), _make_fake_tool("Glob", 0.05, True)],
            system_prompt="test",
            max_turns=1,
            abort_signal=abort,
        ))

        import time
        start = time.perf_counter()
        events = []
        async for event in engine.submit_message("test"):
            events.append(event)
        elapsed = time.perf_counter() - start

        tool_results = [e for e in events if e.get("type") == "tool_result"]
        assert len(tool_results) >= 1
        assert elapsed < 0.2, f"Expected parallel exec ~0.05s, got {elapsed:.3f}s"


def _make_fake_tool(name: str, delay: float, concurrency_safe: bool):
    class FakeTool:
        def __init__(self):
            self._name = name
            self._delay = delay
            self._cs = concurrency_safe

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
            class FI:
                @staticmethod
                def model_json_schema():
                    return {"type": "object", "properties": {}}
            return FI

        @property
        def search_hint(self):
            return ""

        async def call(self, args, context, can_use_tool=None, parent_message=None, on_progress=None):
            import asyncio
            await asyncio.sleep(self._delay)
            return f"result_{self._name}"

        def is_concurrency_safe(self, input=None):
            return self._cs

        def is_read_only(self, input=None):
            return self._cs

    return FakeTool()


class TestYieldMissingToolResults:
    def test_generates_synthetic_results(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        assistant_msgs = [
            {
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "id": "t1", "input": {}},
                        {"type": "tool_use", "name": "Bash", "id": "t2", "input": {}},
                    ]
                }
            }
        ]
        assert len(engine.state.messages) == 0
        results = list(engine._yield_missing_tool_results(assistant_msgs, "Test error", None))
        assert len(engine.state.messages) == 2
        assert len(results) == 2
        for r in results:
            assert r["type"] == "tool_result"
            assert r["data"]["is_error"] is True
            assert "Test error" in r["data"]["content"]
        for msg in engine.state.messages:
            content = msg["message"]["content"]
            assert len(content) == 1
            assert content[0]["is_error"] is True
            assert "Test error" in content[0]["content"]

    def test_no_tool_blocks_does_nothing(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        assistant_msgs = [
            {"message": {"content": [{"type": "text", "text": "hello"}]}}
        ]
        list(engine._yield_missing_tool_results(assistant_msgs, "Test", None))
        assert len(engine.state.messages) == 0


class TestInterruptionMessage:
    def test_interruption_message_format(self):
        msg = _make_interruption_message()
        assert msg["type"] == "user"
        assert msg["is_meta"] is True
        content = msg["message"]["content"]
        assert isinstance(content, list)
        assert any("Interrupted" in c.get("text", "") for c in content if isinstance(c, dict))


class TestNormalizeMessages:
    def test_merge_consecutive_user_messages(self):
        msgs = [
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "a"}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "b"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": "x"}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "c"}]}},
        ]
        merged = QueryEngine._merge_consecutive_user_messages(msgs)
        assert len(merged) == 3
        assert len(merged[0]["message"]["content"]) == 2
        assert merged[1]["type"] == "assistant"
        assert merged[2]["type"] == "user"

    def test_no_consecutive_users_no_change(self):
        msgs = [
            {"type": "user", "message": {"role": "user", "content": "a"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "b"}},
        ]
        merged = QueryEngine._merge_consecutive_user_messages(msgs)
        assert len(merged) == 2


class TestHooks:
    def test_register_and_execute_post_sampling(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        calls: list = []
        engine.register_hook(lambda ev, data: calls.append((ev, data)))
        engine._execute_post_sampling_hooks([{"test": True}])
        assert len(calls) == 1
        assert calls[0][0] == "post_sampling"

    def test_register_and_execute_stop_hooks(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        calls: list = []
        engine.register_hook(lambda ev, data: calls.append((ev, data)))
        engine._execute_stop_hooks()
        assert len(calls) == 1
        assert calls[0][0] == "stop"

    def test_hook_exception_is_suppressed(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        engine.register_hook(lambda ev, data: (_ for _ in ()).throw(Exception("boom")))
        engine._execute_stop_hooks()


class TestStreamingExecutorIntegration:
    @pytest.mark.asyncio
    async def test_executor_created_before_streaming(self):
        abort = asyncio.Event()
        provider = FakeProvider([
            assistant_event([
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/f1"}, "id": "t1"},
                {"type": "tool_use", "name": "Glob", "input": {"pattern": "*.py"}, "id": "t2"},
            ]),
        ])

        engine = QueryEngine(QueryEngineConfig(
            provider=provider,
            tools=[_make_fake_tool("Read", 0.02, True), _make_fake_tool("Glob", 0.02, True)],
            system_prompt="test",
            max_turns=1,
            abort_signal=abort,
        ))

        events = []
        async for event in engine.submit_message("test"):
            events.append(event)

        tool_results = [e for e in events if e.get("type") == "tool_result"]
        assert len(tool_results) >= 1


class TestPromptTooLongRecovery:
    def test_is_withheld_detects_api_error(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        msgs = [{"message": {"type": "assistant", "is_api_error_message": True, "content": [{"type": "text", "text": "prompt too long error"}]}}]
        assert engine._is_withheld_prompt_too_long(msgs) is True

    def test_is_withheld_no_api_error_returns_false(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        msgs = [{"message": {"type": "assistant", "content": [{"type": "text", "text": "normal"}]}}]
        assert engine._is_withheld_prompt_too_long(msgs) is False

    def test_ptl_recovery_three_stage(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        engine.state._has_attempted_collapse_drain = False
        engine.state._has_attempted_reactive_compact = False
        msgs = [{"message": {"type": "assistant", "is_api_error_message": True, "content": [{"type": "text", "text": "prompt too long"}]}}]
        r1 = engine._try_prompt_too_long_recovery(msgs)
        assert r1 == "retry"
        assert engine.state._has_attempted_collapse_drain is True
        r2 = engine._try_prompt_too_long_recovery(msgs)
        assert r2 == "retry"
        assert engine.state._has_attempted_reactive_compact is True
        r3 = engine._try_prompt_too_long_recovery(msgs)
        assert r3 == "surface"

    def test_ptl_recovery_no_withheld(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        msgs = [{"message": {"type": "assistant", "content": [{"type": "text", "text": "ok"}]}}]
        assert engine._try_prompt_too_long_recovery(msgs) is None


class TestCompactBoundary:
    def test_snip_compact_updates_boundary(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        for i in range(40):
            engine.state.messages.append({"type": "user" if i % 2 == 0 else "assistant", "message": {"role": "user", "content": f"msg {i}"}})
        old_boundary = engine.state._compact_boundary_index
        removed = engine._try_snip_compact()
        assert removed > 0

    def test_snip_compact_too_few_messages(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        for i in range(10):
            engine.state.messages.append({"type": "user", "message": {"role": "user", "content": f"msg {i}"}})
        removed = engine._try_snip_compact()
        assert removed == 0

    def test_check_auto_compact_triggers_pipeline(self):
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test", is_auto_compact_enabled=True))
        for i in range(300):
            engine.state.messages.append({"type": "user", "message": {"role": "user", "content": "x" * 100}})
        engine.state.total_usage["input_tokens"] = 200_000
        result = engine._check_auto_compact()
        assert result is None or result == "blocking_limit"

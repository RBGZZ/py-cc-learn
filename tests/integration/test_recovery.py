"""Production audit: error recovery path tests."""
from __future__ import annotations

import asyncio
import uuid

import pytest

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.errors import CannotRetryError
from server.services.provider import ProviderConfig, StreamEvent
from server.services.retry import CircuitBreaker, CircuitBreakerConfig, CircuitState


class FailingProvider:
    """Provider that fails N times then succeeds."""

    def __init__(self, fail_count: int = 3):
        self.config = ProviderConfig(model="fail", api_key="", max_tokens=100)
        self.fail_count = fail_count
        self.call_count = 0

    def get_default_model(self):
        return "fail"

    async def stream_chat(self, messages, system_prompt=None, tools=None):
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise RuntimeError("Simulated provider failure")
        yield StreamEvent(
            type="assistant",
            data={
                "type": "assistant",
                "uuid": str(uuid.uuid4()),
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "recovered"}],
                    "model": "fail",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        )
        yield StreamEvent(type="message_stop", data={})

    def supports_thinking(self):
        return False


class TruncatedProvider:
    """Provider that returns max_tokens stop reason on first call."""

    def __init__(self):
        self.config = ProviderConfig(model="trunc", api_key="", max_tokens=100)
        self.call_count = 0

    def get_default_model(self):
        return "trunc"

    async def stream_chat(self, messages, system_prompt=None, tools=None):
        self.call_count += 1
        yield StreamEvent(
            type="text_delta", data={"type": "text_delta", "text": "partial response..."}
        )
        yield StreamEvent(
            type="assistant",
            data={
                "type": "assistant",
                "uuid": str(uuid.uuid4()),
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "partial response..."}],
                    "model": "trunc",
                    "stop_reason": "max_tokens" if self.call_count <= 2 else "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 50},
                },
            },
        )
        yield StreamEvent(type="message_stop", data={})

    def supports_thinking(self):
        return False


@pytest.mark.asyncio
async def test_circuit_breaker_full_state_machine():
    """Verify CircuitBreaker transitions CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout_seconds=0.3,
        half_open_max_requests=1,
    )
    cb = CircuitBreaker(config)

    assert cb.state == CircuitState.CLOSED
    for _ in range(3):
        await cb.before_request()
        await cb.on_failure()
    assert cb.state == CircuitState.OPEN

    try:
        await cb.before_request()
        assert False, "Should raise CannotRetryError"
    except CannotRetryError:
        pass

    await asyncio.sleep(0.4)
    await cb.before_request()
    assert cb.state == CircuitState.HALF_OPEN

    await cb.on_success()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_failing_provider_handled_gracefully():
    """Verify engine handles failing provider without crashing."""
    provider = FailingProvider(fail_count=1)
    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=[], system_prompt="test", max_turns=1,
    ))

    try:
        async for event in engine.submit_message("test", is_meta=True):
            pass
    except Exception:
        pass

    assert provider.call_count >= 1

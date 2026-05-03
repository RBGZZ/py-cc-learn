from __future__ import annotations

import asyncio
import pytest
from server.services.retry import CircuitBreaker, CircuitBreakerConfig, CircuitState, with_retry, RetryConfig


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_closed_to_open(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3, recovery_timeout_seconds=0.1))
        assert cb.state == CircuitState.CLOSED
        for _ in range(3):
            await cb.before_request()
            await cb.on_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_after_recovery_becomes_half_open(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout_seconds=0.05))
        for _ in range(2):
            await cb.before_request()
            await cb.on_failure()
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.1)
        await cb.before_request()
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_to_closed(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout_seconds=0.05))
        for _ in range(2):
            await cb.before_request()
            await cb.on_failure()
        await asyncio.sleep(0.1)
        await cb.before_request()
        await cb.on_success()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_back_to_open(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout_seconds=0.05))
        for _ in range(2):
            await cb.before_request()
            await cb.on_failure()
        await asyncio.sleep(0.1)
        await cb.before_request()
        await cb.on_failure()
        assert cb.state == CircuitState.OPEN

    def test_default_config(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.config.failure_threshold == 5
        assert cb.config.recovery_timeout_seconds == 30.0


class TestWithRetry:
    @pytest.mark.asyncio
    async def test_retries_exhausted(self):
        call_count = [0]
        class RetryableError(RuntimeError):
            def __init__(self, msg):
                super().__init__(msg)
                self.status_code = 500

        async def always_fail(attempt):
            call_count[0] += 1
            raise RetryableError("server error")

        config = RetryConfig(max_retries=2, model="test", fallback_model=None)
        from server.services.errors import CannotRetryError
        with pytest.raises(CannotRetryError):
            await with_retry(always_fail, config)
        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_first_success_no_retry(self):
        async def success(attempt):
            return "ok"

        config = RetryConfig(max_retries=2, model="test", fallback_model=None)
        result = await with_retry(success, config)
        assert result == "ok"

"""CircuitBreaker resilience benchmark: measure full state machine recovery."""
from __future__ import annotations

import asyncio
import time

from server.services.errors import CannotRetryError
from server.services.retry import CircuitBreaker, CircuitBreakerConfig, CircuitState


async def bench_circuit_breaker():
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout_seconds=0.5,
        half_open_max_requests=1,
    )
    cb = CircuitBreaker(config)

    print(f"  Initial state: {cb.state.value}")

    # Phase 1: CLOSED -> OPEN (trigger failures)
    failure_start = time.perf_counter()
    for _ in range(config.failure_threshold):
        await cb.before_request()
        await cb.on_failure()
    failure_time = time.perf_counter() - failure_start
    print(
        f"  After {config.failure_threshold} failures: "
        f"state={cb.state.value} (triggered in {failure_time*1000:.1f}ms)"
    )

    assert cb.state == CircuitState.OPEN, f"Expected OPEN, got {cb.state}"

    # Phase 2: OPEN -> wait -> HALF_OPEN (recovery timeout)
    open_start = time.perf_counter()
    try:
        await cb.before_request()
        raise AssertionError("Should have raised CannotRetryError")
    except CannotRetryError:
        pass

    await asyncio.sleep(config.recovery_timeout_seconds + 0.1)
    await cb.before_request()
    recovery_time = time.perf_counter() - open_start
    print(f"  Recovery timeout: {recovery_time*1000:.1f}ms, state={cb.state.value}")

    # Phase 3: HALF_OPEN -> CLOSED (successful request)
    await cb.on_success()
    reset_time = time.perf_counter() - failure_start
    print(
        f"  After success in HALF_OPEN: "
        f"state={cb.state.value} (reset in {reset_time*1000:.1f}ms)"
    )

    assert cb.state == CircuitState.CLOSED, f"Expected CLOSED, got {cb.state}"

    return {
        "failure_trigger_ms": failure_time * 1000,
        "recovery_timeout_ms": recovery_time * 1000,
        "total_reset_ms": reset_time * 1000,
    }


async def bench_fallback_switch():
    """Simulate fallback model switch latency."""
    from server.services.errors import FallbackTriggeredError
    from server.services.retry import RetryConfig

    config = RetryConfig(
        max_retries=1,
        model="primary-model",
        fallback_model="fallback-model",
    )

    call_count = 0
    switch_time = None

    async def operation(attempt):
        nonlocal call_count, switch_time
        call_count += 1
        if call_count == 1:
            raise FallbackTriggeredError("primary-model", "fallback-model")
        switch_time = time.perf_counter()
        return "fallback_ok"

    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            _run_retry(operation, config),
            timeout=5.0,
        )
    except (TimeoutError, FallbackTriggeredError):
        result = None

    elapsed = time.perf_counter() - start
    switch_ms = (switch_time - start) * 1000 if switch_time else elapsed * 1000

    print(f"  Fallback switch: {switch_ms:.1f}ms, result={result}")
    return switch_ms


async def _run_retry(operation, config):
    from server.services.retry import with_retry
    return await with_retry(operation, config)


def main():
    print("=== Resilience Benchmark ===")

    # CircuitBreaker full state machine
    print("  [CircuitBreaker] CLOSED -> OPEN -> HALF_OPEN -> CLOSED")
    cb_results = asyncio.run(bench_circuit_breaker())
    print(f"  failure_threshold trigger: {cb_results['failure_trigger_ms']:.1f}ms")
    print(f"  recovery_timeout: {cb_results['recovery_timeout_ms']:.1f}ms")
    print(f"  total reset: {cb_results['total_reset_ms']:.1f}ms")

    # Fallback switch
    print("  [Fallback] Trigger fallback model switch")
    fallback_ms = asyncio.run(bench_fallback_switch())

    assert cb_results["total_reset_ms"] < 5000, (
        f"CircuitBreaker reset too slow: {cb_results['total_reset_ms']:.0f}ms"
    )
    print(
        f"\nPASS: circuit_breaker_reset={cb_results['total_reset_ms']:.0f}ms "
        f"fallback_switch={fallback_ms:.0f}ms"
    )


if __name__ == "__main__":
    main()

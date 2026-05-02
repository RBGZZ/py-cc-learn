from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from server.services.errors import (
    CannotRetryError,
    FallbackTriggeredError,
)

DEFAULT_MAX_RETRIES = 10
FLOOR_OUTPUT_TOKENS = 3000
MAX_529_RETRIES = 3
BASE_DELAY_MS = 500
DEFAULT_FAST_MODE_FALLBACK_HOLD_MS = 30 * 60 * 1000
SHORT_RETRY_THRESHOLD_MS = 20 * 1000
MIN_COOLDOWN_MS = 10 * 60 * 1000
PERSISTENT_MAX_BACKOFF_MS = 5 * 60 * 1000
PERSISTENT_RESET_CAP_MS = 6 * 60 * 60 * 1000
HEARTBEAT_INTERVAL_MS = 30_000

FOREGROUND_529_RETRY_SOURCES = {
    "repl_main_thread",
    "repl_main_thread:outputStyle:custom",
    "repl_main_thread:outputStyle:Explanatory",
    "repl_main_thread:outputStyle:Learning",
    "sdk",
    "agent:custom",
    "agent:default",
    "agent:builtin",
    "compact",
    "hook_agent",
    "hook_prompt",
    "verification_agent",
    "side_question",
    "auto_mode",
}


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_requests: int = 1


class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_requests = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def _transition(self) -> None:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.config.recovery_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0

    async def before_request(self) -> None:
        await self._transition()
        async with self._lock:
            if self._state == CircuitState.OPEN:
                raise CannotRetryError(
                    RuntimeError("Circuit breaker is OPEN — provider unavailable"),
                    "",
                )

    async def on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
            self._failure_count = 0

    async def on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if (
                self._failure_count >= self.config.failure_threshold
                and self._state == CircuitState.CLOSED
            ):
                self._state = CircuitState.OPEN


class RetryConfig:
    def __init__(
        self,
        max_retries: int | None = None,
        model: str = "",
        fallback_model: str | None = None,
        signal: Any = None,
        query_source: str | None = None,
        initial_consecutive_529_errors: int = 0,
    ) -> None:
        self.max_retries = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES
        self.model = model
        self.fallback_model = fallback_model
        self.signal = signal
        self.query_source = query_source
        self.initial_consecutive_529_errors = initial_consecutive_529_errors


def get_retry_delay(
    attempt: int, retry_after_header: str | None = None, max_delay_ms: int = 32000
) -> int:
    if retry_after_header:
        try:
            seconds = int(retry_after_header)
            return seconds * 1000
        except ValueError:
            pass

    base_delay = min(BASE_DELAY_MS * (2 ** (attempt - 1)), max_delay_ms)
    jitter = random.random() * 0.25 * base_delay
    return int(base_delay + jitter)


def is_529_error(error: Exception) -> bool:
    msg = str(error)
    return '"type":"overloaded_error"' in msg or any(
        getattr(error, attr, None) == 529 for attr in ("status_code", "status", "http_status")
    )


def should_retry_529(query_source: str | None) -> bool:
    return query_source is None or query_source in FOREGROUND_529_RETRY_SOURCES


def is_transient_capacity_error(error: Exception) -> bool:
    if is_529_error(error):
        return True
    return any(
        getattr(error, attr, None) == 429 for attr in ("status_code", "status", "http_status")
    )


def should_retry(error: Exception) -> bool:
    if isinstance(error, CannotRetryError):
        return False

    if is_transient_capacity_error(error):
        return True

    if is_529_error(error):
        return True

    msg = str(error).lower()

    if "`tool_use` ids were found without `tool_result`" in msg:
        return False
    if "unexpected `tool_use_id`" in msg:
        return True
    if "invalid model name" in msg:
        return True

    status = None
    for attr in ("status_code", "status", "http_status"):
        val = getattr(error, attr, None)
        if isinstance(val, int):
            status = val
            break

    if status is not None:
        if status == 408:
            return True
        if status == 409:
            return True
        if status == 429:
            return True
        if status == 401 or status == 403:
            return True
        if status >= 500:
            return True

    if "connection" in msg or "timeout" in msg:
        return True

    return False


async def with_retry(
    operation_fn: Callable[[int], Awaitable[Any]],
    config: RetryConfig,
    circuit_breaker: CircuitBreaker | None = None,
) -> Any:
    max_retries = config.max_retries
    consecutive_529_errors = config.initial_consecutive_529_errors
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 2):
        if config.signal is not None:
            cancelled = getattr(config.signal, "is_set", None)
            if cancelled and cancelled():
                raise CannotRetryError(RuntimeError("Request was aborted"), config.model)

        if circuit_breaker is not None:
            try:
                await circuit_breaker.before_request()
            except CannotRetryError:
                raise

        try:
            result = await operation_fn(attempt)
            if circuit_breaker is not None:
                await circuit_breaker.on_success()
            return result
        except FallbackTriggeredError:
            raise
        except CannotRetryError:
            raise
        except Exception as error:
            last_error = error
            if circuit_breaker is not None:
                await circuit_breaker.on_failure()

            if is_529_error(error):
                if not should_retry_529(config.query_source):
                    raise CannotRetryError(error, config.model)

                consecutive_529_errors += 1
                if consecutive_529_errors >= MAX_529_RETRIES:
                    if config.fallback_model:
                        raise FallbackTriggeredError(config.model, config.fallback_model)

            if attempt > max_retries:
                if not should_retry(error):
                    raise CannotRetryError(error, config.model)
                raise CannotRetryError(error, config.model)

            if not should_retry(error):
                raise CannotRetryError(error, config.model)

            retry_after = _get_retry_after_header(error)
            delay_ms = get_retry_delay(attempt, retry_after)
            await asyncio.sleep(delay_ms / 1000)

    if last_error:
        raise CannotRetryError(last_error, config.model)
    raise RuntimeError("Unreachable: with_retry loop exhausted")


def _get_retry_after_header(error: Exception) -> str | None:
    headers = getattr(error, "headers", None)
    if headers is not None:
        if hasattr(headers, "get"):
            return headers.get("retry-after")
        if isinstance(headers, dict):
            return headers.get("retry-after")
    return None


def parse_max_tokens_context_overflow_error(error: Exception) -> dict[str, int] | None:
    msg = str(error)
    import re

    if "input length and `max_tokens` exceed context limit" not in msg:
        return None

    match = re.search(
        r"input length and `max_tokens` exceed context limit: (\d+) \+ (\d+) > (\d+)",
        msg,
    )
    if not match:
        return None

    return {
        "input_tokens": int(match.group(1)),
        "max_tokens": int(match.group(2)),
        "context_limit": int(match.group(3)),
    }

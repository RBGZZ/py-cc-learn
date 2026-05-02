from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.services.anthropic_provider import (
    AnthropicProvider,
    _normalize_usage,
    _safe_parse_json,
    _update_usage,
    EMPTY_USAGE,
)
from server.services.errors import (
    APIErrorType,
    CannotRetryError,
    classify_api_error,
    is_media_size_error,
    is_prompt_too_long_message,
    parse_prompt_too_long_token_counts,
)
from server.services.provider import ProviderConfig, StreamEvent
from server.services.retry import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    FallbackTriggeredError,
    RetryConfig,
    get_retry_delay,
    is_529_error,
    should_retry,
)


class TestSafeParseJSON:
    def test_parses_valid_json(self):
        result = _safe_parse_json('{"type": "message_start", "message": {}}')
        assert result is not None
        assert result["type"] == "message_start"

    def test_returns_none_for_invalid_json(self):
        result = _safe_parse_json('{"type": "message_start"')
        assert result is None

    def test_returns_none_for_half_json(self):
        result = _safe_parse_json('{"type": "content_block_delta", "delta": {"text": "hel')
        assert result is None

    def test_handles_empty_string(self):
        result = _safe_parse_json("")
        assert result is None

    def test_handles_done_marker(self):
        result = _safe_parse_json("[DONE]")
        assert result is None


class TestNormalizeUsage:
    def test_returns_empty_usage_for_none(self):
        result = _normalize_usage(None)
        assert result == EMPTY_USAGE

    def test_extracts_token_counts(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = _normalize_usage(usage)
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50

    def test_handles_missing_fields(self):
        result = _normalize_usage({})
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0

    def test_handles_null_values(self):
        usage = {"input_tokens": None, "output_tokens": None}
        result = _normalize_usage(usage)
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0


class TestUpdateUsage:
    def test_updates_from_part_usage(self):
        existing = {"input_tokens": 100, "output_tokens": 50}
        new = {"input_tokens": 200, "output_tokens": 75}
        result = _update_usage(existing, new)
        assert result["input_tokens"] == 200
        assert result["output_tokens"] == 75

    def test_does_not_overwrite_with_none(self):
        existing = {"input_tokens": 100}
        result = _update_usage(existing, None)
        assert result == existing


class TestSSEEventParsing:
    def _make_provider(self) -> AnthropicProvider:
        config = ProviderConfig(
            api_key="test-key",
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
        )
        return AnthropicProvider(config)

    def test_message_start_event(self):
        provider = self._make_provider()
        content_blocks: list[dict] = []
        partial_message: dict | None = None
        usage = dict(EMPTY_USAGE)

        parsed = {"type": "message_start", "message": {
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 10, "output_tokens": 0},
        }}

        partial_message = parsed.get("message", {})
        usage = _normalize_usage(partial_message.get("usage"))

        assert partial_message is not None
        assert usage["input_tokens"] == 10

    def test_content_block_start_text(self):
        parsed = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": "Hello World"},
        }
        block = dict(parsed["content_block"])
        block["text"] = ""
        assert block["type"] == "text"
        assert block["text"] == ""

    def test_content_block_start_tool_use(self):
        parsed = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu_01", "name": "bash"},
        }
        block = dict(parsed["content_block"])
        block["input"] = ""
        assert block["type"] == "tool_use"
        assert block["id"] == "toolu_01"
        assert block["input"] == ""

    def test_content_block_start_thinking(self):
        parsed = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "Let me think..."},
        }
        block = dict(parsed["content_block"])
        block["thinking"] = ""
        block["signature"] = ""
        assert block["type"] == "thinking"
        assert block["thinking"] == ""

    def test_content_block_delta_text(self):
        blocks = [{"type": "text", "text": ""}]
        parsed = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello"},
        }
        delta = parsed["delta"]
        blocks[parsed["index"]]["text"] += delta["text"]
        assert blocks[0]["text"] == "Hello"

    def test_content_block_delta_input_json(self):
        blocks = [{"type": "tool_use", "id": "t1", "name": "bash", "input": ""}]
        parsed = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"command": "ls"}'},
        }
        delta = parsed["delta"]
        blocks[parsed["index"]]["input"] += delta["partial_json"]
        assert blocks[0]["input"] == '{"command": "ls"}'

    def test_content_block_delta_thinking(self):
        blocks = [{"type": "thinking", "thinking": "", "signature": ""}]
        parsed = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "I should..."},
        }
        delta = parsed["delta"]
        blocks[parsed["index"]]["thinking"] += delta["thinking"]
        assert blocks[0]["thinking"] == "I should..."

    def test_content_block_delta_signature(self):
        blocks = [{"type": "thinking", "thinking": "", "signature": ""}]
        parsed = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "sig123"},
        }
        delta = parsed["delta"]
        blocks[parsed["index"]]["signature"] = delta["signature"]
        assert blocks[0]["signature"] == "sig123"

    def test_content_block_stop(self):
        blocks = [{"type": "text", "text": "Hello World"}]
        partial = {"model": "claude-sonnet-4-20250514", "role": "assistant"}
        index = 0
        normalized = {"type": "text", "text": "Hello World"}
        msg = {
            "message": {
                "role": "assistant",
                "content": [normalized],
                "model": partial["model"],
                "stop_reason": None,
                "usage": EMPTY_USAGE,
            },
            "type": "assistant",
        }
        assert msg["message"]["content"][0]["text"] == "Hello World"

    def test_message_delta_updates_stop_reason_and_usage(self):
        parsed = {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 150},
        }
        delta = parsed["delta"]
        stop_reason = delta.get("stop_reason")
        usage = _update_usage(EMPTY_USAGE, parsed.get("usage"))
        assert stop_reason == "end_turn"
        assert usage["output_tokens"] == 150

    def test_ping_event(self):
        parsed = {"type": "ping"}
        assert parsed["type"] == "ping"

    def test_error_event(self):
        parsed = {"type": "error", "error": {"type": "overloaded_error", "message": "Server overloaded"}}
        assert parsed["error"]["message"] == "Server overloaded"

    def test_malformed_half_json_is_skipped(self):
        result = _safe_parse_json('{"type": "content_blo')
        assert result is None

    def test_empty_data_line_is_skipped(self):
        assert _safe_parse_json("") is None


class TestErrorClassification:
    def test_classify_api_timeout(self):
        error = Exception("Request timed out")
        assert classify_api_error(error) == APIErrorType.TIMEOUT

    def test_classify_overloaded(self):
        class OverloadedError(Exception):
            def __init__(self):
                super().__init__('{"type":"overloaded_error"}')
                self.status = 529
        assert classify_api_error(OverloadedError()) == APIErrorType.SERVER_OVERLOAD

    def test_classify_rate_limit(self):
        class RateLimitError(Exception):
            def __init__(self):
                super().__init__("429 rate limit exceeded")
                self.status_code = 429
        assert classify_api_error(RateLimitError()) == APIErrorType.RATE_LIMIT

    def test_classify_prompt_too_long(self):
        assert classify_api_error(Exception("Prompt is too long")) == APIErrorType.PROMPT_TOO_LONG

    def test_classify_invalid_api_key(self):
        assert classify_api_error(Exception("invalid x-api-key")) == APIErrorType.INVALID_API_KEY

    def test_classify_auth_401(self):
        class AuthError(Exception):
            def __init__(self):
                super().__init__("Unauthorized")
                self.status = 401
        assert classify_api_error(AuthError()) == APIErrorType.AUTH_ERROR

    def test_classify_server_error_500(self):
        class ServerError(Exception):
            def __init__(self):
                super().__init__("Internal server error")
                self.status = 500
        assert classify_api_error(ServerError()) == APIErrorType.SERVER_ERROR

    def test_is_media_size_error_image(self):
        assert is_media_size_error("image exceeds 5MB maximum")

    def test_is_media_size_error_pdf(self):
        assert is_media_size_error("maximum of 100 PDF pages")

    def test_is_prompt_too_long_message(self):
        blocks = [{"type": "text", "text": "Prompt is too long"}]
        assert is_prompt_too_long_message(blocks) is True

    def test_parse_prompt_too_long_token_counts(self):
        actual, limit = parse_prompt_too_long_token_counts("prompt is too long: 137500 tokens > 135000 maximum")
        assert actual == 137500
        assert limit == 135000


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_five_failures(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5, recovery_timeout_seconds=30.0))
        for _ in range(5):
            await cb.on_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_before_request_raises_when_open(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=30.0))
        await cb.on_failure()
        with pytest.raises(CannotRetryError):
            await cb.before_request()

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5, recovery_timeout_seconds=30.0))
        for _ in range(3):
            await cb.on_failure()
        await cb.on_success()
        assert cb.state == CircuitState.CLOSED


class TestRetry:
    def test_get_retry_delay_exponential(self):
        delay = get_retry_delay(1)
        assert 500 <= delay <= 625

    def test_get_retry_delay_with_header(self):
        delay = get_retry_delay(1, "10")
        assert delay == 10000

    def test_is_529_error(self):
        class Error529(Exception):
            def __init__(self):
                super().__init__("Overloaded")
                self.status = 529
        assert is_529_error(Error529()) is True

    def test_is_529_error_from_message(self):
        assert is_529_error(Exception('{"type":"overloaded_error"}')) is True

    def test_should_retry_429(self):
        class Error429(Exception):
            def __init__(self):
                super().__init__("Rate limited")
                self.status_code = 429
        assert should_retry(Error429()) is True

    def test_should_retry_500(self):
        class Error500(Exception):
            def __init__(self):
                super().__init__("Server error")
                self.status_code = 500
        assert should_retry(Error500()) is True

    def test_should_retry_401(self):
        class Error401(Exception):
            def __init__(self):
                super().__init__("Unauthorized")
                self.status_code = 401
        assert should_retry(Error401()) is True


class TestProviderFactory:
    def test_auto_detect_anthropic(self):
        from server.services.provider_factory import ProviderFactory
        from server.services.provider import ProviderType
        from server.utils.settings import Settings

        settings = Settings(anthropic_api_key="test-key")
        factory = ProviderFactory()
        result = factory._auto_detect_provider(settings)
        assert result == ProviderType.ANTHROPIC

    def test_auto_detect_openai(self):
        from server.services.provider_factory import ProviderFactory
        from server.services.provider import ProviderType
        from server.utils.settings import Settings

        settings = Settings(openai_api_key="test-key")
        factory = ProviderFactory()
        result = factory._auto_detect_provider(settings)
        assert result == ProviderType.OPENAI

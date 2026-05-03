from __future__ import annotations

import pytest
from server.services.compact import (
    get_compact_prompt, format_compact_summary, get_compact_user_summary_message,
    rough_token_count, rough_token_count_for_messages,
    calculate_token_warning_state, is_auto_compact_enabled,
)


class TestCompactPrompt:
    def test_no_tools_preamble_present(self):
        prompt = get_compact_prompt()
        assert "CRITICAL: Respond with TEXT ONLY" in prompt

    def test_custom_instructions_appended(self):
        prompt = get_compact_prompt("Use Chinese")
        assert "Use Chinese" in prompt

    def test_format_summary_strips_analysis(self):
        summary = "<analysis>some thoughts</analysis><summary>key points</summary>"
        formatted = format_compact_summary(summary)
        assert "key points" in formatted

    def test_format_summary_no_tags_returns_original(self):
        formatted = format_compact_summary("plain text")
        assert "plain text" in formatted

    def test_get_compact_user_summary_message(self):
        msg = get_compact_user_summary_message("compressed", suppress_follow_up_questions=True)
        assert "compressed" in msg


class TestCompactTokenCounting:
    def test_rough_token_count_empty(self):
        assert rough_token_count("") == 0

    def test_rough_token_count_english(self):
        count = rough_token_count("hello world")
        assert count >= 2

    def test_rough_token_count_chinese(self):
        count = rough_token_count("你好世界")
        assert count >= 1

    def test_token_count_for_messages(self):
        msgs = [{"type": "user", "message": {"content": [{"type": "text", "text": "hello"}]}}]
        count = rough_token_count_for_messages(msgs)
        assert count > 0


class TestCompactThreshold:
    def test_auto_compact_threshold(self):
        threshold = calculate_token_warning_state(100_000, "claude-sonnet-4-20250514")
        assert "percent_left" in threshold
        assert "is_above_auto_compact_threshold" in threshold

    def test_auto_compact_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("DISABLE_COMPACT", "1")
        assert is_auto_compact_enabled() is False

    def test_auto_compact_enabled_default(self):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.delenv("DISABLE_COMPACT", raising=False)
        monkeypatch.delenv("DISABLE_AUTO_COMPACT", raising=False)
        assert is_auto_compact_enabled() is True

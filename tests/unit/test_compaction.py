from __future__ import annotations

import pytest
from server.services.compact import (
    AUTOCOMPACT_BUFFER_TOKENS,
    WARNING_THRESHOLD_BUFFER_TOKENS,
    ERROR_THRESHOLD_BUFFER_TOKENS,
    MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
    COMPACTABLE_TOOL_NAMES,
)


class TestCompactConstants:
    def test_autocompact_buffer(self):
        assert AUTOCOMPACT_BUFFER_TOKENS == 13_000

    def test_warning_threshold(self):
        assert WARNING_THRESHOLD_BUFFER_TOKENS == 20_000

    def test_error_threshold(self):
        assert ERROR_THRESHOLD_BUFFER_TOKENS == 20_000

    def test_max_consecutive_failures(self):
        assert MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES == 3

    def test_compactable_tool_names(self):
        assert "bash" in COMPACTABLE_TOOL_NAMES
        assert "grep" in COMPACTABLE_TOOL_NAMES

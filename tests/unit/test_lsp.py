from __future__ import annotations

import pytest
from server.services.lsp import LSPPosition, LSPClient, LSPError, _detect_language, _LANGUAGE_IDS


class TestLSPBasics:
    def test_position(self):
        pos = LSPPosition(line=10, character=5)
        assert pos.line == 10
        assert pos.character == 5

    def test_language_detection(self):
        assert _detect_language("/path/to/file.py") == "python"
        assert _detect_language("/path/to/file.ts") == "typescript"
        assert _detect_language("/path/to/file.js") == "javascript"
        assert _detect_language("/path/to/file.go") == "go"
        assert _detect_language("/path/to/file.rs") == "rust"
        assert _detect_language("/path/to/file.txt") is None

    def test_lsp_error(self):
        error = LSPError(code=-1, message="Not found")
        assert error.code == -1
        assert "Not found" in str(error)

    def test_language_ids_complete(self):
        assert ".py" in _LANGUAGE_IDS
        assert ".ts" in _LANGUAGE_IDS
        assert ".js" in _LANGUAGE_IDS
        assert ".go" in _LANGUAGE_IDS
        assert ".rs" in _LANGUAGE_IDS

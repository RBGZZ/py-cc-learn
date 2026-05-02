from __future__ import annotations

import pytest
from server.models.tools import ValidationResult


class TestValidationResult:
    def test_valid(self):
        r = ValidationResult(valid=True)
        assert r.valid
        assert r.errors == []

    def test_invalid_with_errors(self):
        r = ValidationResult(valid=False, errors=["field required", "invalid type"])
        assert not r.valid
        assert len(r.errors) == 2


class TestToolBase:
    def test_tool_registration(self):
        from server.tools.tool import Tool, ToolCallResult

        assert ToolCallResult(data="test").data == "test"


class TestToolRegistry:
    def test_assemble_tool_pool_empty(self):
        from server.tools.registry import assemble_tool_pool

        result = assemble_tool_pool(None, [], [])
        assert result == []

    def test_assemble_tool_pool_with_builtins(self):
        from server.tools.registry import assemble_tool_pool
        from server.tools.file_read_tool import FileReadTool
        from server.tools.file_write_tool import FileWriteTool

        tools = [FileReadTool(), FileWriteTool()]
        result = assemble_tool_pool(None, [], tools)
        assert len(result) == 2
        names = [t.name for t in result]
        assert "Read" in names
        assert "Write" in names

    def test_assemble_tool_pool_dedup(self):
        from server.tools.registry import assemble_tool_pool
        from server.tools.file_read_tool import FileReadTool

        read_tool = FileReadTool()
        result = assemble_tool_pool(None, [], [read_tool, read_tool])
        names = [t.name for t in result]
        assert names.count("Read") == 1

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


from server.tools.tool import tool_matches_name, find_tool_by_name


class TestToolUtils:
    def test_tool_matches_name_exact(self):
        class FakeTool:
            name = "Read"
            aliases = None
        assert tool_matches_name(FakeTool(), "Read") is True

    def test_tool_matches_name_alias(self):
        class FakeTool:
            name = "Read"
            aliases = ["cat"]
        assert tool_matches_name(FakeTool(), "cat") is True

    def test_tool_matches_name_no_match(self):
        class FakeTool:
            name = "Read"
            aliases = []
        assert tool_matches_name(FakeTool(), "Write") is False

    def test_find_tool_by_name_found(self):
        class FakeRead:
            name = "Read"
            aliases = None
        assert find_tool_by_name([FakeRead()], "Read") is not None

    def test_find_tool_by_name_not_found(self):
        class FakeRead:
            name = "Read"
            aliases = None
        assert find_tool_by_name([FakeRead()], "Write") is None


class TestBuiltToolDefaults:
    def test_defaults_sealed(self):
        from server.tools.tool import build_tool, ToolDef

        class FakeInput:
            @staticmethod
            def model_json_schema():
                return {"type": "object", "properties": {}}

        async def fake_call(args, ctx, can, parent, on_progress=None):
            from server.tools.tool import ToolCallResult
            return ToolCallResult(data="ok")

        async def fake_desc(inp, opts):
            return ""

        async def fake_prompt(opts):
            return ""

        def fake_ufn(inp=None):
            return "Test"
        def fake_rm(inp, opts):
            return None
        def fake_map(content, tui):
            return {"type": "tool_result", "tool_use_id": tui, "content": []}

        tool = build_tool(ToolDef(
            name="TestTool",
            input_schema=FakeInput,
            call=fake_call,
            description=fake_desc,
            prompt=fake_prompt,
            render_tool_use_message=fake_rm,
            map_tool_result_to_tool_result_block_param=fake_map,
            max_result_size_chars=1000,
        ))
        assert tool.is_concurrency_safe(None) is False
        assert tool.is_read_only(None) is False
        assert tool.is_destructive(None) is False
        assert tool.interrupt_behavior() == "block"
        assert tool.is_enabled() is True

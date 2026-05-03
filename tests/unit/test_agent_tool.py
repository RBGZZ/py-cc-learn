from __future__ import annotations

import pytest
from server.tools.agent_tool import AgentTool, SubagentContext, AgentInput, AgentOutput, _timeout_info


class TestSubagentContext:
    def test_create(self):
        ctx = SubagentContext(
            subagent_type="general-purpose",
        )
        assert ctx.subagent_type == "general-purpose"
        assert not ctx.is_aborted

    def test_abort(self):
        ctx = SubagentContext(subagent_type="Explore")
        ctx.abort()
        assert ctx.is_aborted

    def test_filter_tools_allowed(self):
        ctx = SubagentContext(
            allowed_tools={"Read", "Write"},
        )
        filtered = ctx.filter_tools([])
        assert filtered == []

    def test_messages(self):
        ctx = SubagentContext()
        ctx.add_message({"type": "user", "content": "hello"})
        msgs = ctx.get_messages()
        assert len(msgs) == 1


class TestAgentTool:
    def test_name(self):
        tool = AgentTool()
        assert tool.name == "Agent"

    def test_input_validation(self):
        tool = AgentTool()
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            tool.validate_input(
                AgentInput(description="test", prompt="do something"),
                None,
            )
        )
        assert result.valid

    def test_input_validation_missing(self):
        tool = AgentTool()
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            tool.validate_input(
                AgentInput(description="", prompt=""),
                None,
            )
        )
        assert not result.valid

    def test_is_read_only(self):
        tool = AgentTool()
        assert tool.is_read_only()

    def test_is_concurrency_safe(self):
        tool = AgentTool()
        assert tool.is_concurrency_safe()


import asyncio
from server.tools.tool import ToolCallResult


class TestAgentToolCall:
    @pytest.mark.asyncio
    async def test_call_no_parent_tools_fallback(self):
        tool = AgentTool()
        result = await tool.call(AgentInput(description="test", prompt="hi"), None)
        assert isinstance(result, ToolCallResult)
        output = result.data
        assert "I would run" in output.result or output.status != "completed"

    def test_timeout_info_helper(self):
        from server.tools.agent_tool import _timeout_info
        ti = _timeout_info(True)
        assert ti["timed_out"] is True
        assert ti["timeout_ms"] == 300000
        ti2 = _timeout_info(False)
        assert ti2["timed_out"] is False

    def test_map_result_timeout(self):
        tool = AgentTool()
        from server.tools.agent_tool import AgentOutput
        output = AgentOutput(agent_id="a1", task_id="t1", status="timeout", tool_use_count=5, elapsed_ms=120000)
        result = tool.map_tool_result_to_tool_result_block_param(output, "tu1")
        assert result["tool_use_id"] == "tu1"
        content = result["content"]
        assert len(content) == 1
        assert "timed out" in content[0]["text"]

    def test_map_result_killed(self):
        tool = AgentTool()
        from server.tools.agent_tool import AgentOutput
        output = AgentOutput(agent_id="a1", task_id="t1", status="killed")
        result = tool.map_tool_result_to_tool_result_block_param(output, "tu1")
        assert "cancelled by user" in result["content"][0]["text"]

    def test_map_result_failed(self):
        tool = AgentTool()
        from server.tools.agent_tool import AgentOutput
        output = AgentOutput(agent_id="a1", task_id="t1", status="failed", result="boom")
        result = tool.map_tool_result_to_tool_result_block_param(output, "tu1")
        assert "boom" in result["content"][0]["text"]

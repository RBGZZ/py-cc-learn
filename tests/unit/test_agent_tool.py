from __future__ import annotations

import pytest
from server.tools.agent_tool import AgentTool, SubagentContext, AgentInput


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

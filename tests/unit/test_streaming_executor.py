from __future__ import annotations

import asyncio

import pytest
from server.tools.streaming import (
    STATUS_COMPLETED,
    STATUS_EXECUTING,
    STATUS_QUEUED,
    AbortController,
    ToolUseBlock,
    StreamingToolExecutor,
    TrackedTool,
)


class TestStreamingBasics:
    def test_abort_controller_basic(self):
        ctrl = AbortController()
        assert not ctrl.aborted

        ctrl.abort("test")
        assert ctrl.aborted
        assert ctrl.reason == "test"

    async def test_abort_controller_wait(self):
        ctrl = AbortController()
        task = asyncio.ensure_future(ctrl.wait())
        await asyncio.sleep(0.01)
        assert not task.done()
        ctrl.abort()
        await task

    def test_tool_status_constants(self):
        assert STATUS_QUEUED == "queued"
        assert STATUS_EXECUTING == "executing"
        assert STATUS_COMPLETED == "completed"


class TestToolExecution:
    def test_tool_use_block(self):
        block = ToolUseBlock(id="1", name="Bash", input={"command": "ls"})
        assert block.id == "1"
        assert block.name == "Bash"
        assert block.input["command"] == "ls"

    async def test_streaming_executor_init(self):
        from server.tools.file_read_tool import FileReadTool

        executor = StreamingToolExecutor(
            tool_definitions=[FileReadTool()],
            can_use_tool=lambda *a, **kw: True,
            tool_use_context=None,
        )
        assert executor is not None

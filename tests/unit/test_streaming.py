from __future__ import annotations

import pytest
from server.tools.streaming import (
    StreamingToolExecutor, TrackedTool, ToolUseBlock, AssistantMessage,
    STATUS_QUEUED, STATUS_EXECUTING, STATUS_COMPLETED, STATUS_YIELDED,
    AbortController, create_child_abort_controller,
)

class TestTrackedToolStates:
    def test_default_status_is_queued(self):
        block = ToolUseBlock(id="t1", name="Read", input={})
        am = AssistantMessage(uuid="msg1")
        tt = TrackedTool(id="t1", block=block, assistant_message=am)
        assert tt.status == STATUS_QUEUED
        assert tt.is_concurrency_safe is False

    def test_abort_controller_create_child(self):
        parent = AbortController()
        child = create_child_abort_controller(parent)
        assert child is not None
        assert child.parent is parent
        assert not child.aborted

    def test_abort_controller_signal(self):
        ac = AbortController()
        assert not ac.signal.is_set()
        ac.abort("user_interrupted")
        assert ac.aborted
        assert ac.reason == "user_interrupted"


class TestSyntheticErrorMessages:
    def _make_executor(self):
        class FakeContext:
            def __init__(self):
                self.abort_controller = None
        ctx = FakeContext()
        def allow(*a, **kw):
            return {"behavior": "allow"}
        return StreamingToolExecutor(tool_definitions=[], can_use_tool=allow, tool_use_context=ctx)

    def test_synthetic_error_user_interrupted(self):
        executor = self._make_executor()
        am = AssistantMessage(uuid="m1")
        msg = executor._create_synthetic_error_message("t1", "user_interrupted", am)
        assert msg is not None

    def test_synthetic_error_streaming_fallback(self):
        executor = self._make_executor()
        am = AssistantMessage(uuid="m1")
        msg = executor._create_synthetic_error_message("t1", "streaming_fallback", am)
        assert msg is not None

    def test_synthetic_error_sibling_error(self):
        executor = self._make_executor()
        am = AssistantMessage(uuid="m1")
        msg = executor._create_synthetic_error_message("t1", "sibling_error", am)
        assert msg is not None

    def test_get_abort_reason_none_by_default(self):
        executor = self._make_executor()
        block = ToolUseBlock(id="t1", name="Read", input={})
        am = AssistantMessage(uuid="msg1")
        tt = TrackedTool(id="t1", block=block, assistant_message=am)
        reason = executor._get_abort_reason(tt)
        assert reason is None

    def test_discard_unfinished_tools(self):
        executor = self._make_executor()
        executor.discard()
        assert executor._discarded is True

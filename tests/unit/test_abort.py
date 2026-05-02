from __future__ import annotations

import asyncio

import pytest

from server.utils.abort import AbortController


class TestAbortController:
    def test_not_aborted_initially(self):
        ctrl = AbortController()
        assert not ctrl.aborted

    def test_abort_sets_signal(self):
        ctrl = AbortController()
        ctrl.abort("test reason")
        assert ctrl.aborted
        assert ctrl.reason == "test reason"

    async def test_wait_blocks(self):
        ctrl = AbortController()
        task = asyncio.ensure_future(ctrl.wait())
        await asyncio.sleep(0.01)
        assert not task.done()

        ctrl.abort()
        await asyncio.wait_for(task, timeout=1.0)

    async def test_abort_signal(self):
        parent = AbortController()
        assert parent.signal is not None
        assert not parent.signal.is_set()
        parent.abort("parent reason")
        assert parent.aborted
        assert parent.signal.is_set()

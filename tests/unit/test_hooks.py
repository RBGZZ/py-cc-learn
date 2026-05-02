from __future__ import annotations

import pytest
from server.services.hooks import HookEventType, HookExecutionType


class TestHookTypes:
    def test_event_types_exist(self):
        events = [
            "PRE_TOOL_USE",
            "POST_TOOL_USE",
            "NOTIFICATION",
            "USER_PROMPT_SUBMIT",
            "SESSION_START",
            "SESSION_END",
            "STOP",
            "PRE_COMPACT",
            "POST_COMPACT",
        ]
        for evt in events:
            assert evt in HookEventType.__members__

    def test_hook_execution_types(self):
        types = ["COMMAND", "PROMPT", "HTTP", "CALLBACK"]
        for t in types:
            assert t in HookExecutionType.__members__

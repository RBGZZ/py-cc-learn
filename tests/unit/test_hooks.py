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


class TestHookRegistration:
    def test_register_task_hook_called(self):
        from server.engine.query_engine import QueryEngine, QueryEngineConfig
        calls = []
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        engine.register_task_hook(lambda ev, data: calls.append((ev, data)))
        engine._execute_task_completed_hooks()
        assert len(calls) == 1
        assert calls[0][0] == "task_completed"

    def test_register_teammate_hook_called(self):
        from server.engine.query_engine import QueryEngine, QueryEngineConfig
        calls = []
        engine = QueryEngine(QueryEngineConfig(tools=[], system_prompt="test"))
        engine.register_teammate_hook(lambda ev, data: calls.append((ev, data)))
        engine._execute_teammate_idle_hooks()
        assert len(calls) == 1
        assert calls[0][0] == "teammate_idle"


class TestMessagesEdgeCases:
    def test_normalize_empty_content_adds_placeholder(self):
        from server.engine.query_engine import QueryEngine
        msg = {"type": "user", "message": {"role": "user", "content": []}}
        normalized = QueryEngine._normalize_api_message(msg)
        content = normalized["message"]["content"]
        assert len(content) == 1
        assert content[0]["text"] == ""

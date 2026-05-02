from __future__ import annotations

import pytest
from server.models.tasks import (
    TaskStatus,
    TaskType,
    create_task_state_base,
    generate_task_id,
    is_terminal_task_status,
)


class TestTaskStateMachine:
    def test_pending_to_running(self):
        state = create_task_state_base("t1", TaskType.LOCAL_AGENT, "test")
        assert state.status == TaskStatus.PENDING
        assert not is_terminal_task_status(state.status)
        state.status = TaskStatus.RUNNING
        assert not is_terminal_task_status(state.status)

    def test_running_to_completed(self):
        state = create_task_state_base("t2", TaskType.LOCAL_AGENT, "test")
        state.status = TaskStatus.RUNNING
        state.status = TaskStatus.COMPLETED
        assert is_terminal_task_status(state.status)

    def test_terminal_cannot_reverse(self):
        state = create_task_state_base("t3", TaskType.LOCAL_AGENT, "test")
        state.status = TaskStatus.FAILED
        assert is_terminal_task_status(state.status)
        assert is_terminal_task_status(TaskStatus.KILLED)

    def test_generate_unique_ids(self):
        ids = {generate_task_id(TaskType.LOCAL_AGENT) for _ in range(20)}
        assert len(ids) >= 15

    def test_all_task_types_have_prefixes(self):
        for task_type in TaskType:
            task_id = generate_task_id(task_type)
            assert len(task_id) == 9
            assert task_id[0].isalpha()

    def test_create_task_state_base_fields(self):
        state = create_task_state_base(
            "test_id",
            TaskType.LOCAL_BASH,
            "Run a command",
            tool_use_id="tool_01",
        )
        data = state.model_dump()
        assert data["id"] == "test_id"
        assert data["type"] == "local_bash"
        assert data["status"] == "pending"
        assert data["description"] == "Run a command"
        assert data["tool_use_id"] == "tool_01"

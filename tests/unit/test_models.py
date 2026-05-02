from __future__ import annotations

import json

from server.models.messages import (
    AssistantMessage,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from server.models.tasks import (
    TaskStatus,
    TaskType,
    create_task_state_base,
    generate_task_id,
    is_terminal_task_status,
)


class TestMessages:
    def test_text_block(self):
        block = TextBlock(type="text", text="Hello world")
        assert block.type == "text"
        assert block.text == "Hello world"

    def test_tool_use_block(self):
        block = ToolUseBlock(id="tool_01", name="Bash", input={"command": "ls"})
        assert block.type == "tool_use"
        assert block.name == "Bash"
        assert block.input["command"] == "ls"

    def test_tool_result_block(self):
        block = ToolResultBlock(tool_use_id="tool_01", content="result")
        assert block.tool_use_id == "tool_01"
        assert not block.is_error

    def test_tool_result_error(self):
        block = ToolResultBlock(tool_use_id="tool_01", content="error", is_error=True)
        assert block.is_error

    def test_user_message_serialize(self):
        msg = UserMessage(role="user", content=[TextBlock(type="text", text="hello")])
        data = msg.model_dump()
        assert data["role"] == "user"
        assert isinstance(data["content"], list)

    def test_assistant_message_serialize(self):
        msg = AssistantMessage(role="assistant", content="Hello")
        data = msg.model_dump()
        assert data["role"] == "assistant"


class TestTasks:
    def test_task_types_exist(self):
        assert TaskType.LOCAL_BASH.value == "local_bash"
        assert TaskType.LOCAL_AGENT.value == "local_agent"
        assert TaskType.DREAM.value == "dream"

    def test_task_status_enum(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.KILLED.value == "killed"

    def test_is_terminal_status(self):
        assert is_terminal_task_status(TaskStatus.COMPLETED)
        assert is_terminal_task_status(TaskStatus.FAILED)
        assert is_terminal_task_status(TaskStatus.KILLED)
        assert not is_terminal_task_status(TaskStatus.PENDING)
        assert not is_terminal_task_status(TaskStatus.RUNNING)

    def test_generate_task_id(self):
        task_id = generate_task_id(TaskType.LOCAL_AGENT)
        assert task_id.startswith("a")
        assert len(task_id) == 9

        bash_id = generate_task_id(TaskType.LOCAL_BASH)
        assert bash_id.startswith("b")
        assert len(bash_id) == 9

    def test_create_task_state_base(self):
        state = create_task_state_base(
            task_id="a_test_01",
            task_type=TaskType.LOCAL_AGENT,
            description="Test task",
            tool_use_id="tool_01",
        )
        assert state.id == "a_test_01"
        assert state.type == TaskType.LOCAL_AGENT
        assert state.status == TaskStatus.PENDING
        assert state.description == "Test task"
        assert state.tool_use_id == "tool_01"

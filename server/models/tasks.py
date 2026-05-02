from __future__ import annotations

import os
import secrets
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

TASK_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
TASK_ID_PREFIXES: Dict[str, str] = {
    "local_bash": "b",
    "local_agent": "a",
    "remote_agent": "r",
    "in_process_teammate": "t",
    "local_workflow": "w",
    "monitor_mcp": "m",
    "dream": "d",
}


class TaskType(str, Enum):
    LOCAL_BASH = "local_bash"
    LOCAL_AGENT = "local_agent"
    REMOTE_AGENT = "remote_agent"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    LOCAL_WORKFLOW = "local_workflow"
    MONITOR_MCP = "monitor_mcp"
    DREAM = "dream"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


def is_terminal_task_status(status: TaskStatus) -> bool:
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED)


def generate_task_id(task_type: TaskType) -> str:
    prefix = TASK_ID_PREFIXES.get(task_type.value, "x")
    random_bytes = os.urandom(8)
    id_str = prefix
    for i in range(8):
        id_str += TASK_ID_ALPHABET[random_bytes[i] % len(TASK_ID_ALPHABET)]
    return id_str


class TaskStateBase(BaseModel):
    id: str
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    description: str
    tool_use_id: Optional[str] = None
    start_time: int = 0
    end_time: Optional[int] = None
    total_paused_ms: Optional[int] = None
    output_file: str = ""
    output_offset: int = 0
    notified: bool = False


def create_task_state_base(
    task_id: str,
    task_type: TaskType,
    description: str,
    tool_use_id: Optional[str] = None,
) -> TaskStateBase:
    import time

    return TaskStateBase(
        id=task_id,
        type=task_type,
        status=TaskStatus.PENDING,
        description=description,
        tool_use_id=tool_use_id,
        start_time=int(time.time() * 1000),
        output_file=f"/tmp/task_output_{task_id}.json",
        output_offset=0,
        notified=False,
    )


class TaskHandle(BaseModel):
    task_id: str
    cleanup: Optional[Any] = None


class TaskContext(BaseModel):
    abort_controller: Any = None
    app_state_getter: Any = None
    app_state_setter: Any = None

    class Config:
        arbitrary_types_allowed = True


class Task(BaseModel):
    name: str
    type: TaskType

    class Config:
        arbitrary_types_allowed = True


class LocalShellSpawnInput(BaseModel):
    command: str
    description: str
    timeout: Optional[int] = None
    tool_use_id: Optional[str] = None
    agent_id: Optional[str] = None
    kind: Optional[str] = None

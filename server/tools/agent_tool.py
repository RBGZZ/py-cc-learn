from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from server.models.tasks import (
    TaskStatus,
    TaskType,
    create_task_state_base,
    generate_task_id,
)
from server.models.tools import ValidationResult
from server.tools.tool import (
    PermissionResult,
    Tool,
    ToolCallResult,
)

SUBAGENT_TIMEOUT_MS = 300_000

_logger = logging.getLogger(__name__)

AGENT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "general-purpose": "General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you.",
    "Explore": 'Fast agent specialized for exploring codebases. Use this when you need to find files by patterns (eg. "src/components/**/*.tsx"), search code for keywords (eg. "API endpoints"), or answer questions about the codebase (eg. "how do API endpoints work?").',
    "Plan": "Fast agent specialized for planning tasks. Use this when you need to plan a task before executing it.",
    "verification": "Fast agent specialized for verifying that a task was completed successfully.",
}


class AgentInput(BaseModel):
    description: str = Field(description="A short (3-5 words) description of the task")
    prompt: str = Field(
        description="The task for the agent to perform (<= 30 words). Provide reasonable and clear requirements."
    )
    subagent_type: str = Field(
        default="general-purpose", description="The type of specialized agent to use for this task"
    )
    context: str | None = Field(
        default=None, description="Additional context to include in the agent's system prompt"
    )
    allowed_tools: list[str] | None = Field(
        default=None, description="List of tool names the agent is allowed to use"
    )
    disallowed_tools: list[str] | None = Field(
        default=None, description="List of tool names the agent is NOT allowed to use"
    )
    model: str | None = Field(default=None, description="Optional model override for the agent")


class AgentOutput(BaseModel):
    agent_id: str = Field(default="")
    task_id: str = Field(default="")
    result: str = Field(default="")
    status: str = Field(default="completed")
    tool_use_count: int = Field(default=0)
    elapsed_ms: float = Field(default=0)
    total_tokens: int = Field(default=0)
    prompt: str = Field(default="")
    content: list[dict[str, Any]] = Field(default_factory=list)


class SubagentContext:
    """Per-invocation context for a subagent run.
    TS reference: AgentTool.tsx runWithAgentContext() + createSubagentContext().
    """

    def __init__(
        self,
        parent_abort: asyncio.Event | None = None,
        allowed_tools: set[str] | None = None,
        disallowed_tools: set[str] | None = None,
        subagent_type: str = "general-purpose",
    ):
        self.abort_controller = asyncio.Event()
        self._parent_abort = parent_abort
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.subagent_type = subagent_type
        self._messages: list[dict[str, Any]] = []
        self._start_time = time.monotonic()

    @property
    def elapsed_ms(self) -> float:
        return (time.monotonic() - self._start_time) * 1000

    def abort(self) -> None:
        self.abort_controller.set()

    @property
    def is_aborted(self) -> bool:
        if self._parent_abort and self._parent_abort.is_set():
            return True
        return self.abort_controller.is_set()

    def filter_tools(self, tools: list[Any]) -> list[Any]:
        if self.allowed_tools is None and self.disallowed_tools is None:
            return list(tools)

        result: list[Any] = []
        for t in tools:
            name = getattr(t, "name", "")
            name_lower = name.lower()
            if self.disallowed_tools and name_lower in {n.lower() for n in self.disallowed_tools}:
                continue
            if self.allowed_tools and name_lower not in {n.lower() for n in self.allowed_tools}:
                continue
            result.append(t)
        return result

    def add_message(self, msg: dict[str, Any]) -> None:
        self._messages.append(msg)

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)


class AgentTool(Tool[AgentInput, AgentOutput, Any]):
    """AgentTool - delegates work to a subagent.
    Before using, the hosting engine must set _parent_tools and _parent_provider.
    TS reference: AgentTool.tsx call() assembles workerTools via assembleToolPool().
    """

    _parent_tools: list[Any] | None = None
    _parent_provider: Any = None

    @property
    def name(self) -> str:
        return "Agent"

    @property
    def input_schema(self) -> type[AgentInput]:
        return AgentInput

    @property
    def max_result_size_chars(self) -> int:
        return 100000

    @property
    def aliases(self) -> list[str] | None:
        return ["Task"]

    @property
    def search_hint(self) -> str | None:
        return "launch subagents for complex tasks"

    def is_concurrency_safe(self, input: AgentInput | None = None) -> bool:
        return True

    def is_read_only(self, input: AgentInput | None = None) -> bool:
        return True

    async def validate_input(self, input: AgentInput, context: Any) -> ValidationResult:
        errors: list[str] = []
        if not input.description or not input.description.strip():
            errors.append("description is required")
        if not input.prompt or not input.prompt.strip():
            errors.append("prompt is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def check_permissions(self, input: dict[str, Any], context: Any = None) -> PermissionResult:
        return PermissionResult(behavior="allow", updated_input=input)

    async def call(
        self, args: AgentInput, context: Any, can_use_tool: Any = None,
        parent_message: Any = None, on_progress: Any = None,
    ) -> ToolCallResult:
        task_id = generate_task_id(TaskType.LOCAL_AGENT)
        agent_id = str(uuid.uuid4())[:8]

        parent_abort = getattr(context, "abort_controller", None) if context else None
        if hasattr(parent_abort, "signal") and hasattr(parent_abort.signal, "is_set"):
            parent_abort = parent_abort.signal
        if not isinstance(parent_abort, asyncio.Event):
            parent_abort = None

        allowed = set(args.allowed_tools) if args.allowed_tools else None
        disallowed = set(args.disallowed_tools) if args.disallowed_tools else None

        subagent_ctx = SubagentContext(
            parent_abort=parent_abort, allowed_tools=allowed,
            disallowed_tools=disallowed, subagent_type=args.subagent_type,
        )

        task_state = create_task_state_base(
            task_id=task_id, task_type=TaskType.LOCAL_AGENT,
            description=args.description,
            tool_use_id=parent_message.get("uuid") if isinstance(parent_message, dict) else None,
        )
        task_state.status = TaskStatus.RUNNING

        try:
            result_dict = await self._run_subagent(args, subagent_ctx)
            task_state.status = TaskStatus.COMPLETED
            task_state.end_time = int(time.time() * 1000)

            output = AgentOutput(
                agent_id=agent_id, task_id=task_id,
                result=result_dict["result_text"],
                status=result_dict.get("status", "completed"),
                tool_use_count=result_dict["tool_use_count"],
                elapsed_ms=subagent_ctx.elapsed_ms,
                total_tokens=result_dict["total_tokens"],
                prompt=args.prompt, content=result_dict["content"],
            )
            return ToolCallResult(
                data=output,
                new_messages=[{"type": "text", "text": f"[Agent {agent_id}] {output.result}"}],
            )
        except asyncio.CancelledError:
            task_state.status = TaskStatus.KILLED
            return ToolCallResult(data=AgentOutput(
                agent_id=agent_id, task_id=task_id,
                result="Agent was cancelled by user", status="killed",
                elapsed_ms=subagent_ctx.elapsed_ms,
            ))
        except Exception as exc:
            task_state.status = TaskStatus.FAILED
            return ToolCallResult(data=AgentOutput(
                agent_id=agent_id, task_id=task_id,
                result=f"Agent failed: {exc}", status="failed",
                elapsed_ms=subagent_ctx.elapsed_ms,
            ))

    async def _run_subagent(self, args: AgentInput, ctx: SubagentContext) -> dict[str, Any]:
        parent_tools = getattr(self, "_parent_tools", None)
        if not parent_tools:
            return {
                "result_text": f"I would run the subagent of type '{args.subagent_type}' for task: '{args.prompt}'. Subagent execution requires the full query engine infrastructure.",
                "tool_use_count": 0, "total_tokens": 0, "status": "completed",
                "content": [{"type": "text", "text": AGENT_TYPE_DESCRIPTIONS.get(args.subagent_type, "")}],
            }

        from server.engine.query_engine import QueryEngine, QueryEngineConfig

        subagent_tools = ctx.filter_tools(parent_tools)
        if not subagent_tools:
            return {
                "result_text": f"No tools available for agent type '{args.subagent_type}'",
                "tool_use_count": 0, "total_tokens": 0, "status": "completed",
                "content": [{"type": "text", "text": f"No tools available"}],
            }

        prompt_parts = [
            AGENT_TYPE_DESCRIPTIONS.get(args.subagent_type, AGENT_TYPE_DESCRIPTIONS["general-purpose"]),
            "Complete the task fully — don't leave it half-done. When you complete the task, respond with a concise report.",
        ]
        if args.context:
            prompt_parts.append(f"Additional context: {args.context}")

        subagent_engine = QueryEngine(QueryEngineConfig(
            cwd=os.getcwd(), tools=subagent_tools,
            provider=getattr(self, "_parent_provider", None),
            system_prompt="\n".join(prompt_parts),
            max_turns=10, abort_signal=ctx.abort_controller,
        ))

        result_parts: list[str] = []
        tool_use_count = 0
        total_tokens = 0
        subagent_status = "completed"

        try:
            async with asyncio.timeout(SUBAGENT_TIMEOUT_MS / 1000):
                async for event in subagent_engine.submit_message(args.prompt):
                    if ctx.is_aborted:
                        result_parts.append("[aborted by user]")
                        subagent_status = "aborted"
                        break
                    event_type = event.get("type", "")
                    if event_type == "tool_use":
                        tool_use_count += 1
                    elif event_type == "text_delta":
                        result_parts.append(event.get("text", ""))
                    elif event_type == "error":
                        result_parts.append(f"[Error: {event.get('data', '')}]")
                        subagent_status = "error"
                        break
                    elif event_type == "result":
                        usage = event.get("usage", {})
                        total_tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
                        break
        except TimeoutError:
            result_parts.append(f"[timeout: subagent exceeded {SUBAGENT_TIMEOUT_MS / 1000:.0f}s limit]")
            subagent_status = "timeout"
            _logger.warning("Subagent timeout after %dms: %d tool uses", SUBAGENT_TIMEOUT_MS, tool_use_count)

        result_text = "".join(result_parts) if result_parts else "Task completed."
        return {
            "result_text": result_text, "tool_use_count": tool_use_count,
            "total_tokens": total_tokens, "status": subagent_status,
            "content": [{"type": "text", "text": result_text}] if result_text else [],
        }

    async def description(self, input: AgentInput, options: dict[str, Any]) -> str:
        return f"Launch {input.subagent_type} agent: {input.description}"

    async def prompt(self, options: dict[str, Any]) -> str:
        return "Launch subagents for complex multi-step tasks"

    def user_facing_name(self, input: dict[str, Any] | None = None) -> str:
        return "Agent"

    def to_auto_classifier_input(self, input: AgentInput) -> Any:
        return input.description

    def map_tool_result_to_tool_result_block_param(self, content: AgentOutput, tool_use_id: str) -> Any:
        if content.status == "completed":
            output_blocks: list[dict[str, Any]] = list(content.content) if content.content else []
            if not output_blocks:
                output_blocks.append({"type": "text", "text": "(Subagent completed but returned no output.)"})
            output_blocks.append({
                "type": "text", "text": (
                    f"<usage>total_tokens: {content.total_tokens}\ntool_uses: {content.tool_use_count}\nduration_ms: {int(content.elapsed_ms)}</usage>"
                ),
            })
            return {"type": "tool_result", "tool_use_id": tool_use_id, "content": output_blocks}
        return {
            "type": "tool_result", "tool_use_id": tool_use_id,
            "content": [{"type": "text", "text": content.result or f"Agent status: {content.status}"}],
        }

    def render_tool_use_message(self, input: dict[str, Any], options: dict[str, Any]) -> Any:
        return None

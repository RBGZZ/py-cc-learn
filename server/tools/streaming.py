from __future__ import annotations

import asyncio
import copy
import logging
import time
from collections.abc import AsyncGenerator, Callable, Generator
from dataclasses import dataclass, field
from typing import Any

from server.tools.tool import Tools, find_tool_by_name

BASH_TOOL_NAME = "Bash"

REJECT_MESSAGE = "User rejected tool use"

STATUS_QUEUED = "queued"
STATUS_EXECUTING = "executing"
STATUS_COMPLETED = "completed"
STATUS_YIELDED = "yielded"


class AbortController:
    """Python equivalent of TypeScript AbortController."""

    def __init__(self, parent: AbortController | None = None):
        self._event: asyncio.Event = asyncio.Event()
        self.reason: str | None = None
        self.parent: AbortController | None = parent

    @property
    def signal(self) -> asyncio.Event:
        return self._event

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    def abort(self, reason: str | None = None) -> None:
        self.reason = reason
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


def create_child_abort_controller(
    parent: AbortController | None,
) -> AbortController:
    """Source: abortController.ts createChildAbortController."""
    return AbortController(parent=parent)


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantMessage:
    uuid: str
    message: Any = None


@dataclass
class UserMessage:
    type: str = "user"
    message: Any = None
    tool_use_result: str = ""
    source_tool_assistant_uuid: str = ""


@dataclass
class ProgressMessage:
    type: str = "progress"
    data: Any = None


Message = Any
MessageUpdate = dict[str, Any]

ToolStatus = str


@dataclass
class TrackedTool:
    """Source: StreamingToolExecutor.ts L21-32."""

    id: str
    block: ToolUseBlock
    assistant_message: AssistantMessage
    status: ToolStatus = STATUS_QUEUED
    is_concurrency_safe: bool = False
    promise: asyncio.Task | None = None
    results: list[Message] | None = None
    pending_progress: list[Message] = field(default_factory=list)
    context_modifiers: list[Callable] | None = None


def _create_user_message(
    content: list[dict[str, Any]],
    tool_use_result: str,
    source_tool_assistant_uuid: str,
) -> UserMessage:
    """Source: messages.ts createUserMessage."""
    return UserMessage(
        type="user",
        message=UserMessageContent(type="user", content=content),
        tool_use_result=tool_use_result,
        source_tool_assistant_uuid=source_tool_assistant_uuid,
    )


class UserMessageContent:
    def __init__(self, type: str, content: list[dict[str, Any]]):
        self.type = type
        self.content = content


class StreamingToolExecutor:
    """
    Executes tools as they stream in with concurrency control.
    Source: StreamingToolExecutor.ts L40-529.

    - Concurrent-safe tools can execute in parallel with other concurrent-safe tools
    - Non-concurrent tools must execute alone (exclusive access)
    - Results are buffered and emitted in the order tools were received
    """

    def __init__(
        self,
        tool_definitions: Tools,
        can_use_tool: Callable,
        tool_use_context: Any,
    ):
        self._tool_definitions: Tools = tool_definitions
        self._can_use_tool: Callable = can_use_tool
        self._tool_use_context: Any = tool_use_context
        self._tools: list[TrackedTool] = []
        self._has_errored: bool = False
        self._errored_tool_description: str = ""
        self._discarded: bool = False
        self._progress_available_resolve: Callable[[], None] | None = None

        parent_abort = getattr(tool_use_context, "abort_controller", None)
        self._sibling_abort_controller: AbortController = create_child_abort_controller(
            parent_abort
        )

        self._run_tool_use_fn: Callable | None = None

    def set_run_tool_use_fn(self, fn: Callable) -> None:
        """
        Set the function used to run individual tool uses.
        Equivalent to the runToolUse import in StreamingToolExecutor.ts.
        The function must be an async generator yielding dicts with
        'message' (Message | None) and 'contextModifier' (optional).
        Source: toolExecution.ts runToolUse.
        """
        self._run_tool_use_fn = fn

    def _run_tool_use(
        self,
        block: ToolUseBlock,
        assistant_message: AssistantMessage,
        can_use_tool: Callable,
        tool_use_context: Any,
    ) -> Any:
        """Hook for running tool use. Must be set via set_run_tool_use_fn before tools execute."""
        if self._run_tool_use_fn is not None:
            return self._run_tool_use_fn(block, assistant_message, can_use_tool, tool_use_context)
        raise NotImplementedError("run_tool_use_fn must be set before tools execute")

    def discard(self) -> None:
        """
        Discards all pending and in-progress tools. Called when streaming fallback
        occurs and results from the failed attempt should be abandoned.
        Queued tools won't start, and in-progress tools will receive synthetic errors.
        Source: L69-71.
        """
        self._discarded = True

    def add_tool(self, block: ToolUseBlock, assistant_message: AssistantMessage) -> None:
        """
        Add a tool to the execution queue. Will start executing immediately if
        conditions allow.
        Source: L76-124.
        """
        tool_definition = find_tool_by_name(self._tool_definitions, block.name)
        if tool_definition is None:
            self._tools.append(
                TrackedTool(
                    id=block.id,
                    block=block,
                    assistant_message=assistant_message,
                    status=STATUS_COMPLETED,
                    is_concurrency_safe=True,
                    results=[
                        _create_user_message(
                            content=[
                                {
                                    "type": "tool_result",
                                    "content": f"<tool_use_error>Error: No such tool available: {block.name}</tool_use_error>",
                                    "is_error": True,
                                    "tool_use_id": block.id,
                                },
                            ],
                            tool_use_result=f"Error: No such tool available: {block.name}",
                            source_tool_assistant_uuid=assistant_message.uuid,
                        ),
                    ],
                )
            )
            return

        parsed_input = block.input
        is_concurrency_safe = False
        try:
            input_schema = tool_definition.input_schema
            if hasattr(input_schema, "model_validate"):
                parsed = input_schema.model_validate(block.input)
                is_concurrency_safe = bool(tool_definition.is_concurrency_safe(parsed))
            else:
                is_concurrency_safe = bool(tool_definition.is_concurrency_safe(parsed_input))
        except Exception:
            is_concurrency_safe = False

        self._tools.append(
            TrackedTool(
                id=block.id,
                block=block,
                assistant_message=assistant_message,
                status=STATUS_QUEUED,
                is_concurrency_safe=is_concurrency_safe,
            )
        )

        asyncio.create_task(self._process_queue())

    def _can_execute_tool(self, is_concurrency_safe: bool) -> bool:
        """
        Check if a tool can execute based on current concurrency state.
        Source: L129-135.
        """
        executing_tools = [t for t in self._tools if t.status == STATUS_EXECUTING]
        if not executing_tools:
            return True
        if is_concurrency_safe and all(t.is_concurrency_safe for t in executing_tools):
            return True
        return False

    async def _process_queue(self) -> None:
        """
        Process the queue, starting tools when concurrency conditions allow.
        Source: L140-151.
        """
        for tool in self._tools:
            if tool.status != STATUS_QUEUED:
                continue
            if self._can_execute_tool(tool.is_concurrency_safe):
                await self._execute_tool(tool)
            else:
                if not tool.is_concurrency_safe:
                    break

    def _get_tool_description(self, tool: TrackedTool) -> str:
        """
        Get a human-readable description of a tool for error messages.
        Source: L243-252.
        """
        input_data = tool.block.input
        summary = (
            input_data.get("command")
            or input_data.get("file_path")
            or input_data.get("pattern")
            or ""
        )
        if isinstance(summary, str) and len(summary) > 0:
            truncated = summary[:40] + "\u2026" if len(summary) > 40 else summary
            return f"{tool.block.name}({truncated})"
        return tool.block.name

    def _get_tool_interrupt_behavior(self, tool: TrackedTool) -> str:
        """Source: L233-241."""
        definition = find_tool_by_name(self._tool_definitions, tool.block.name)
        if definition is None:
            return "block"
        try:
            result = definition.interrupt_behavior()
            if result in ("cancel", "block"):
                return result
        except Exception:
            pass
        return "block"

    def _get_abort_reason(self, tool: TrackedTool) -> str | None:
        """
        Determine why a tool should be cancelled.
        Source: L210-231.
        """
        if self._discarded:
            return "streaming_fallback"
        if self._has_errored:
            return "sibling_error"

        parent_abort = getattr(self._tool_use_context, "abort_controller", None)
        if parent_abort is not None and parent_abort.aborted:
            if parent_abort.reason == "interrupt":
                behavior = self._get_tool_interrupt_behavior(tool)
                if behavior == "cancel":
                    return "user_interrupted"
                return None
            return "user_interrupted"
        return None

    def _create_synthetic_error_message(
        self,
        tool_use_id: str,
        reason: str,
        assistant_message: AssistantMessage,
    ) -> UserMessage:
        """
        Source: L153-205.
        """
        if reason == "user_interrupted":
            return _create_user_message(
                content=[
                    {
                        "type": "tool_result",
                        "content": f"<system-reminder>{REJECT_MESSAGE}</system-reminder>",
                        "is_error": True,
                        "tool_use_id": tool_use_id,
                    },
                ],
                tool_use_result="User rejected tool use",
                source_tool_assistant_uuid=assistant_message.uuid,
            )
        if reason == "streaming_fallback":
            return _create_user_message(
                content=[
                    {
                        "type": "tool_result",
                        "content": "<tool_use_error>Error: Streaming fallback - tool execution discarded</tool_use_error>",
                        "is_error": True,
                        "tool_use_id": tool_use_id,
                    },
                ],
                tool_use_result="Streaming fallback - tool execution discarded",
                source_tool_assistant_uuid=assistant_message.uuid,
            )
        desc = self._errored_tool_description
        msg = (
            f"Cancelled: parallel tool call {desc} errored"
            if desc
            else "Cancelled: parallel tool call errored"
        )
        return _create_user_message(
            content=[
                {
                    "type": "tool_result",
                    "content": f"<tool_use_error>{msg}</tool_use_error>",
                    "is_error": True,
                    "tool_use_id": tool_use_id,
                },
            ],
            tool_use_result=msg,
            source_tool_assistant_uuid=assistant_message.uuid,
        )

    def _update_interruptible_state(self) -> None:
        """Source: L254-260."""
        executing = [t for t in self._tools if t.status == STATUS_EXECUTING]
        set_has = getattr(self._tool_use_context, "set_has_interruptible_tool_in_progress", None)
        if set_has is not None:
            set_has(
                len(executing) > 0
                and all(self._get_tool_interrupt_behavior(t) == "cancel" for t in executing)
            )

    async def _execute_tool(self, tool: TrackedTool) -> None:
        """
        Execute a tool and collect its results.
        Source: L265-405.
        """
        tool.status = STATUS_EXECUTING

        set_in_progress = getattr(self._tool_use_context, "set_in_progress_tool_use_ids", None)
        if set_in_progress is not None:
            set_in_progress(lambda prev: set(prev) | {tool.id})

        self._update_interruptible_state()

        messages: list[Message] = []
        context_modifiers: list[Callable] = []

        async def collect_results() -> None:
            nonlocal messages, context_modifiers

            initial_abort_reason = self._get_abort_reason(tool)
            if initial_abort_reason is not None:
                messages.append(
                    self._create_synthetic_error_message(
                        tool.id,
                        initial_abort_reason,
                        tool.assistant_message,
                    )
                )
                tool.results = messages
                tool.context_modifiers = context_modifiers
                tool.status = STATUS_COMPLETED
                self._update_interruptible_state()
                return

            tool_abort_controller = create_child_abort_controller(self._sibling_abort_controller)

            async def on_abort() -> None:
                await tool_abort_controller.wait()
                parent_abort = getattr(self._tool_use_context, "abort_controller", None)
                if (
                    tool_abort_controller.reason != "sibling_error"
                    and parent_abort is not None
                    and not parent_abort.aborted
                    and not self._discarded
                ):
                    parent_abort.abort(tool_abort_controller.reason)

            abort_task = asyncio.create_task(on_abort())

            tool_start = time.perf_counter()

            try:
                this_tool_errored = False

                tool_context_with_abort = copy.copy(self._tool_use_context)
                tool_context_with_abort.abort_controller = tool_abort_controller

                async for update in self._run_tool_use(
                    tool.block,
                    tool.assistant_message,
                    self._can_use_tool,
                    tool_context_with_abort,
                ):
                    abort_reason = self._get_abort_reason(tool)
                    if abort_reason is not None and not this_tool_errored:
                        messages.append(
                            self._create_synthetic_error_message(
                                tool.id,
                                abort_reason,
                                tool.assistant_message,
                            )
                        )
                        break

                    update_message = update.get("message")
                    is_error_result = False
                    if update_message is not None:
                        msg_type = getattr(update_message, "type", None)
                        if msg_type == "user":
                            msg_inner = getattr(update_message, "message", None)
                            if msg_inner is not None:
                                content = getattr(msg_inner, "content", None)
                                if isinstance(content, list):
                                    is_error_result = any(
                                        isinstance(c, dict)
                                        and c.get("type") == "tool_result"
                                        and c.get("is_error") is True
                                        for c in content
                                    )

                    if is_error_result:
                        this_tool_errored = True
                        if tool.block.name == BASH_TOOL_NAME:
                            self._has_errored = True
                            self._errored_tool_description = self._get_tool_description(tool)
                            self._sibling_abort_controller.abort("sibling_error")
                        if tool.block.name == "bash" and hasattr(self, "_sibling_abort"):
                            self._sibling_abort.set()

                    if update_message is not None:
                        if getattr(update_message, "type", None) == "progress":
                            tool.pending_progress.append(update_message)
                            if self._progress_available_resolve is not None:
                                resolve = self._progress_available_resolve
                                self._progress_available_resolve = None
                                resolve()
                        else:
                            messages.append(update_message)

                    context_modifier = update.get("context_modifier")
                    if context_modifier is not None:
                        context_modifiers.append(context_modifier.get("modify_context"))

            except Exception:
                pass
            finally:
                tool_elapsed = time.perf_counter() - tool_start
                logger = logging.getLogger("streaming")
                logger.info("tool_executed", tool=tool.block.name, duration_ms=round(tool_elapsed * 1000, 1))
                abort_task.cancel()
                try:
                    await abort_task
                except asyncio.CancelledError:
                    pass

            tool.results = messages
            tool.context_modifiers = context_modifiers
            tool.status = STATUS_COMPLETED
            self._update_interruptible_state()

            if not tool.is_concurrency_safe and context_modifiers:
                for modifier in context_modifiers:
                    if modifier is not None:
                        self._tool_use_context = modifier(self._tool_use_context)

        tool.promise = asyncio.create_task(collect_results())

        async def on_done() -> None:
            try:
                await tool.promise
            except Exception:
                pass
            await self._process_queue()

        asyncio.create_task(on_done())

    def _has_pending_progress(self) -> bool:
        """Source: L445-447."""
        return any(len(t.pending_progress) > 0 for t in self._tools)

    def get_completed_results(self) -> Generator[MessageUpdate, None, None]:
        """
        Get any completed results that haven't been yielded yet (non-blocking).
        Maintains order where necessary.
        Also yields any pending progress messages immediately.
        Source: L412-439.
        """
        if self._discarded:
            return

        for tool in self._tools:
            while tool.pending_progress:
                progress_message = tool.pending_progress.pop(0)
                yield {
                    "message": progress_message,
                    "new_context": self._tool_use_context,
                    "is_progress": True,
                }

            if tool.status == STATUS_YIELDED:
                continue

            if tool.status == STATUS_COMPLETED and tool.results is not None:
                tool.status = STATUS_YIELDED

                for message in tool.results:
                    yield {
                        "message": message,
                        "new_context": self._tool_use_context,
                    }

                _mark_tool_use_as_complete(self._tool_use_context, tool.id)

            elif tool.status == STATUS_EXECUTING and not tool.is_concurrency_safe:
                break

    def _has_completed_results(self) -> bool:
        """Source: L495-497."""
        return any(t.status == STATUS_COMPLETED for t in self._tools)

    def _has_executing_tools(self) -> bool:
        """Source: L502-504."""
        return any(t.status == STATUS_EXECUTING for t in self._tools)

    def _has_unfinished_tools(self) -> bool:
        """Source: L509-511."""
        return any(t.status != STATUS_YIELDED for t in self._tools)

    async def get_remaining_results(self) -> AsyncGenerator[MessageUpdate, None]:
        """
        Wait for remaining tools and yield their results as they complete.
        Also yields progress messages as they become available.
        Source: L453-490.
        """
        if self._discarded:
            return

        while self._has_unfinished_tools():
            await self._process_queue()

            for result in self.get_completed_results():
                yield result

            if (
                self._has_executing_tools()
                and not self._has_completed_results()
                and not self._has_pending_progress()
            ):
                executing_tools = [
                    t for t in self._tools if t.status == STATUS_EXECUTING and t.promise is not None
                ]
                executing_promises = [t.promise for t in executing_tools]  # type: ignore

                progress_future: asyncio.Future = asyncio.get_event_loop().create_future()

                def _resolve_progress(_fut: asyncio.Future = progress_future) -> None:
                    if not _fut.done():
                        _fut.set_result(None)

                self._progress_available_resolve = _resolve_progress

                if executing_promises:
                    await asyncio.wait(
                        [asyncio.ensure_future(p) for p in executing_promises]
                        + [asyncio.ensure_future(progress_future)],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

        for result in self.get_completed_results():
            yield result

    def get_updated_context(self) -> Any:
        """
        Get the current tool use context (may have been modified by context modifiers).
        Source: L516-518.
        """
        return self._tool_use_context


def _mark_tool_use_as_complete(
    tool_use_context: Any,
    tool_use_id: str,
) -> None:
    """
    Source: L521-529.
    """
    set_in_progress = getattr(tool_use_context, "set_in_progress_tool_use_ids", None)
    if set_in_progress is not None:
        set_in_progress(lambda prev: set(prev) - {tool_use_id})

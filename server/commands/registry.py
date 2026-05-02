from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

CommandType = Literal["local", "local-jsx", "prompt"]
CommandResultDisplay = Literal["skip", "system", "user"]


@dataclass
class LocalCommandResult:
    type: Literal["text", "compact", "skip"]
    value: str | None = None
    display_text: str | None = None
    compaction_result: dict[str, Any] | None = None


@dataclass
class Command:
    name: str
    type: CommandType
    description: str
    aliases: list[str] = field(default_factory=list)
    argument_hint: str | None = None
    is_enabled: Callable[[], bool] | None = None
    is_hidden: bool = False
    source: str = "builtin"
    loaded_from: str | None = None
    kind: str | None = None
    immediate: bool = False
    is_sensitive: bool = False
    supports_non_interactive: bool = False
    user_facing_name: Callable[[], str] | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    when_to_use: str | None = None
    availability: list[str] | None = None
    plugin_info: dict[str, Any] | None = None
    version: str | None = None
    has_user_specified_description: bool = False
    is_mcp: bool = False
    arg_names: list[str] | None = None
    progress_message: str = ""
    content_length: int = 0
    allowed_tools: list[str] | None = None
    model: str | None = None

    execute: Callable[..., Any] | None = None
    get_prompt: Callable[..., Any] | None = None
    load: Callable[..., Any] | None = None

    def get_command_name(self) -> str:
        if self.user_facing_name is not None:
            return self.user_facing_name()
        return self.name

    def check_enabled(self) -> bool:
        if self.is_enabled is not None:
            return self.is_enabled()
        return True


class CommandRegistry:
    _instance: CommandRegistry | None = None

    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._register_core_commands()

    @classmethod
    def get_instance(cls) -> CommandRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, command: Command) -> None:
        self._commands[command.name] = command
        for alias in command.aliases:
            if alias not in self._commands:
                self._commands[alias] = command

    def unregister(self, name: str) -> None:
        cmd = self._commands.pop(name, None)
        if cmd is not None:
            for alias in cmd.aliases:
                self._commands.pop(alias, None)

    def find_command(self, command_name: str) -> Command | None:
        return self._commands.get(command_name)

    def has_command(self, command_name: str) -> bool:
        return command_name in self._commands

    def get_commands(self) -> list[Command]:
        seen: set[str] = set()
        result: list[Command] = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        return sorted(result, key=lambda c: c.name)

    def get_visible_commands(self) -> list[Command]:
        return [c for c in self.get_commands() if not c.is_hidden and c.check_enabled()]

    def get_user_invocable_commands(self) -> list[Command]:
        return [c for c in self.get_visible_commands() if c.user_invocable and not c.is_mcp]

    def get_prompt_commands(self) -> list[Command]:
        return [c for c in self.get_commands() if c.type == "prompt"]

    def _register_core_commands(self) -> None:
        self.register(
            Command(
                name="help",
                type="local",
                description="Show help and available commands",
                execute=_cmd_help,
            )
        )

        self.register(
            Command(
                name="clear",
                type="local",
                description="Clear conversation history and free up context",
                aliases=["reset", "new"],
                execute=_cmd_clear,
            )
        )

        self.register(
            Command(
                name="cost",
                type="local",
                description="Show the total cost and duration of the current session",
                supports_non_interactive=True,
                execute=_cmd_cost,
                is_enabled=lambda: True,
            )
        )

        self.register(
            Command(
                name="stats",
                type="local",
                description="Show your Claude Code usage statistics and activity",
                execute=_cmd_stats,
            )
        )

        self.register(
            Command(
                name="resume",
                type="local",
                description="Resume a previous conversation",
                aliases=["continue"],
                argument_hint="[conversation id or search term]",
                execute=_cmd_resume,
            )
        )

        self.register(
            Command(
                name="model",
                type="local",
                description="Set the AI model for Claude Code",
                argument_hint="[model]",
                execute=_cmd_model,
            )
        )


async def _cmd_help(args: str, context: dict[str, Any] | None = None) -> LocalCommandResult:
    registry = CommandRegistry.get_instance()
    commands = registry.get_visible_commands()
    lines = []
    for cmd in commands:
        aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"/{cmd.name}{aliases_str} - {cmd.description}")
    return LocalCommandResult(type="text", value="\n".join(lines))


async def _cmd_model(args: str, context: dict[str, Any] | None = None) -> LocalCommandResult:
    from server.state.global_state import GlobalState

    gs = GlobalState.get_instance()
    if args.strip():
        gs.set_main_loop_model_override({"model": args.strip()})
        return LocalCommandResult(type="text", value=f"Model set to: {args.strip()}")
    override = gs.get_main_loop_model_override()
    if override and "model" in override:
        return LocalCommandResult(type="text", value=f"Current model: {override['model']}")
    initial = gs.get_initial_main_loop_model()
    if initial and "model" in initial:
        return LocalCommandResult(type="text", value=f"Current model: {initial['model']}")
    return LocalCommandResult(type="text", value="Current model: unknown")


async def _cmd_clear(args: str, context: dict[str, Any] | None = None) -> LocalCommandResult:
    from server.state.global_state import GlobalState

    gs = GlobalState.get_instance()
    gs.reset_cost_state()
    return LocalCommandResult(type="text", value="Conversation cleared.")


async def _cmd_cost(args: str, context: dict[str, Any] | None = None) -> LocalCommandResult:
    from server.state.global_state import GlobalState

    gs = GlobalState.get_instance()
    total_cost = gs.get_total_cost_usd()
    duration_sec = gs.get_total_duration()
    lines = [
        f"Total cost: ${total_cost:.4f}",
        f"Session duration: {duration_sec:.1f}s",
    ]
    return LocalCommandResult(type="text", value="\n".join(lines))


async def _cmd_stats(args: str, context: dict[str, Any] | None = None) -> LocalCommandResult:
    from server.state.global_state import GlobalState

    gs = GlobalState.get_instance()
    input_tokens = gs.get_total_input_tokens()
    output_tokens = gs.get_total_output_tokens()
    model_usage = gs.get_model_usage()
    lines = [
        f"Total input tokens: {input_tokens}",
        f"Total output tokens: {output_tokens}",
        f"Total cost: ${gs.get_total_cost_usd():.4f}",
    ]
    if model_usage:
        lines.append("Model usage:")
        for model_name, usage_data in model_usage.items():
            count = usage_data.get("count", 0) if isinstance(usage_data, dict) else usage_data
            lines.append(f"  {model_name}: {count} requests")
    return LocalCommandResult(type="text", value="\n".join(lines))


async def _cmd_resume(args: str, context: dict[str, Any] | None = None) -> LocalCommandResult:
    if args.strip():
        session_id = args.strip()
        return LocalCommandResult(
            type="text",
            value=(
                f'To resume session "{session_id}", use --resume "{session_id}" '
                f"at CLI launch, or POST /api/v1/resume with session_id={session_id}."
            ),
        )
    return LocalCommandResult(
        type="text",
        value="Provide a session ID to resume: /resume <session_id>",
    )


def get_registry() -> CommandRegistry:
    return CommandRegistry.get_instance()


def find_command(command_name: str) -> Command | None:
    return CommandRegistry.get_instance().find_command(command_name)


def has_command(command_name: str) -> bool:
    return CommandRegistry.get_instance().has_command(command_name)


def get_commands() -> list[Command]:
    return CommandRegistry.get_instance().get_commands()

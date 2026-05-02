from __future__ import annotations

from server.commands.registry import CommandRegistry


def handle_slash_command(text: str) -> dict[str, str | None] | None:
    if not text or not text.startswith("/"):
        return None

    parts = text.strip().split(" ", 1)
    command_name = parts[0][1:]
    args = parts[1] if len(parts) > 1 else ""

    registry = CommandRegistry.get_instance()
    cmd = registry.find_command(command_name)
    if cmd is None:
        return None

    return {
        "command": command_name,
        "args": args,
        "type": cmd.type,
    }


def is_slash_command(text: str) -> bool:
    return text.strip().startswith("/")


def dispatch_command(command_text: str) -> dict[str, str | None] | None:
    return handle_slash_command(command_text)

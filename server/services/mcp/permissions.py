"""MCP Channel Permissions - per-server allowlist/denylist control."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpChannelPermissions:
    allowlist: list[str] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)

    def is_allowed(self, tool_name: str) -> bool:
        if self.allowlist:
            return tool_name in self.allowlist
        if self.denylist:
            return tool_name not in self.denylist
        return True

    def filter_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [t for t in tools if self.is_allowed(t.get("name", ""))]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "McpChannelPermissions":
        allowlist = config.get("channelAllowlist", [])
        denylist = config.get("channelDenylist", [])
        if isinstance(allowlist, str):
            allowlist = [allowlist]
        if isinstance(denylist, str):
            denylist = [denylist]
        return cls(allowlist=list(allowlist), denylist=list(denylist))

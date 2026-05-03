from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

MCP_TOOL_PREFIX = "mcp__"
MCP_TOOL_SEPARATOR = "__"

TransportType = Literal["stdio", "sse", "http", "ws", "sdk"]
ConfigScope = Literal["local", "user", "project", "dynamic", "enterprise", "claudeai", "managed"]
ServerConnectionType = Literal["connected", "failed", "needs-auth", "pending", "disabled"]


class McpStdioServerConfig(BaseModel):
    type: Literal["stdio"] = "stdio"
    command: str = Field(..., min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None


class McpOAuthConfig(BaseModel):
    client_id: str | None = None
    callback_port: int | None = None
    auth_server_metadata_url: str | None = None
    xaa: bool = False


class McpSSEServerConfig(BaseModel):
    type: Literal["sse"] = "sse"
    url: str
    headers: dict[str, str] | None = None
    headers_helper: str | None = None
    oauth: McpOAuthConfig | None = None


class McpHTTPServerConfig(BaseModel):
    type: Literal["http"] = "http"
    url: str
    headers: dict[str, str] | None = None
    headers_helper: str | None = None
    oauth: McpOAuthConfig | None = None


class McpWebSocketServerConfig(BaseModel):
    type: Literal["ws"] = "ws"
    url: str
    headers: dict[str, str] | None = None
    headers_helper: str | None = None


class McpSdkServerConfig(BaseModel):
    type: Literal["sdk"] = "sdk"
    name: str


McpServerConfig = (
    McpStdioServerConfig
    | McpSSEServerConfig
    | McpHTTPServerConfig
    | McpWebSocketServerConfig
    | McpSdkServerConfig
)


@dataclass
class ScopedMcpServerConfig:
    config: McpServerConfig
    scope: ConfigScope
    plugin_source: str | None = None


@dataclass
class McpTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    original_tool_name: str = ""
    server_name: str = ""
    is_mcp: bool = True

    @property
    def full_name(self) -> str:
        return format_mcp_tool_name(self.server_name, self.original_tool_name or self.name)


@dataclass
class McpServerConnection:
    name: str
    type: ServerConnectionType
    config: ScopedMcpServerConfig
    server_info: dict[str, str] | None = None
    capabilities: dict[str, Any] | None = None
    instructions: str | None = None
    error: str | None = None
    reconnect_attempt: int = 0
    max_reconnect_attempts: int = 3
    tools: list[McpTool] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)


def format_mcp_tool_name(server_name: str, tool_name: str) -> str:
    return f"{MCP_TOOL_PREFIX}{server_name}{MCP_TOOL_SEPARATOR}{tool_name}"


def parse_mcp_tool_name(full_name: str) -> tuple[str, str] | None:
    if not full_name.startswith(MCP_TOOL_PREFIX):
        return None
    rest = full_name[len(MCP_TOOL_PREFIX) :]
    parts = rest.split(MCP_TOOL_SEPARATOR, 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def normalize_name_for_mcp(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    if name.startswith("claude.ai "):
        normalized = re.sub(r"_+", "_", normalized)
        normalized = normalized.strip("_")
    return normalized

"""MCP Connection Manager - manages lifecycle of multiple MCP server connections."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from server.services.mcp.types import (
    McpServerConfig,
    McpServerConnection,
    McpStdioServerConfig,
    McpSSEServerConfig,
    McpHTTPServerConfig,
    McpTool,
    ScopedMcpServerConfig,
    ServerConnectionType,
    format_mcp_tool_name,
)
from server.services.mcp.transport import BaseMcpClient, HttpMcpClient, SseMcpClient, StdioMcpClient

logger = logging.getLogger(__name__)

MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_BASE_DELAY = 1.0


def create_client(config: McpServerConfig, server_name: str) -> BaseMcpClient:
    if isinstance(config, McpStdioServerConfig):
        return StdioMcpClient(config, server_name)
    elif isinstance(config, McpSSEServerConfig):
        return SseMcpClient(config, server_name)
    elif isinstance(config, McpHTTPServerConfig):
        return HttpMcpClient(config, server_name)
    raise ValueError(f"Unsupported MCP config type: {type(config)}")


class McpConnectionManager:

    def __init__(self):
        self._connections: dict[str, McpServerConnection] = {}
        self._clients: dict[str, BaseMcpClient] = {}
        self._server_configs: dict[str, ScopedMcpServerConfig] = {}

    def add_server(self, name: str, config: McpServerConfig, scope: str = "user"):
        self._server_configs[name] = ScopedMcpServerConfig(config=config, scope=scope)

    async def connect_all(self) -> list[McpServerConnection]:
        tasks = []
        for name, scoped_config in self._server_configs.items():
            tasks.append(self._connect_server(name, scoped_config))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        connections = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"MCP connect error: {result}")
            elif isinstance(result, McpServerConnection):
                connections.append(result)
        return connections

    async def _connect_server(self, name: str, scoped_config: ScopedMcpServerConfig) -> McpServerConnection:
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            try:
                client = create_client(scoped_config.config, name)
                connection = await client.connect()
                if connection.type == "connected":
                    self._clients[name] = client
                    self._connections[name] = connection
                    tools = await self._fetch_tools(client, name)
                    connection.tools = tools
                    return connection
                else:
                    if attempt < MAX_RECONNECT_ATTEMPTS - 1:
                        delay = RECONNECT_BASE_DELAY * (2 ** attempt)
                        await asyncio.sleep(delay)
                    else:
                        return connection
            except Exception as e:
                if attempt < MAX_RECONNECT_ATTEMPTS - 1:
                    delay = RECONNECT_BASE_DELAY * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    return McpServerConnection(
                        name=name, type="failed",
                        config=scoped_config, error=str(e),
                    )
        return McpServerConnection(
            name=name, type="failed",
            config=scoped_config, error="Max reconnect attempts exceeded",
        )

    async def _fetch_tools(self, client: BaseMcpClient, server_name: str) -> list[McpTool]:
        try:
            result = await client.send_request("tools/list", timeout=10.0)
            raw_tools = result.get("tools", [])
            tools = []
            for t in raw_tools:
                tools.append(McpTool(
                    name=format_mcp_tool_name(server_name, t.get("name", "")),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    original_tool_name=t.get("name", ""),
                    server_name=server_name,
                    is_mcp=True,
                ))
            return tools
        except Exception:
            return []

    def list_tools(self) -> list[McpTool]:
        all_tools = []
        for conn in self._connections.values():
            if conn.type == "connected":
                all_tools.extend(conn.tools)
        return all_tools

    def get_client(self, name: str) -> BaseMcpClient | None:
        return self._clients.get(name)

    async def call_tool(self, full_name: str, arguments: dict) -> Any:
        from server.services.mcp.types import parse_mcp_tool_name
        parsed = parse_mcp_tool_name(full_name)
        if not parsed:
            raise ValueError(f"Invalid MCP tool name: {full_name}")
        server_name, tool_name = parsed
        client = self._clients.get(server_name)
        if not client:
            raise ValueError(f"MCP server not connected: {server_name}")
        result = await client.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        return result

    async def close_all(self):
        for name, client in list(self._clients.items()):
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()
        self._connections.clear()

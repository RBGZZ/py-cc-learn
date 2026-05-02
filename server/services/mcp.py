from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
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


class _JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class _JsonRpcRequest:
    def __init__(
        self, method: str, params: dict[str, Any] | None = None, request_id: str | int | None = None
    ):
        self.jsonrpc = "2.0"
        self.method = method
        self.params = params or {}
        self.id = request_id if request_id is not None else str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            result["params"] = self.params
        if self.id is not None:
            result["id"] = self.id
        return result


class _JsonRpcNotification:
    def __init__(self, method: str, params: dict[str, Any] | None = None):
        self.jsonrpc = "2.0"
        self.method = method
        self.params = params or {}

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            result["params"] = self.params
        return result


def _parse_json_rpc_response(data: dict[str, Any]) -> dict[str, Any]:
    if "error" in data:
        err = data["error"]
        raise _JsonRpcError(
            code=err.get("code", -1),
            message=err.get("message", "Unknown error"),
            data=err.get("data"),
        )
    if "result" not in data:
        raise _JsonRpcError(code=-1, message="Invalid JSON-RPC response: missing result")
    return data["result"]


STDIO_CONNECT_TIMEOUT = 30.0
STDIO_READ_TIMEOUT = 10.0
STDIO_SHUTDOWN_TIMEOUT = 5.0
STDIO_MAX_BUFFER = 10 * 1024 * 1024


class StdioMcpClient:
    def __init__(self, config: McpStdioServerConfig, server_name: str):
        self._config = config
        self._server_name = server_name
        self._process: subprocess.Popen[bytes] | None = None
        self._reader_task: asyncio.Task[Any] | None = None
        self._pending: dict[str | int, asyncio.Future[dict[str, Any]]] = {}
        self._buffer = b""
        self._closed = False
        self._lock = asyncio.Lock()
        self._initialized = False
        self._server_info: dict[str, str] | None = None
        self._capabilities: dict[str, Any] | None = None
        self._instructions: str | None = None

    async def connect(self) -> McpServerConnection:
        env = os.environ.copy()
        if self._config.env:
            env.update(self._config.env)

        try:
            self._process = await asyncio.create_subprocess_exec(
                self._config.command,
                *self._config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except Exception as e:
            return McpServerConnection(
                name=self._server_name,
                type="failed",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                error=str(e),
            )

        self._reader_task = asyncio.create_task(self._read_loop())

        init_result = await self._initialize()
        if init_result.type == "failed":
            return init_result

        return McpServerConnection(
            name=self._server_name,
            type="connected",
            config=ScopedMcpServerConfig(config=self._config, scope="user"),
            server_info=self._server_info,
            capabilities=self._capabilities,
            instructions=self._instructions,
        )

    async def _initialize(self) -> McpServerConnection:
        try:
            result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "py-cc-learn",
                        "version": "0.1.0",
                    },
                },
                timeout=STDIO_CONNECT_TIMEOUT,
            )
            self._initialized = True
            self._server_info = result.get("serverInfo")
            self._capabilities = result.get("capabilities", {})
            self._instructions = result.get("instructions")

            notification = _JsonRpcNotification("notifications/initialized")
            await self._send_raw(json.dumps(notification.to_dict()))

            return McpServerConnection(
                name=self._server_name,
                type="connected",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                server_info=self._server_info,
                capabilities=self._capabilities,
                instructions=self._instructions,
            )
        except Exception as e:
            return McpServerConnection(
                name=self._server_name,
                type="failed",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                error=str(e),
            )

    async def _send_request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = STDIO_READ_TIMEOUT
    ) -> dict[str, Any]:
        request = _JsonRpcRequest(method=method, params=params)
        return await self._send_and_wait(request.to_dict(), timeout)

    async def _send_and_wait(self, request_dict: dict[str, Any], timeout: float) -> dict[str, Any]:
        request_id = request_dict["id"]
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending[request_id] = future

        await self._send_raw(json.dumps(request_dict))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending.pop(request_id, None)
            raise _JsonRpcError(code=-1, message=f"Request timed out after {timeout}s")

    async def _send_raw(self, data: str) -> None:
        if self._process is None or self._process.stdin is None:
            raise _JsonRpcError(code=-1, message="Process not connected")
        async with self._lock:
            raw = (data + "\n").encode("utf-8")
            self._process.stdin.write(raw)
            await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        try:
            while not self._closed:
                try:
                    chunk = await asyncio.wait_for(self._process.stdout.read(8192), timeout=60.0)
                except TimeoutError:
                    continue
                if not chunk:
                    break
                self._buffer += chunk
                if len(self._buffer) > STDIO_MAX_BUFFER:
                    self._buffer = self._buffer[-STDIO_MAX_BUFFER:]
                self._process_buffer()
        except Exception:
            pass

    def _process_buffer(self) -> None:
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            self._handle_message(data)

    def _handle_message(self, data: dict[str, Any]) -> None:
        msg_id = data.get("id")
        if msg_id is not None and msg_id in self._pending:
            if "error" in data:
                self._pending[msg_id].set_exception(
                    _JsonRpcError(
                        code=data["error"].get("code", -1),
                        message=data["error"].get("message", "Unknown error"),
                        data=data["error"].get("data"),
                    )
                )
            else:
                self._pending[msg_id].set_result(data.get("result", {}))
            self._pending.pop(msg_id, None)

    async def list_tools(self) -> list[McpTool]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        result = await self._send_request("tools/list")
        tools_data = result.get("tools", [])
        mcp_tools: list[McpTool] = []
        for td in tools_data:
            mcp_tools.append(
                McpTool(
                    name=td.get("name", ""),
                    description=td.get("description", ""),
                    input_schema=td.get("inputSchema", {}),
                    original_tool_name=td.get("name", ""),
                    server_name=self._server_name,
                )
            )
        return mcp_tools

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )
        return result

    async def list_resources(self) -> list[dict[str, Any]]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        try:
            result = await self._send_request("resources/list")
            return result.get("resources", [])
        except Exception:
            return []

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        return await self._send_request("resources/read", {"uri": uri})

    async def close(self) -> None:
        self._closed = True
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._process is not None:
            if self._process.stdin is not None:
                try:
                    self._process.stdin.close()
                except Exception:
                    pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=STDIO_SHUTDOWN_TIMEOUT)
            except TimeoutError:
                try:
                    self._process.kill()
                    await self._process.wait()
                except Exception:
                    pass
            self._process = None


SSE_CONNECT_TIMEOUT = 30.0
SSE_READ_TIMEOUT = 60.0


class SSEMcpClient:
    def __init__(self, config: McpSSEServerConfig, server_name: str):
        self._config = config
        self._server_name = server_name
        self._http_client: httpx.AsyncClient | None = None
        self._message_endpoint: str | None = None
        self._session_id: str | None = None
        self._pending: dict[str | int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[Any] | None = None
        self._closed = False
        self._initialized = False
        self._server_info: dict[str, str] | None = None
        self._capabilities: dict[str, Any] | None = None
        self._instructions: str | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def connect(self) -> McpServerConnection:
        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if self._config.headers:
            headers.update(self._config.headers)

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(SSE_CONNECT_TIMEOUT),
            headers=headers,
        )

        try:
            self._reader_task = asyncio.create_task(self._sse_read_loop())

            event = await asyncio.wait_for(self._event_queue.get(), timeout=SSE_CONNECT_TIMEOUT)

            if event.get("event") == "endpoint":
                self._message_endpoint = event.get("data", "").strip()

                if not self._message_endpoint:
                    return McpServerConnection(
                        name=self._server_name,
                        type="failed",
                        config=ScopedMcpServerConfig(config=self._config, scope="user"),
                        error="SSE endpoint event missing message endpoint URL",
                    )

                if self._message_endpoint.startswith("/"):
                    base = self._config.url.rstrip("/")
                    self._message_endpoint = f"{base}{self._message_endpoint}"

                init_result = await self._initialize()
                return init_result

            return McpServerConnection(
                name=self._server_name,
                type="failed",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                error=f"Expected endpoint event, got: {event.get('event')}",
            )

        except TimeoutError:
            return McpServerConnection(
                name=self._server_name,
                type="failed",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                error="SSE connection timed out waiting for endpoint event",
            )
        except Exception as e:
            return McpServerConnection(
                name=self._server_name,
                type="failed",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                error=str(e),
            )

    async def _initialize(self) -> McpServerConnection:
        if self._message_endpoint is None:
            return McpServerConnection(
                name=self._server_name,
                type="failed",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                error="No message endpoint",
            )

        try:
            result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "py-cc-learn",
                        "version": "0.1.0",
                    },
                },
            )
            self._initialized = True
            self._server_info = result.get("serverInfo")
            self._capabilities = result.get("capabilities", {})
            self._instructions = result.get("instructions")

            notification = _JsonRpcNotification("notifications/initialized")
            await self._send_raw(notification.to_dict())

            return McpServerConnection(
                name=self._server_name,
                type="connected",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                server_info=self._server_info,
                capabilities=self._capabilities,
                instructions=self._instructions,
            )
        except Exception as e:
            return McpServerConnection(
                name=self._server_name,
                type="failed",
                config=ScopedMcpServerConfig(config=self._config, scope="user"),
                error=str(e),
            )

    async def _send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        request = _JsonRpcRequest(method=method, params=params)
        return await self._send_and_wait(request.to_dict(), SSE_READ_TIMEOUT)

    async def _send_and_wait(self, request_dict: dict[str, Any], timeout: float) -> dict[str, Any]:
        request_id = request_dict["id"]
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending[request_id] = future

        await self._send_raw(request_dict)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending.pop(request_id, None)
            raise _JsonRpcError(code=-1, message=f"Request timed out after {timeout}s")

    async def _send_raw(self, data: dict[str, Any]) -> None:
        if self._http_client is None or self._message_endpoint is None:
            raise _JsonRpcError(code=-1, message="Not connected")
        response = await self._http_client.post(
            self._message_endpoint,
            json=data,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            result = response.json()
            self._handle_message(result)

    async def _sse_read_loop(self) -> None:
        if self._http_client is None:
            return
        try:
            async with self._http_client.stream("GET", self._config.url) as response:
                response.raise_for_status()
                buffer = ""
                current_event: dict[str, str] = {}
                async for line in response.aiter_lines():
                    if self._closed:
                        break
                    if line == "":
                        if current_event:
                            event_type = current_event.get("event", "message")
                            event_data = current_event.get("data", "")
                            if event_type == "message":
                                self._handle_json_line(event_data)
                            else:
                                self._event_queue.put_nowait(
                                    {"event": event_type, "data": event_data}
                                )
                            current_event = {}
                        continue
                    if line.startswith("event:"):
                        current_event["event"] = line[6:].strip()
                    elif line.startswith("data:"):
                        data_val = line[5:].strip()
                        current_event["data"] = current_event.get("data", "") + data_val
                    elif ":" not in line:
                        continue
        except Exception:
            pass

    def _handle_json_line(self, data: str) -> None:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return
        if isinstance(parsed, dict):
            self._handle_message(parsed)

    def _handle_message(self, data: dict[str, Any]) -> None:
        msg_id = data.get("id")
        if msg_id is not None and msg_id in self._pending:
            if "error" in data:
                self._pending[msg_id].set_exception(
                    _JsonRpcError(
                        code=data["error"].get("code", -1),
                        message=data["error"].get("message", "Unknown error"),
                        data=data["error"].get("data"),
                    )
                )
            else:
                self._pending[msg_id].set_result(data.get("result", {}))
            self._pending.pop(msg_id, None)

    async def list_tools(self) -> list[McpTool]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        result = await self._send_request("tools/list")
        tools_data = result.get("tools", [])
        mcp_tools: list[McpTool] = []
        for td in tools_data:
            mcp_tools.append(
                McpTool(
                    name=td.get("name", ""),
                    description=td.get("description", ""),
                    input_schema=td.get("inputSchema", {}),
                    original_tool_name=td.get("name", ""),
                    server_name=self._server_name,
                )
            )
        return mcp_tools

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )
        return result

    async def list_resources(self) -> list[dict[str, Any]]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        try:
            result = await self._send_request("resources/list")
            return result.get("resources", [])
        except Exception:
            return []

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if not self._initialized:
            raise _JsonRpcError(code=-1, message="Client not initialized")
        return await self._send_request("resources/read", {"uri": uri})

    async def close(self) -> None:
        self._closed = True
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None


async def connect_to_server(
    server_name: str, config: McpServerConfig, scope: ConfigScope = "user"
) -> McpServerConnection:
    if isinstance(config, McpStdioServerConfig):
        client = StdioMcpClient(config, server_name)
        return await client.connect()
    elif isinstance(config, McpSSEServerConfig):
        client = SSEMcpClient(config, server_name)
        return await client.connect()
    else:
        return McpServerConnection(
            name=server_name,
            type="failed",
            config=ScopedMcpServerConfig(config=config, scope=scope),
            error=f"Unsupported transport type: {type(config).__name__}",
        )


async def load_mcp_configs(project_root: str | None = None) -> dict[str, ScopedMcpServerConfig]:
    result: dict[str, ScopedMcpServerConfig] = {}

    search_paths: list[tuple[str, ConfigScope]] = []

    home = os.path.expanduser("~")

    user_config_path = os.path.join(home, ".claude", "mcp.json")
    if os.path.isfile(user_config_path):
        search_paths.append((user_config_path, "user"))

    local_config_path = os.path.join(home, ".claude", "local", "mcp.json")
    if os.path.isfile(local_config_path):
        search_paths.append((local_config_path, "local"))

    if project_root:
        project_config_path = os.path.join(project_root, ".mcp.json")
        if os.path.isfile(project_config_path):
            search_paths.append((project_config_path, "project"))

    for config_path, scope in search_paths:
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            servers = data.get("mcpServers", {})
            for name, server_config in servers.items():
                parsed = _parse_server_config(server_config)
                if parsed is not None:
                    result[name] = ScopedMcpServerConfig(config=parsed, scope=scope)
        except (json.JSONDecodeError, OSError):
            continue

    return result


def _parse_server_config(data: dict[str, Any]) -> McpServerConfig | None:
    transport_type = data.get("type", "stdio")

    if transport_type == "stdio":
        return McpStdioServerConfig(
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env"),
        )
    elif transport_type == "sse":
        return McpSSEServerConfig(
            url=data.get("url", ""),
            headers=data.get("headers"),
        )
    elif transport_type == "http":
        return McpHTTPServerConfig(
            url=data.get("url", ""),
            headers=data.get("headers"),
        )
    elif transport_type == "ws":
        return McpWebSocketServerConfig(
            url=data.get("url", ""),
            headers=data.get("headers"),
        )
    elif transport_type == "sdk":
        return McpSdkServerConfig(name=data.get("name", ""))

    return None


class McpSession:
    def __init__(self):
        self._connections: dict[str, McpServerConnection] = {}
        self._clients: dict[str, StdioMcpClient | SSEMcpClient] = {}
        self._tools_cache: dict[str, list[McpTool]] = {}

    async def connect_server(
        self, server_name: str, config: McpServerConfig, scope: ConfigScope = "user"
    ) -> McpServerConnection:
        if server_name in self._connections:
            existing = self._connections[server_name]
            if existing.type == "connected":
                return existing

        conn = await connect_to_server(server_name, config, scope)
        self._connections[server_name] = conn
        return conn

    async def disconnect_server(self, server_name: str) -> None:
        if server_name in self._clients:
            await self._clients[server_name].close()
            del self._clients[server_name]
        self._connections.pop(server_name, None)
        self._tools_cache.pop(server_name, None)

    async def get_tools(
        self, server_name: str, config: McpServerConfig, scope: ConfigScope = "user"
    ) -> list[McpTool]:
        if server_name in self._tools_cache:
            return self._tools_cache[server_name]

        conn = await self.connect_server(server_name, config, scope)
        if conn.type != "connected":
            return []

        client = self._clients.get(server_name)
        if client is None:
            if isinstance(config, McpStdioServerConfig):
                client = StdioMcpClient(config, server_name)
            elif isinstance(config, McpSSEServerConfig):
                client = SSEMcpClient(config, server_name)
            else:
                return []
            self._clients[server_name] = client

        try:
            tools = await client.list_tools()
            self._tools_cache[server_name] = tools
            return tools
        except Exception:
            return []

    async def call_tool(
        self,
        full_name: str,
        arguments: dict[str, Any] | None = None,
        config: McpServerConfig | None = None,
    ) -> dict[str, Any]:
        parsed = parse_mcp_tool_name(full_name)
        if parsed is None:
            raise ValueError(f"Invalid MCP tool name: {full_name}")
        server_name, tool_name = parsed

        if config is None:
            loaded = await load_mcp_configs()
            scoped = loaded.get(server_name)
            if scoped is None:
                raise ValueError(f"No config found for MCP server: {server_name}")
            config = scoped.config

        conn = await self.connect_server(server_name, config)
        if conn.type != "connected":
            raise _JsonRpcError(
                code=-1, message=f"Server {server_name} is not connected: {conn.type}"
            )

        client = self._clients.get(server_name)
        if client is None:
            if isinstance(config, McpStdioServerConfig):
                client = StdioMcpClient(config, server_name)
            elif isinstance(config, McpSSEServerConfig):
                client = SSEMcpClient(config, server_name)
            else:
                raise ValueError(f"Unsupported config type: {type(config).__name__}")
            self._clients[server_name] = client

        return await client.call_tool(tool_name, arguments)

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
        self._connections.clear()
        self._tools_cache.clear()


_mcp_session: McpSession | None = None


def get_mcp_session() -> McpSession:
    global _mcp_session
    if _mcp_session is None:
        _mcp_session = McpSession()
    return _mcp_session

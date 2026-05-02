from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LANGUAGE_SERVERS: dict[str, list[str]] = {
    ".py": ["pylsp"],
    ".ts": ["typescript-language-server", "--stdio"],
    ".tsx": ["typescript-language-server", "--stdio"],
    ".js": ["typescript-language-server", "--stdio"],
    ".jsx": ["typescript-language-server", "--stdio"],
    ".go": ["gopls"],
    ".rs": ["rust-analyzer"],
    ".vue": ["vue-language-server", "--stdio"],
    ".json": ["vscode-json-languageserver", "--stdio"],
}


@dataclass
class LSPPosition:
    line: int
    character: int


@dataclass
class LSPRange:
    start: LSPPosition
    end: LSPPosition


@dataclass
class LSPLocation:
    uri: str
    range: LSPRange


@dataclass
class LSPCompletionItem:
    label: str
    kind: int | None = None
    detail: str | None = None
    documentation: str | None = None
    insert_text: str | None = None


@dataclass
class LSPDiagnostic:
    range: LSPRange
    severity: int
    message: str
    source: str | None = None
    code: str | None = None


@dataclass
class LSPServerConfig:
    language_id: str
    extension_to_language: dict[str, str] = field(default_factory=dict)


_LANGUAGE_IDS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".go": "go",
    ".rs": "rust",
    ".vue": "vue",
    ".json": "json",
    ".css": "css",
    ".html": "html",
}


class LSPClient:
    def __init__(self, root_uri: str, cmd: list[str]):
        self.root_uri = root_uri
        self.cmd = cmd
        self._process: asyncio.subprocess.Process | None = None
        self._buffer = b""
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[Any] | None = None
        self._notification_handlers: dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        if self._process is not None:
            return

        self._process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.ensure_future(self._read_loop())

    async def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                try:
                    self._process.kill()
                except Exception:
                    pass
            except Exception:
                pass
            self._process = None

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def initialize(
        self, process_id: int, capabilities: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "processId": process_id,
            "rootUri": self.root_uri,
            "capabilities": capabilities or {},
        }
        return await self._send_request("initialize", params)

    async def send_initialized(self) -> None:
        await self._send_notification("initialized", {})

    async def send_notification(self, method: str, params: Any) -> None:
        await self._send_message(method, params, is_request=False)

    async def send_request(self, method: str, params: Any) -> Any:
        return await self._send_request(method, params)

    async def _send_request(self, method: str, params: Any) -> Any:
        request_id = self._request_id + 1
        self._request_id = request_id

        future: asyncio.Future[Any] = asyncio.Future()
        self._pending[request_id] = future

        try:
            await self._send_message(method, params, request_id, is_request=True)
            return await asyncio.wait_for(future, timeout=30.0)
        finally:
            self._pending.pop(request_id, None)

    async def _send_message(
        self,
        method: str,
        params: Any,
        request_id: int | None = None,
        is_request: bool = False,
    ) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP process not started")

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        if is_request and request_id is not None:
            message["id"] = request_id

        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._process.stdin.write((header + body).encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        if self._process is None or self._process.stdout is None:
            return

        while True:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break

                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                if line_str.startswith("Content-Length:"):
                    content_length = int(line_str.split(":")[1].strip())
                    await self._process.stdout.readline()

                    body_data = await self._process.stdout.readexactly(content_length)
                    try:
                        message = json.loads(body_data.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue

                    await self._handle_message(message)
                else:
                    try:
                        message = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue
                    await self._handle_message(message)

            except asyncio.CancelledError:
                break
            except asyncio.IncompleteReadError:
                break
            except Exception:
                break

    async def _handle_message(self, message: dict[str, Any]) -> None:
        if "id" in message:
            request_id = message["id"]
            future = self._pending.get(request_id)
            if future and not future.done():
                if "error" in message:
                    future.set_exception(
                        LSPError(
                            message["error"].get("code", -1),
                            message["error"].get("message", "Unknown error"),
                        )
                    )
                else:
                    future.set_result(message.get("result"))
        elif "method" in message:
            handler = self._notification_handlers.get(message["method"])
            if handler:
                try:
                    handler(message.get("params"))
                except Exception:
                    pass


class LSPError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"LSP Error [{code}]: {message}")


def _detect_language(file_uri: str) -> str | None:
    ext = Path(file_uri).suffix.lower()
    return _LANGUAGE_IDS.get(ext)


def _get_lsp_command(file_uri: str) -> list[str] | None:
    ext = Path(file_uri).suffix.lower()
    return LANGUAGE_SERVERS.get(ext)


def _file_uri_to_path(uri: str) -> str:
    path = uri.replace("file://", "", 1)
    if os.name == "nt":
        path = path.lstrip("/")
    return path


def _path_to_file_uri(file_path: str) -> str:
    abs_path = os.path.abspath(file_path)
    if os.name == "nt":
        return "file:///" + abs_path.replace("\\", "/")
    return "file://" + abs_path


class LSPServer:
    def __init__(self, root_uri: str, cmd: list[str], language_id: str):
        self.root_uri = root_uri
        self.cmd = cmd
        self.language_id = language_id
        self._client = LSPClient(root_uri, cmd)
        self._initialized = False
        self._open_files: set[str] = set()
        self._diagnostics: dict[str, list[LSPDiagnostic]] = {}

    @property
    def is_running(self) -> bool:
        return self._client.is_running and self._initialized

    async def start(self) -> None:
        await self._client.start()

        default_capabilities = {
            "textDocument": {
                "publishDiagnostics": {"relatedInformation": True},
                "completion": {"dynamicRegistration": False},
                "hover": {"contentFormat": ["markdown", "plaintext"]},
                "definition": {"linkSupport": True},
                "references": {"dynamicRegistration": False},
                "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
            },
            "workspace": {
                "configuration": False,
                "workspaceFolders": False,
            },
        }

        await self._client.initialize(os.getpid(), default_capabilities)
        await self._client.send_initialized()

        self._client._notification_handlers["textDocument/publishDiagnostics"] = (
            self._on_publish_diagnostics
        )

        self._initialized = True

    async def stop(self) -> None:
        self._initialized = False
        await self._client.stop()

    def _on_publish_diagnostics(self, params: dict[str, Any]) -> None:
        uri = params.get("uri", "")
        diagnostics_raw = params.get("diagnostics", [])
        diagnostics: list[LSPDiagnostic] = []
        for d in diagnostics_raw:
            diag_range = d.get("range", {})
            diagnostics.append(
                LSPDiagnostic(
                    range=LSPRange(
                        start=LSPPosition(
                            line=diag_range.get("start", {}).get("line", 0),
                            character=diag_range.get("start", {}).get("character", 0),
                        ),
                        end=LSPPosition(
                            line=diag_range.get("end", {}).get("line", 0),
                            character=diag_range.get("end", {}).get("character", 0),
                        ),
                    ),
                    severity=d.get("severity", 1),
                    message=d.get("message", ""),
                    source=d.get("source"),
                    code=str(d.get("code", "")) if d.get("code") else None,
                )
            )
        self._diagnostics[uri] = diagnostics

    async def _ensure_did_open(self, uri: str) -> None:
        if uri in self._open_files:
            return

        file_path = _file_uri_to_path(uri)
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, FileNotFoundError):
            return

        await self._client.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": self.language_id,
                    "version": 1,
                    "text": content,
                }
            },
        )
        self._open_files.add(uri)

    async def get_completions(self, uri: str, position: LSPPosition) -> list[LSPCompletionItem]:
        if not self.is_running:
            return []
        await self._ensure_did_open(uri)

        try:
            result = await self._client.send_request(
                "textDocument/completion",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": position.line, "character": position.character},
                },
            )
        except (TimeoutError, LSPError):
            return []

        items = result if isinstance(result, list) else result.get("items", [])
        completions: list[LSPCompletionItem] = []
        for item in items:
            completions.append(
                LSPCompletionItem(
                    label=item.get("label", ""),
                    kind=item.get("kind"),
                    detail=item.get("detail"),
                    documentation=item.get("documentation"),
                    insert_text=item.get("insertText") or item.get("label", ""),
                )
            )
        return completions

    async def go_to_definition(self, uri: str, position: LSPPosition) -> list[LSPLocation]:
        if not self.is_running:
            return []
        await self._ensure_did_open(uri)

        try:
            result = await self._client.send_request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": position.line, "character": position.character},
                },
            )
        except (TimeoutError, LSPError):
            return []

        locations: list[LSPLocation] = []
        raw_locations = result if isinstance(result, list) else [result] if result else []

        for loc in raw_locations:
            if loc is None:
                continue
            target_uri = loc.get("uri") or loc.get("targetUri", "")
            loc_range = loc.get("range") or loc.get("targetRange", {})
            locations.append(
                LSPLocation(
                    uri=target_uri,
                    range=LSPRange(
                        start=LSPPosition(
                            line=loc_range.get("start", {}).get("line", 0),
                            character=loc_range.get("start", {}).get("character", 0),
                        ),
                        end=LSPPosition(
                            line=loc_range.get("end", {}).get("line", 0),
                            character=loc_range.get("end", {}).get("character", 0),
                        ),
                    ),
                )
            )
        return locations

    async def get_diagnostics(self, uri: str) -> list[LSPDiagnostic]:
        if not self.is_running:
            return []
        await self._ensure_did_open(uri)
        await asyncio.sleep(0.5)
        return self._diagnostics.get(uri, [])


class LSPService:
    _instance: LSPService | None = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._servers: dict[str, LSPServer] = {}
        self._extension_map: dict[str, str] = {}

    @classmethod
    async def get_instance(cls) -> LSPService:
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = LSPService()
        return cls._instance

    async def _get_or_create_server(self, file_uri: str) -> LSPServer | None:
        ext = Path(file_uri).suffix.lower()
        language_id = _LANGUAGE_IDS.get(ext)
        if not language_id:
            return None

        cmd = LANGUAGE_SERVERS.get(ext)
        if not cmd:
            return None

        server_key = ext
        if server_key in self._servers:
            server = self._servers[server_key]
            if server.is_running:
                return server

        root_path = os.getcwd()
        root_uri = _path_to_file_uri(root_path)

        server = LSPServer(root_uri, cmd, language_id)
        try:
            await server.start()
        except (FileNotFoundError, Exception):
            return None

        self._servers[server_key] = server
        self._extension_map[ext] = server_key
        return server

    async def get_completions(
        self, file_uri: str, position: LSPPosition
    ) -> list[LSPCompletionItem]:
        server = await self._get_or_create_server(file_uri)
        if server is None:
            return []
        return await server.get_completions(file_uri, position)

    async def go_to_definition(self, file_uri: str, position: LSPPosition) -> list[LSPLocation]:
        server = await self._get_or_create_server(file_uri)
        if server is None:
            return []
        return await server.go_to_definition(file_uri, position)

    async def get_diagnostics(self, file_uri: str) -> list[LSPDiagnostic]:
        server = await self._get_or_create_server(file_uri)
        if server is None:
            return []
        return await server.get_diagnostics(file_uri)

    async def shutdown(self) -> None:
        for server in self._servers.values():
            try:
                await server.stop()
            except Exception:
                pass
        self._servers.clear()
        self._extension_map.clear()

    def is_connected(self, file_uri: str) -> bool:
        ext = Path(file_uri).suffix.lower()
        server_key = self._extension_map.get(ext)
        if server_key is None:
            return False
        server = self._servers.get(server_key)
        return server is not None and server.is_running


async def get_completions(uri: str, position: LSPPosition) -> list[LSPCompletionItem]:
    service = await LSPService.get_instance()
    return await service.get_completions(uri, position)


async def go_to_definition(uri: str, position: LSPPosition) -> list[LSPLocation]:
    service = await LSPService.get_instance()
    return await service.go_to_definition(uri, position)


async def get_diagnostics(uri: str) -> list[LSPDiagnostic]:
    service = await LSPService.get_instance()
    return await service.get_diagnostics(uri)

from __future__ import annotations

import asyncio
import io
import json
import os
import signal
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"

MAX_PROMPT_CHARS = 200_000
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
SSE_KEEPALIVE_INTERVAL = 15.0
SHUTDOWN_TIMEOUT = 10.0

_shutting_down = False
_active_connection_count = 0
_active_connection_lock = asyncio.Lock()

limiter = Limiter(key_func=get_remote_address, default_limits=[])


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_CHARS)
    model: str | None = None
    permission_mode: str = "default"
    session_id: str | None = None
    resume: bool = False


class StopResponse(BaseModel):
    stopped: bool
    session_id: str
    message: str = "Session stopped"


class UploadImageResponse(BaseModel):
    base64: str
    width: int
    height: int
    size_bytes: int
    format: str


class HealthResponse(BaseModel):
    status: str = "ok"


class StatusResponse(BaseModel):
    session_id: str | None
    model: str | None
    permission_mode: str
    total_cost_usd: float
    context_tokens: int
    context_limit: int
    uptime_seconds: float
    docker_available: bool


def _validate_prompt(prompt: str) -> None:
    stripped = prompt.strip()
    if not stripped:
        raise ValueError("prompt must not be empty")
    if all(c in "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
           "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
           "\x7f" for c in stripped):
        raise ValueError("prompt must not consist entirely of control characters")


def _get_tools():
    from server.tools.registry import assemble_tool_pool
    from server.tools.bash_tool import BashTool
    from server.tools.file_read_tool import FileReadTool
    from server.tools.file_write_tool import FileWriteTool
    from server.tools.file_edit_tool import FileEditTool
    from server.tools.glob_tool import GlobTool
    from server.tools.grep_tool import GrepTool
    from server.tools.todo_write_tool import TodoWriteTool
    from server.tools.web_search_tool import WebSearchTool
    from server.tools.web_fetch_tool import WebFetchTool

    builtins = [
        BashTool(),
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        GlobTool(),
        GrepTool(),
        TodoWriteTool(),
        WebSearchTool(),
        WebFetchTool(),
    ]
    return assemble_tool_pool(None, [], builtins)


def _format_sse_event(event: dict[str, Any], event_type: str) -> str:
    data_str = json.dumps(event, ensure_ascii=False, default=str)

    type_map = {
        "text_delta": "text_delta",
        "tool_use": "tool_use",
        "tool_result": "tool_result",
        "system_init": "system_init",
        "assistant": "message",
        "stream_event": "message",
        "error": "error",
        "result": "result",
        "exit": "result",
    }

    sse_type = type_map.get(event_type, "message")
    return f"event: {sse_type}\ndata: {data_str}\n\n"


def _json_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@asynccontextmanager
async def lifespan(app: FastAPI):
    from server.state.global_state import GlobalState
    from server.utils.log import setup_logging

    setup_logging()

    state = GlobalState.get_instance()
    state.initialize()

    loop = asyncio.get_running_loop()

    def _handle_sigterm():
        global _shutting_down
        _shutting_down = True
        asyncio.ensure_future(_graceful_shutdown(app))

    if os.name == "nt":
        signal.signal(signal.SIGINT, lambda s, f: _handle_sigterm())
        signal.signal(signal.SIGBREAK, lambda s, f: _handle_sigterm())
    else:
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
        loop.add_signal_handler(signal.SIGINT, _handle_sigterm)

    yield

    global _shutting_down
    _shutting_down = True
    await _graceful_shutdown(app)
    state.shutdown()


async def _graceful_shutdown(app: FastAPI) -> None:
    from server.state.session import SessionStorage
    from server.utils.log import get_logger

    log = get_logger("shutdown")
    log.info("graceful_shutdown_started")

    await asyncio.sleep(0.5)

    deadline = time.monotonic() + SHUTDOWN_TIMEOUT
    while time.monotonic() < deadline:
        if _active_connection_count <= 0:
            break
        await asyncio.sleep(0.1)

    log.info("graceful_shutdown_complete", remaining_connections=_active_connection_count)


app = FastAPI(
    title="py-cc-learn",
    description="Python rewrite of Claude Code Haha - multi-vendor AI coding assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def proxy_fix_middleware(request: Request, call_next):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        request.scope["client"] = (
            forwarded.split(",")[0].strip(),
            request.scope.get("client", ("127.0.0.1", 0))[1],
        )
    response = await call_next(request)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    from server.utils.log import set_request_id, clear_request_id

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(request_id)
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_request_id()


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    from server.utils.log import get_logger

    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000

    log = get_logger("http")
    log.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        elapsed_ms=round(elapsed_ms, 2),
    )
    response.headers["X-Response-Time-Ms"] = str(round(elapsed_ms, 2))
    return response


@app.middleware("http")
async def prompt_validation_middleware(request: Request, call_next):
    global _shutting_down
    if _shutting_down:
        return JSONResponse(
            status_code=503,
            content={"error": "shutting_down", "message": "Server is shutting down"},
        )

    if request.url.path == "/api/v1/chat" and request.method == "POST":
        try:
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    return JSONResponse(
                        status_code=422,
                        content={"error": "invalid_json", "message": "Request body must be valid JSON"},
                    )
                prompt = data.get("prompt", "")
                if not prompt or not prompt.strip():
                    return JSONResponse(
                        status_code=422,
                        content={"error": "empty_prompt", "message": "prompt must not be empty"},
                    )
                if len(prompt) > MAX_PROMPT_CHARS:
                    return JSONResponse(
                        status_code=422,
                        content={"error": "prompt_too_long",
                                 "message": f"prompt must be at most {MAX_PROMPT_CHARS} characters"},
                    )
                if all(c in "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
                       "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
                       "\x7f" for c in prompt.strip()):
                    return JSONResponse(
                        status_code=422,
                        content={"error": "control_chars_only",
                                 "message": "prompt must not consist entirely of control characters"},
                    )
            request._body = body
        except Exception:
            pass

    global _active_connection_count
    async with _active_connection_lock:
        _active_connection_count += 1

    try:
        response = await call_next(request)
        return response
    finally:
        async with _active_connection_lock:
            _active_connection_count = max(0, _active_connection_count - 1)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1/status", response_model=StatusResponse)
async def status():
    from server.state.global_state import GlobalState

    state = GlobalState.get_instance()
    docker_available = False
    try:
        from server.sandbox.manager import is_docker_available
        docker_available = is_docker_available()
    except Exception:
        pass

    ctx_tokens = 0
    if state.model_usage:
        for usage in state.model_usage.values():
            if isinstance(usage, dict):
                ctx_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

    return {
        "session_id": state.session_id,
        "model": state.initial_main_loop_model.get("model")
        if state.initial_main_loop_model
        else None,
        "permission_mode": "default",
        "total_cost_usd": state.total_cost_usd,
        "context_tokens": ctx_tokens,
        "context_limit": 200000,
        "uptime_seconds": state.get_uptime_seconds(),
        "docker_available": docker_available,
    }


@app.post("/api/v1/chat")
@limiter.limit("30/minute")
async def chat(request: Request):
    from server.routes.session_registry import register_session, unregister_session
    from server.utils.log import get_logger

    log = get_logger("chat")

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(status_code=422, content={"error": "invalid_json"})

    chat_req = ChatRequest(**data)
    _validate_prompt(chat_req.prompt)

    session_id = chat_req.session_id or str(uuid.uuid4())
    cancel_event = asyncio.Event()

    provider = None
    try:
        from server.services.provider_factory import ProviderFactory
        factory = ProviderFactory.get_instance()
        provider = factory.get_provider()
        if chat_req.model and provider:
            provider.config.model = chat_req.model
    except Exception as exc:
        log.error("provider_error", error=str(exc))
        return JSONResponse(status_code=500, content={"error": "provider_unavailable"})

    tools = _get_tools()
    from server.engine.query_engine import QueryEngine, QueryEngineConfig
    from server.state.session import SessionStorage

    engine = QueryEngine(QueryEngineConfig(
        cwd=os.getcwd(),
        tools=tools,
        provider=provider,
        system_prompt="You are a helpful AI coding assistant.",
        max_turns=50,
        session_storage=SessionStorage(session_id=session_id),
        abort_signal=cancel_event,
    ))

    await register_session(session_id, engine, cancel_event)

    async def _chat_sse():
        last_send = time.monotonic()
        try:
            async for event in engine.submit_message(chat_req.prompt):
                if cancel_event.is_set():
                    yield f"event: error\ndata: {{\"stop_reason\": \"cancelled_by_user\"}}\n\n"
                    return

                event_type = event.get("type", "")
                sse = _format_sse_event(event, event_type)

                if sse.strip():
                    yield sse
                    last_send = time.monotonic()

                current = time.monotonic()
                if current - last_send >= SSE_KEEPALIVE_INTERVAL:
                    yield ":keepalive\n\n"
                    last_send = current

                if event_type in ("exit", "result"):
                    if event_type == "result":
                        yield _format_sse_event(event, "result")
                    return

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            yield f"event: error\ndata: {{\"stop_reason\": \"cancelled_by_user\"}}\n\n"
        except Exception as exc:
            log.error("chat_stream_error", error=str(exc))
            yield f"event: error\ndata: {{\"stop_reason\": \"error\", \"message\": \"{_json_escape(str(exc))}\"}}\n\n"
        finally:
            await unregister_session(session_id)

    return StreamingResponse(
        _chat_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


@app.post("/api/v1/stop/{session_id}", response_model=StopResponse)
async def stop_session(session_id: str):
    from server.routes.session_registry import stop_session as do_stop

    stopped = await do_stop(session_id)
    if stopped:
        return {"stopped": True, "session_id": session_id, "message": "Session stopped"}
    return JSONResponse(
        status_code=404,
        content={"stopped": False, "session_id": session_id, "message": "Session not found or already completed"},
    )


@app.post("/api/v1/upload/image", response_model=UploadImageResponse)
async def upload_image(file: UploadFile):
    from server.utils.log import get_logger

    log = get_logger("upload")

    if not file.content_type or not file.content_type.startswith("image/"):
        return JSONResponse(status_code=415, content={"error": "unsupported_media_type",
                                                       "message": "Only image files are accepted"})

    contents = await file.read()
    size = len(contents)

    if size > MAX_IMAGE_SIZE_BYTES:
        return JSONResponse(status_code=413, content={"error": "image_too_large",
                                                       "message": f"Image must be ≤ 5MB, got {size} bytes"})

    if size == 0:
        return JSONResponse(status_code=422, content={"error": "empty_image",
                                                       "message": "Image file is empty"})

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(contents))
        width, height = img.size
        fmt = img.format or "PNG"

        if size > MAX_IMAGE_SIZE_BYTES:
            max_dim = 2048
            if width > max_dim or height > max_dim:
                ratio = min(max_dim / width, max_dim / height)
                new_w, new_h = int(width * ratio), int(height * ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format=fmt)
                contents = buf.getvalue()
                size = len(contents)
                width, height = new_w, new_h

                if size > MAX_IMAGE_SIZE_BYTES:
                    return JSONResponse(status_code=413, content={"error": "image_too_large",
                                                                   "message": "Image too large even after resize"})

        import base64
        b64 = base64.b64encode(contents).decode("ascii")

        log.info("image_uploaded", width=width, height=height, size_bytes=size, format=fmt)

        return {
            "base64": b64,
            "width": width,
            "height": height,
            "size_bytes": size,
            "format": fmt,
        }
    except Exception as exc:
        log.error("image_processing_error", error=str(exc))
        return JSONResponse(status_code=422, content={"error": "image_processing_failed",
                                                       "message": str(exc)})


if STATIC_DIR.exists() and STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

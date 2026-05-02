import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from server.state.global_state import GlobalState

    state = GlobalState.get_instance()
    state.initialize()
    yield
    state.shutdown()


app = FastAPI(
    title="py-cc-learn",
    description="Python rewrite of Claude Code Haha - multi-vendor AI coding assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1/status")
async def status():
    from server.state.global_state import GlobalState

    state = GlobalState.get_instance()
    return {
        "session_id": state.session_id,
        "model": state.initial_main_loop_model.get("model") if state.initial_main_loop_model else None,
        "permission_mode": "default",
        "total_cost_usd": state.total_cost_usd,
        "context_tokens": 0,
        "context_limit": 200000,
        "uptime_seconds": state.get_uptime_seconds(),
        "docker_available": False,
    }


if STATIC_DIR.exists() and STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

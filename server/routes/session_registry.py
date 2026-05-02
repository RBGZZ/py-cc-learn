from __future__ import annotations

import asyncio
from typing import Any

_active_engines: dict[str, tuple[Any, asyncio.Event]] = {}
_engines_lock = asyncio.Lock()


async def register_session(session_id: str, engine: Any, cancel_event: asyncio.Event) -> None:
    async with _engines_lock:
        _active_engines[session_id] = (engine, cancel_event)


async def unregister_session(session_id: str) -> None:
    async with _engines_lock:
        _active_engines.pop(session_id, None)


async def stop_session(session_id: str) -> bool:
    async with _engines_lock:
        entry = _active_engines.pop(session_id, None)
    if entry is None:
        return False
    engine, cancel_event = entry
    cancel_event.set()
    if hasattr(engine, "interrupt"):
        engine.interrupt()
    return True


async def get_active_session_ids() -> list[str]:
    async with _engines_lock:
        return list(_active_engines.keys())

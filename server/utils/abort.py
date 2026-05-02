from __future__ import annotations

import asyncio
import signal
import weakref
from typing import Optional


DEFAULT_MAX_LISTENERS = 50


class AbortController:
    def __init__(self, max_listeners: int = DEFAULT_MAX_LISTENERS) -> None:
        self._event = asyncio.Event()
        self._reason: Optional[str] = None

    @property
    def signal(self) -> asyncio.Event:
        return self._event

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    def abort(self, reason: Optional[str] = None) -> None:
        self._reason = reason
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


def create_abort_controller(
    max_listeners: int = DEFAULT_MAX_LISTENERS,
) -> AbortController:
    return AbortController(max_listeners)


def create_child_abort_controller(
    parent: AbortController,
    max_listeners: int = DEFAULT_MAX_LISTENERS,
) -> AbortController:
    child = AbortController(max_listeners)

    if parent.aborted:
        child.abort(parent.reason)
        return child

    _weak_child = weakref.ref(child)
    _weak_parent = weakref.ref(parent)

    async def _propagate_abort() -> None:
        p = _weak_parent()
        c = _weak_child()
        if p is not None and c is not None:
            c.abort(p.reason)

    _propagation_task = asyncio.create_task(_propagate_abort())

    async def _cancel_propagation() -> None:
        await child._event.wait()
        _propagation_task.cancel()

    asyncio.create_task(_cancel_propagation())

    return child


async def wait_for_with_abort(
    coro,
    timeout: Optional[float],
    abort_controller: Optional[AbortController] = None,
):
    if abort_controller is not None and abort_controller.aborted:
        raise asyncio.CancelledError("Aborted")

    if abort_controller is not None:
        abort_task = asyncio.create_task(abort_controller.wait())
        main_task = asyncio.create_task(coro)
    else:
        abort_task = None
        main_task = asyncio.create_task(coro)

    try:
        if timeout is not None:
            if abort_controller is not None:
                done, pending = await asyncio.wait(
                    [main_task, abort_task],
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            else:
                try:
                    return await asyncio.wait_for(main_task, timeout=timeout)
                except asyncio.TimeoutError:
                    raise
            if abort_task in done:
                main_task.cancel()
                try:
                    await main_task
                except asyncio.CancelledError:
                    pass
                raise asyncio.CancelledError("Aborted")
            if main_task in done:
                if abort_task is not None:
                    abort_task.cancel()
                    try:
                        await abort_task
                    except asyncio.CancelledError:
                        pass
                return main_task.result()
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            raise asyncio.TimeoutError()
        else:
            if abort_controller is not None:
                done, pending = await asyncio.wait(
                    [main_task, abort_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if abort_task in done:
                    main_task.cancel()
                    try:
                        await main_task
                    except asyncio.CancelledError:
                        pass
                    raise asyncio.CancelledError("Aborted")
                if main_task in done:
                    abort_task.cancel()
                    try:
                        await abort_task
                    except asyncio.CancelledError:
                        pass
                    return main_task.result()
            else:
                return await main_task
    except Exception:
        if abort_task is not None:
            abort_task.cancel()
            try:
                await abort_task
            except asyncio.CancelledError:
                pass
        raise


async def force_kill_process(
    process: asyncio.subprocess.Process,
    timeout_grace: float = 2.0,
) -> None:
    if process.returncode is not None:
        return

    try:
        if hasattr(signal, "SIGTERM"):
            process.send_signal(signal.SIGTERM)
        else:
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_grace)
            return
        except asyncio.TimeoutError:
            pass

        if hasattr(signal, "SIGKILL"):
            process.send_signal(signal.SIGKILL)
        else:
            process.kill()

        await process.wait()
    except ProcessLookupError:
        pass

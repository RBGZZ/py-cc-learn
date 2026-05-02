import asyncio
import contextlib
import ctypes
import subprocess

from .platform import get_platform

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

CAFFEINATE_TIMEOUT_SECONDS = 300
RESTART_INTERVAL_SECONDS = 240

_caffeinate_process: subprocess.Popen | None = None
_restart_task: asyncio.Task | None = None
_ref_count = 0


async def _spawn_caffeinate() -> None:
    global _caffeinate_process

    if get_platform() != "macos":
        return

    if _caffeinate_process is not None:
        return

    try:
        _caffeinate_process = subprocess.Popen(
            ["caffeinate", "-i", "-t", str(CAFFEINATE_TIMEOUT_SECONDS)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        _caffeinate_process = None


def _kill_caffeinate() -> None:
    global _caffeinate_process
    if _caffeinate_process is not None:
        proc = _caffeinate_process
        _caffeinate_process = None
        with contextlib.suppress(OSError, ProcessLookupError):
            proc.kill()


async def _restart_caffeinate_loop() -> None:
    while True:
        await asyncio.sleep(RESTART_INTERVAL_SECONDS)
        if _ref_count > 0:
            _kill_caffeinate()
            await _spawn_caffeinate()


def start_prevent_sleep() -> None:
    global _ref_count, _restart_task
    _ref_count += 1

    if _ref_count == 1:
        platform = get_platform()
        if platform == "windows":
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
        elif platform == "macos":
            asyncio.get_event_loop().create_task(_spawn_caffeinate())
            _restart_task = asyncio.get_event_loop().create_task(_restart_caffeinate_loop())


def stop_prevent_sleep() -> None:
    global _ref_count, _restart_task
    if _ref_count > 0:
        _ref_count -= 1

    if _ref_count == 0:
        platform = get_platform()
        if platform == "windows":
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        elif platform == "macos":
            if _restart_task is not None:
                _restart_task.cancel()
                _restart_task = None
            _kill_caffeinate()


def force_stop_prevent_sleep() -> None:
    global _ref_count, _restart_task
    _ref_count = 0
    if _restart_task is not None:
        _restart_task.cancel()
        _restart_task = None

    platform = get_platform()
    if platform == "windows":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    elif platform == "macos":
        _kill_caffeinate()

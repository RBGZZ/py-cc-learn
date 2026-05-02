import asyncio
import os
import shutil
from functools import lru_cache

from ..platform import get_platform
from ..windows_paths import find_git_bash_path as _find_git_bash


def find_git_bash_path() -> str:
    return _find_git_bash()


def is_msys() -> bool:
    return bool(os.environ.get("MSYSTEM"))


def is_cygwin() -> bool:
    return bool(os.environ.get("OSTYPE") and "cygwin" in os.environ.get("OSTYPE", "").lower())


async def _probe_path(p: str) -> str | None:
    if os.path.isfile(p):
        return p
    return None


async def find_power_shell_path() -> str | None:
    pwsh_path = shutil.which("pwsh")
    if pwsh_path:
        if get_platform() == "linux":
            resolved = os.path.realpath(pwsh_path)
            if pwsh_path.startswith("/snap/") or resolved.startswith("/snap/"):
                direct = await _probe_path("/opt/microsoft/powershell/7/pwsh")
                if not direct:
                    direct = await _probe_path("/usr/bin/pwsh")
                if direct:
                    direct_resolved = os.path.realpath(direct)
                    if not direct.startswith("/snap/") and not direct_resolved.startswith("/snap/"):
                        return direct
        return pwsh_path

    powershell_path = shutil.which("powershell")
    if powershell_path:
        return powershell_path

    return None


_cached_power_shell_path: str | None = None
_cached_power_shell_resolved: bool = False
_cached_power_shell_pending: asyncio.Task | None = None


async def get_cached_power_shell_path() -> str | None:
    global _cached_power_shell_path, _cached_power_shell_resolved, _cached_power_shell_pending
    if _cached_power_shell_resolved:
        return _cached_power_shell_path
    if _cached_power_shell_pending is not None:
        return await _cached_power_shell_pending
    task = asyncio.create_task(find_power_shell_path())
    _cached_power_shell_pending = task
    try:
        _cached_power_shell_path = await task
        _cached_power_shell_resolved = True
        return _cached_power_shell_path
    finally:
        _cached_power_shell_pending = None


@lru_cache(maxsize=1)
def _get_power_shell_edition_inner(path: str) -> str | None:
    base = os.path.basename(path).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    if base == "pwsh":
        return "core"
    return "desktop"


async def get_power_shell_edition() -> str | None:
    p = await get_cached_power_shell_path()
    if not p:
        return None
    return _get_power_shell_edition_inner(p)


def reset_power_shell_cache() -> None:
    global _cached_power_shell_path, _cached_power_shell_resolved, _cached_power_shell_pending
    _cached_power_shell_path = None
    _cached_power_shell_resolved = False
    _cached_power_shell_pending = None
    _get_power_shell_edition_inner.cache_clear()

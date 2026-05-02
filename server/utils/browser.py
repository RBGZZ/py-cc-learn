import asyncio
import os
import subprocess
from urllib.parse import urlparse

from .platform import get_platform


def _validate_url(url: str) -> None:
    try:
        parsed = urlparse(url)
    except (ValueError, Exception) as e:
        raise ValueError(f"Invalid URL format: {url}") from e

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL protocol: must use http:// or https://, got {parsed.scheme}")


async def open_path(path: str) -> bool:
    try:
        platform = get_platform()

        if platform == "windows":
            proc = await asyncio.create_subprocess_exec(
                "explorer",
                path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0

        command = "open" if platform == "macos" else "xdg-open"
        proc = await asyncio.create_subprocess_exec(
            command,
            path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


async def open_browser(url: str) -> bool:
    try:
        _validate_url(url)

        browser_env = os.environ.get("BROWSER")
        platform = get_platform()

        if platform == "windows":
            if browser_env:
                proc = await asyncio.create_subprocess_exec(
                    browser_env,
                    f'"{url}"',
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "rundll32",
                    "url,OpenURL",
                    url,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            await proc.wait()
            return proc.returncode == 0

        command = browser_env or ("open" if platform == "macos" else "xdg-open")
        proc = await asyncio.create_subprocess_exec(
            command,
            url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return False

import asyncio
import os
import subprocess
from pathlib import Path

from .platform import get_platform

_clipboard_commands = {
    "darwin": {
        "checkImage": "osascript -e 'the clipboard as «class PNGf»'",
        "saveImage": (
            "osascript -e 'set png_data to (the clipboard as «class PNGf»)'"
            " -e 'set fp to open for access POSIX file \"{path}\" with write permission'"
            " -e 'write png_data to fp'"
            " -e 'close access fp'"
        ),
        "getPath": "osascript -e 'get POSIX path of (the clipboard as «class furl»)'",
        "deleteFile": 'rm -f "{path}"',
    },
    "linux": {
        "checkImage": (
            "xclip -selection clipboard -t TARGETS -o 2>/dev/null"
            ' | grep -E "image/(png|jpeg|jpg|gif|webp|bmp)"'
            " || wl-paste -l 2>/dev/null"
            ' | grep -E "image/(png|jpeg|jpg|gif|webp|bmp)"'
        ),
        "saveImage": (
            'xclip -selection clipboard -t image/png -o > "{path}" 2>/dev/null'
            ' || wl-paste --type image/png > "{path}" 2>/dev/null'
            ' || xclip -selection clipboard -t image/bmp -o > "{path}" 2>/dev/null'
            ' || wl-paste --type image/bmp > "{path}"'
        ),
        "getPath": (
            "xclip -selection clipboard -t text/plain -o 2>/dev/null || wl-paste 2>/dev/null"
        ),
        "deleteFile": 'rm -f "{path}"',
    },
    "win32": {
        "checkImage": ('powershell -NoProfile -Command "(Get-Clipboard -Format Image) -ne $null"'),
        "saveImage": (
            "powershell -NoProfile -Command "
            '"$img = Get-Clipboard -Format Image; '
            "if ($img) {{ $img.Save('{path}', "
            '[System.Drawing.Imaging.ImageFormat]::Png) }}"'
        ),
        "getPath": 'powershell -NoProfile -Command "Get-Clipboard"',
        "deleteFile": 'del /f "{path}"',
    },
}


def _get_platform_key() -> str:
    p = get_platform()
    if p == "macos":
        return "darwin"
    if p == "windows":
        return "win32"
    return "linux"


def _get_clipboard_commands() -> dict:
    key = _get_platform_key()
    base_tmp_dir = os.environ.get(
        "CLAUDE_CODE_TMPDIR",
        os.environ.get("TEMP", "C:\\Temp") if key == "win32" else "/tmp",
    )
    screenshot_filename = "claude_cli_latest_screenshot.png"
    screenshot_path = str(Path(base_tmp_dir) / screenshot_filename)

    cmds = _clipboard_commands.get(key, _clipboard_commands["linux"])

    formatted = {}
    for k, v in cmds.items():
        formatted[k] = v.replace("{path}", screenshot_path.replace("\\", "\\\\"))

    return {
        "commands": formatted,
        "screenshotPath": screenshot_path,
    }


async def has_image_in_clipboard() -> bool:
    if get_platform() != "macos":
        return False

    try:
        proc = await asyncio.create_subprocess_shell(
            "osascript -e 'the clipboard as «class PNGf»'",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


async def get_image_from_clipboard() -> bytes | None:
    info = _get_clipboard_commands()
    cmds = info["commands"]
    screenshot_path = info["screenshotPath"]

    try:
        check_proc = await asyncio.create_subprocess_shell(
            cmds["checkImage"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        check_stdout, _ = await check_proc.communicate()
        if check_proc.returncode != 0 or not check_stdout.strip():
            return None
    except (OSError, subprocess.SubprocessError):
        return None

    try:
        save_proc = await asyncio.create_subprocess_shell(
            cmds["saveImage"],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await save_proc.wait()
    except (OSError, subprocess.SubprocessError):
        return None

    try:
        with open(screenshot_path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    try:
        delete_proc = await asyncio.create_subprocess_shell(
            cmds["deleteFile"],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await delete_proc.wait()
    except (OSError, subprocess.SubprocessError):
        pass

    return data if data else None

from __future__ import annotations

import functools
import os as _os
import sys

from server.utils.log import log_error

Platform = str  # 'macos' | 'windows' | 'wsl' | 'linux' | 'unknown'

SUPPORTED_PLATFORMS: list[Platform] = ["macos", "wsl"]


@functools.lru_cache(maxsize=1)
def get_platform() -> Platform:
    try:
        if sys.platform == "darwin":
            return "macos"

        if sys.platform == "win32":
            return "windows"

        if sys.platform == "linux":
            try:
                with open("/proc/version", encoding="utf-8") as f:
                    proc_version = f.read()
                if "microsoft" in proc_version.lower() or "wsl" in proc_version.lower():
                    return "wsl"
            except Exception as error:
                log_error(error)

            return "linux"

        return "unknown"
    except Exception as error:
        log_error(error)
        return "unknown"


@functools.lru_cache(maxsize=1)
def get_wsl_version() -> str | None:
    if sys.platform != "linux":
        return None
    try:
        with open("/proc/version", encoding="utf-8") as f:
            proc_version = f.read()

        import re

        wsl_version_match = re.search(r"WSL(\d+)", proc_version, re.IGNORECASE)
        if wsl_version_match and wsl_version_match.group(1):
            return wsl_version_match.group(1)

        if "microsoft" in proc_version.lower():
            return "1"

        return None
    except Exception as error:
        log_error(error)
        return None


class LinuxDistroInfo:
    def __init__(
        self,
        linux_distro_id: str | None = None,
        linux_distro_version: str | None = None,
        linux_kernel: str | None = None,
    ) -> None:
        self.linux_distro_id = linux_distro_id
        self.linux_distro_version = linux_distro_version
        self.linux_kernel = linux_kernel


@functools.lru_cache(maxsize=1)
def get_linux_distro_info() -> LinuxDistroInfo | None:
    if sys.platform != "linux":
        return None

    import platform

    result = LinuxDistroInfo(linux_kernel=platform.release())

    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            content = f.read()
        for line in content.split("\n"):
            import re

            match = re.match(r"^(ID|VERSION_ID)=(.*)$", line)
            if match and match.group(1) and match.group(2):
                value = match.group(2).strip('"')
                if match.group(1) == "ID":
                    result.linux_distro_id = value
                else:
                    result.linux_distro_version = value
    except Exception:
        pass

    return result


VCS_MARKERS: list[tuple[str, str]] = [
    (".git", "git"),
    (".hg", "mercurial"),
    (".svn", "svn"),
    (".p4config", "perforce"),
    ("$tf", "tfs"),
    (".tfvc", "tfs"),
    (".jj", "jujutsu"),
    (".sl", "sapling"),
]


def detect_vcs(directory: str | None = None) -> list[str]:
    import os as _os

    detected: set[str] = set()

    if _os.environ.get("P4PORT"):
        detected.add("perforce")

    try:
        target_dir = directory or _os.getcwd()
        entries = set(_os.listdir(target_dir))
        for marker, vcs in VCS_MARKERS:
            if marker in entries:
                detected.add(vcs)
    except Exception:
        pass

    return list(detected)


def is_macos() -> bool:
    return get_platform() == "macos"


def is_windows() -> bool:
    return get_platform() == "windows"


def is_wsl() -> bool:
    return get_platform() == "wsl"


def is_linux() -> bool:
    return get_platform() == "linux"


def is_msys() -> bool:
    return bool(_os.environ.get("MSYSTEM"))


def is_cygwin() -> bool:
    ostype = _os.environ.get("OSTYPE", "")
    return "cygwin" in ostype.lower()


def get_windows_subtype() -> str:
    if is_wsl():
        return "wsl"
    if is_msys():
        return "msys"
    if is_cygwin():
        return "cygwin"
    if is_windows():
        return "native"
    return "none"

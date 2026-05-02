import os
from functools import lru_cache

from .platform import get_platform


def get_temp_dir() -> str:
    if get_platform() == "windows":
        return os.environ.get(
            "TEMP",
            os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "Temp"),
        )
    return "/tmp"


def get_appdata_dir() -> str:
    if get_platform() == "windows":
        return os.environ.get(
            "APPDATA",
            os.path.join(os.environ.get("USERPROFILE", "C:\\"), "AppData", "Roaming"),
        )
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude")


def get_session_storage_dir() -> str:
    appdata = get_appdata_dir()
    if get_platform() == "windows":
        return os.path.join(appdata, "Claude", "sessions")
    return os.path.join(appdata, "sessions")


def normalize_path_for_comparison(file_path: str) -> str:
    normalized = os.path.normpath(file_path)

    if get_platform() == "windows":
        normalized = normalized.replace("/", "\\").lower()

    return normalized


def paths_equal(path1: str, path2: str) -> bool:
    return normalize_path_for_comparison(path1) == normalize_path_for_comparison(path2)


def normalize_filename(filename: str) -> str:
    if get_platform() == "windows":
        return filename.lower()
    return filename


_WRITE_FLAGS_WINDOWS = "w"
_WRITE_FLAGS_POSIX = "a"


def get_write_flags() -> str:
    if get_platform() == "windows":
        return _WRITE_FLAGS_WINDOWS
    return _WRITE_FLAGS_POSIX


def get_utf8_encoding() -> str:
    return "utf-8"


def get_glob_separators() -> tuple[str, str]:
    return ("/", "\\")


@lru_cache(maxsize=500)
def get_last_separator_index(pattern: str) -> int:
    fwd = pattern.rfind("/")
    bwd = pattern.rfind("\\")
    return max(fwd, bwd)

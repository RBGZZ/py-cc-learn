import os
import re
import subprocess
import sys
from functools import lru_cache

from .platform import get_platform


def check_path_exists(path: str) -> bool:
    try:
        subprocess.run(
            f'dir "{path}"',
            capture_output=True,
            check=True,
            shell=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def find_executable(executable: str) -> str | None:
    if executable == "git":
        default_locations = [
            "C:\\Program Files\\Git\\cmd\\git.exe",
            "C:\\Program Files (x86)\\Git\\cmd\\git.exe",
        ]
        for location in default_locations:
            if check_path_exists(location):
                return location

    try:
        result = subprocess.run(
            ["where.exe", executable],
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip()
        if not output:
            return None

        paths = [p for p in output.split("\r\n") if p]
        cwd = os.getcwd().lower()

        for candidate_path in paths:
            normalized_path = os.path.normpath(candidate_path).lower()
            path_dir = os.path.dirname(normalized_path).lower()

            if path_dir == cwd or normalized_path.startswith(cwd + os.sep):
                continue

            return candidate_path

        return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


@lru_cache(maxsize=1)
def find_git_bash_path() -> str:
    env_path = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if env_path:
        if check_path_exists(env_path):
            return env_path
        print(
            f'Claude Code was unable to find CLAUDE_CODE_GIT_BASH_PATH path "{env_path}"',
            file=sys.stderr,
        )
        sys.exit(1)

    git_path = find_executable("git")
    if git_path:
        bash_path = os.path.normpath(os.path.join(git_path, "..", "..", "bin", "bash.exe"))
        if check_path_exists(bash_path):
            return bash_path

    print(
        "Claude Code on Windows requires git-bash (https://git-scm.com/downloads/win). "
        "If installed but not in PATH, set environment variable pointing to your bash.exe, "
        "similar to: CLAUDE_CODE_GIT_BASH_PATH=C:\\Program Files\\Git\\bin\\bash.exe",
        file=sys.stderr,
    )
    sys.exit(1)


@lru_cache(maxsize=500)
def windows_path_to_posix_path(windows_path: str) -> str:
    if windows_path.startswith("\\\\"):
        return windows_path.replace("\\", "/")

    match = re.match(r"^([A-Za-z]):[/\\]", windows_path)
    if match:
        drive_letter = match.group(1).lower()
        return "/" + drive_letter + windows_path[2:].replace("\\", "/")

    return windows_path.replace("\\", "/")


@lru_cache(maxsize=500)
def posix_path_to_windows_path(posix_path: str) -> str:
    if posix_path.startswith("//"):
        return posix_path.replace("/", "\\")

    cygdrive_match = re.match(r"^/cygdrive/([A-Za-z])(/|$)", posix_path)
    if cygdrive_match:
        drive_letter = cygdrive_match.group(1).upper()
        prefix = "/cygdrive/" + cygdrive_match.group(1)
        rest = posix_path[len(prefix) :]
        result = drive_letter + ":" + (rest or "\\").replace("/", "\\")
        return result

    drive_match = re.match(r"^/([A-Za-z])(/|$)", posix_path)
    if drive_match:
        drive_letter = drive_match.group(1).upper()
        rest = posix_path[2:]
        return drive_letter + ":" + (rest or "\\").replace("/", "\\")

    return posix_path.replace("/", "\\")


def set_shell_if_windows() -> None:
    if get_platform() == "windows":
        git_bash_path = find_git_bash_path()
        os.environ["SHELL"] = git_bash_path

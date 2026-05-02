import os
import shutil
import subprocess
from functools import lru_cache

from .platform import get_platform

_GUI_EDITORS = [
    "code",
    "cursor",
    "windsurf",
    "codium",
    "subl",
    "atom",
    "gedit",
    "notepad++",
    "notepad",
]

_PLUS_N_EDITORS = {"vi", "vim", "nvim", "nano", "emacs", "pico", "micro", "helix", "hx"}

_VSCODE_FAMILY = {"code", "cursor", "windsurf", "codium"}


def classify_gui_editor(editor: str) -> str | None:
    base = os.path.basename(editor.split(" ")[0])
    for g in _GUI_EDITORS:
        if g in base:
            return g
    return None


@lru_cache(maxsize=1)
def get_external_editor() -> str | None:
    visual = os.environ.get("VISUAL", "").strip()
    if visual:
        return visual

    editor_env = os.environ.get("EDITOR", "").strip()
    if editor_env:
        return editor_env

    if get_platform() == "windows":
        return "start /wait notepad"

    editors = ["code", "vi", "nano"]
    for cmd in editors:
        if shutil.which(cmd):
            return cmd

    return None


def open_file_in_external_editor(file_path: str, line: int | None = None) -> bool:
    editor = get_external_editor()
    if not editor:
        return False

    parts = editor.split(" ")
    base_bin = parts[0]
    editor_args = parts[1:]
    gui_family = classify_gui_editor(editor)

    if gui_family:
        goto_argv = [file_path]
        if line:
            if gui_family in _VSCODE_FAMILY:
                goto_argv = ["-g", f"{file_path}:{line}"]
            elif gui_family == "subl":
                goto_argv = [f"{file_path}:{line}"]

        if get_platform() == "windows":
            goto_str = " ".join(f'"{a}"' for a in goto_argv)
            cmd_line = f"{editor} {goto_str}"
            try:
                subprocess.Popen(
                    cmd_line,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
                return True
            except (OSError, subprocess.SubprocessError):
                return False
        else:
            try:
                subprocess.Popen(
                    [base_bin, *editor_args, *goto_argv],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except (OSError, subprocess.SubprocessError):
                return False

    use_goto_line = bool(line and os.path.basename(base_bin) in _PLUS_N_EDITORS)

    if get_platform() == "windows":
        line_arg = f"+{line} " if use_goto_line else ""
        cmd_line = f'{editor} {line_arg}"{file_path}"'
        try:
            result = subprocess.run(
                cmd_line,
                shell=True,
                capture_output=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    else:
        args = [
            *editor_args,
            *([f"+{line}", file_path] if use_goto_line else [file_path]),
        ]
        try:
            result = subprocess.run(
                [base_bin, *args],
                capture_output=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

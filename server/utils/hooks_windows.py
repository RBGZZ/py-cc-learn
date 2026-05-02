import re
from collections.abc import Callable

from .platform import is_windows
from .windows_paths import windows_path_to_posix_path

DEFAULT_HOOK_SHELL: str = "bash"


def make_to_hook_path(
    shell_type: str = DEFAULT_HOOK_SHELL,
) -> Callable[[str], str]:
    is_power_shell = shell_type == "powershell"

    if is_windows() and not is_power_shell:

        def _to_hook_path(p: str) -> str:
            return windows_path_to_posix_path(p)

        return _to_hook_path

    def _identity(p: str) -> str:
        return p

    return _identity


def auto_prepend_bash(command: str, shell_type: str = DEFAULT_HOOK_SHELL) -> str:
    is_power_shell = shell_type == "powershell"
    if (
        is_windows()
        and not is_power_shell
        and re.search(r'\.sh(\s|$|")', command.strip())
        and not command.strip().startswith("bash ")
    ):
        return f"bash {command}"
    return command


def should_skip_shell_prefix(shell_type: str = DEFAULT_HOOK_SHELL) -> bool:
    return shell_type == "powershell"


def should_skip_env_file(shell_type: str = DEFAULT_HOOK_SHELL) -> bool:
    return shell_type == "powershell"

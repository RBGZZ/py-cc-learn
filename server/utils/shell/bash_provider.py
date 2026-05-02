import os
import re
from tempfile import gettempdir

from ..platform import get_platform
from ..windows_paths import windows_path_to_posix_path

_NUL_REDIRECT_REGEX = re.compile(
    r"(\d?&?>+\s*)[Nn][Uu][Ll](?=\s|$|[|&;)\n])",
)


def rewrite_windows_null_redirect(command: str) -> str:
    return _NUL_REDIRECT_REGEX.sub(r"\1/dev/null", command)


def _contains_heredoc(command: str) -> bool:
    if re.search(r"\d\s*<<\s*\d", command):
        return False
    if re.search(r"\[\[\s*\d+\s*<<\s*\d+\s*\]\]", command):
        return False
    if re.search(r"\$\(\(.*<<.*\)\)", command):
        return False
    heredoc_regex = re.compile(r'<<-?\s*(?:([\'"]?)(\w+)\1|\\(\w+))')
    return bool(heredoc_regex.search(command))


def _contains_multiline_string(command: str) -> bool:
    single_quote_multiline = re.compile(r"'(?:[^'\\]|\\.)*\n(?:[^'\\]|\\.)*'")
    double_quote_multiline = re.compile(r'"(?:[^"\\]|\\.)*\n(?:[^"\\]|\\.)*"')
    return bool(single_quote_multiline.search(command) or double_quote_multiline.search(command))


def _quote(args: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(a) for a in args)


def quote_shell_command(command: str, add_stdin_redirect: bool = True) -> str:
    if _contains_heredoc(command) or _contains_multiline_string(command):
        escaped = command.replace("'", "'\"'\"'")
        quoted = f"'{escaped}'"
        if _contains_heredoc(command):
            return quoted
        return f"{quoted} < /dev/null" if add_stdin_redirect else quoted

    if add_stdin_redirect:
        return _quote([command, "<", "/dev/null"])
    return _quote([command])


def _has_stdin_redirect(command: str) -> bool:
    return bool(re.search(r"(?:^|[\s;&|])<(?![<(])\s*\S+", command))


def should_add_stdin_redirect(command: str) -> bool:
    return not (_contains_heredoc(command) or _has_stdin_redirect(command))


async def create_bash_shell_provider(
    shell_path: str,
    skip_snapshot: bool = False,
):
    last_snapshot_file_path: str | None = None

    def get_spawn_args(command_string: str) -> list[str]:
        skip_login = last_snapshot_file_path is not None
        if skip_login:
            return ["-c", command_string]
        return ["-c", "-l", command_string]

    async def get_environment_overrides(
        command: str,
    ) -> dict[str, str]:
        return {}

    class BashShellProvider:
        def __init__(self):
            self.type = "bash"
            self.shell_path = shell_path
            self.detached = True
            self.get_spawn_args = get_spawn_args
            self.get_environment_overrides = get_environment_overrides

        async def build_exec_command(
            self,
            command: str,
            opts: dict,
        ) -> dict:
            nonlocal last_snapshot_file_path

            is_windows = get_platform() == "windows"
            tmpdir = gettempdir()
            shell_tmpdir = windows_path_to_posix_path(tmpdir) if is_windows else tmpdir

            cmd_id = opts["id"]
            sandbox_tmp_dir = opts.get("sandboxTmpDir")
            use_sandbox = opts.get("useSandbox", False)

            if use_sandbox and sandbox_tmp_dir:
                shell_cwd_file_path = os.path.join(sandbox_tmp_dir, f"cwd-{cmd_id}").replace(
                    "\\", "/"
                )
                cwd_file_path = os.path.join(sandbox_tmp_dir, f"cwd-{cmd_id}")
            else:
                shell_cwd_file_path = os.path.join(shell_tmpdir, f"claude-{cmd_id}-cwd").replace(
                    "\\", "/"
                )
                cwd_file_path = os.path.join(tmpdir, f"claude-{cmd_id}-cwd")

            normalized_command = rewrite_windows_null_redirect(command)
            add_stdin_redirect = should_add_stdin_redirect(normalized_command)
            quoted_command = quote_shell_command(normalized_command, add_stdin_redirect)

            command_parts: list[str] = []
            command_parts.append(f"eval {quoted_command}")
            command_parts.append(f"pwd -P >| {_quote([shell_cwd_file_path])}")
            command_string = " && ".join(command_parts)

            return {
                "commandString": command_string,
                "cwdFilePath": cwd_file_path,
            }

    return BashShellProvider()

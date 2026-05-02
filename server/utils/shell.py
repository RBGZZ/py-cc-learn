from __future__ import annotations

import asyncio
import functools
import os
import random
import shlex
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from server.utils.abort import AbortController, force_kill_process
from server.utils.log import log_error, log_for_debugging
from server.utils.platform import is_windows


class ShellType(str, Enum):
    BASH = "bash"
    POWERSHELL = "powershell"


DEFAULT_TIMEOUT_SECONDS = 30 * 60


class ShellResult:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        aborted: bool = False,
        timed_out: bool = False,
        background_task_id: Optional[str] = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.aborted = aborted
        self.timed_out = timed_out
        self.background_task_id = background_task_id

    @property
    def failed(self) -> bool:
        return self.exit_code != 0 and not self.aborted


def create_aborted_result(reason: Optional[str] = None) -> ShellResult:
    return ShellResult(
        stderr=reason or "Aborted",
        exit_code=130,
        aborted=True,
    )


def create_failed_result(error_message: str) -> ShellResult:
    return ShellResult(
        stderr=error_message,
        exit_code=126,
    )


@dataclass
class BuildExecResult:
    command_string: str
    cwd_file_path: str


class ShellProvider(ABC):
    @property
    @abstractmethod
    def shell_type(self) -> ShellType: ...

    @property
    @abstractmethod
    def shell_path(self) -> str: ...

    @property
    @abstractmethod
    def detached(self) -> bool: ...

    @abstractmethod
    async def build_exec_command(
        self,
        command: str,
        cmd_id: str,
        working_dir: Optional[str] = None,
    ) -> BuildExecResult: ...

    @abstractmethod
    def get_spawn_args(self, command_string: str) -> List[str]: ...

    async def get_environment_overrides(self, command: str) -> Dict[str, str]:
        return {}


class BashShellProvider(ShellProvider):
    def __init__(self, shell_path: str) -> None:
        self._shell_path = shell_path

    @property
    def shell_type(self) -> ShellType:
        return ShellType.BASH

    @property
    def shell_path(self) -> str:
        return self._shell_path

    @property
    def detached(self) -> bool:
        return False

    async def build_exec_command(
        self,
        command: str,
        cmd_id: str,
        working_dir: Optional[str] = None,
    ) -> BuildExecResult:
        cwd_file_path = _create_temp_tracker()
        if is_windows():
            cwd_tracker = f"pwd -P >| {cwd_file_path}"
        else:
            cwd_tracker = f"pwd -P >| {shlex.quote(cwd_file_path)}"
        full_command = f"{cwd_tracker}\n{command}"
        return BuildExecResult(
            command_string=full_command,
            cwd_file_path=cwd_file_path,
        )

    def get_spawn_args(self, command_string: str) -> List[str]:
        return [self._shell_path, "-c", command_string]

    async def get_environment_overrides(self, command: str) -> Dict[str, str]:
        overrides: Dict[str, str] = {}
        if is_windows():
            overrides["HOME"] = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        return overrides


class PowerShellShellProvider(ShellProvider):
    def __init__(self, shell_path: str) -> None:
        self._shell_path = shell_path

    @property
    def shell_type(self) -> ShellType:
        return ShellType.POWERSHELL

    @property
    def shell_path(self) -> str:
        return self._shell_path

    @property
    def detached(self) -> bool:
        return False

    async def build_exec_command(
        self,
        command: str,
        cmd_id: str,
        working_dir: Optional[str] = None,
    ) -> BuildExecResult:
        import base64

        cwd_file_path = _create_temp_tracker()
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return BuildExecResult(
            command_string=encoded,
            cwd_file_path=cwd_file_path,
        )

    def get_spawn_args(self, command_string: str) -> List[str]:
        return [
            self._shell_path,
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            command_string,
        ]

    async def get_environment_overrides(self, command: str) -> Dict[str, str]:
        return {}


def _create_temp_tracker() -> str:
    fd, path = tempfile.mkstemp(prefix="cwd_tracker_", suffix=".txt")
    os.close(fd)
    return path


def _is_executable(shell_path: str) -> bool:
    if not os.path.exists(shell_path):
        return False
    return os.access(shell_path, os.X_OK)


async def find_suitable_shell() -> str:
    shell_override = os.environ.get("CLAUDE_CODE_SHELL")
    if shell_override:
        is_supported = "bash" in shell_override or "zsh" in shell_override
        if is_supported and _is_executable(shell_override):
            log_for_debugging(f"Using shell override: {shell_override}")
            return shell_override
        log_for_debugging(
            f'CLAUDE_CODE_SHELL="{shell_override}" is not a valid bash/zsh path, '
            f"falling back to detection"
        )

    env_shell = os.environ.get("SHELL", "")
    is_env_shell_supported = env_shell and (
        "bash" in env_shell or "zsh" in env_shell
    )
    prefer_bash = "bash" in env_shell

    zsh_path = await asyncio.to_thread(shutil.which, "zsh")
    bash_path = await asyncio.to_thread(shutil.which, "bash")

    shell_paths = ["/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"]
    shell_order = ["bash", "zsh"] if prefer_bash else ["zsh", "bash"]

    candidate_shells: List[str] = []

    if is_env_shell_supported and _is_executable(env_shell):
        candidate_shells.append(env_shell)

    if prefer_bash:
        if bash_path:
            candidate_shells.append(bash_path)
    else:
        if zsh_path:
            candidate_shells.append(zsh_path)

    for shell_name in shell_order:
        for base_path in shell_paths:
            shell_candidate = os.path.join(base_path, shell_name)
            if shell_candidate not in candidate_shells:
                candidate_shells.append(shell_candidate)

    if not prefer_bash:
        if bash_path and bash_path not in candidate_shells:
            candidate_shells.append(bash_path)
    else:
        if zsh_path and zsh_path not in candidate_shells:
            candidate_shells.append(zsh_path)

    if is_windows():
        for git_bash in [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]:
            if git_bash not in candidate_shells:
                candidate_shells.append(git_bash)

    for shell_candidate in candidate_shells:
        if shell_candidate and _is_executable(shell_candidate):
            return shell_candidate

    error_msg = (
        "No suitable shell found. Claude CLI requires a Posix shell environment. "
        "Please ensure you have a valid shell installed and the SHELL environment variable set."
    )
    log_error(Exception(error_msg))
    raise RuntimeError(error_msg)


async def _get_shell_config_impl() -> ShellConfig:
    bin_shell = await find_suitable_shell()
    provider = BashShellProvider(bin_shell)
    return ShellConfig(provider=provider)


class ShellConfig:
    def __init__(self, provider: ShellProvider) -> None:
        self.provider = provider


_shell_config_cache: Optional[ShellConfig] = None


async def get_shell_config() -> ShellConfig:
    global _shell_config_cache
    if _shell_config_cache is None:
        _shell_config_cache = await _get_shell_config_impl()
    return _shell_config_cache


def _reset_shell_config_cache() -> None:
    global _shell_config_cache
    _shell_config_cache = None


async def find_powershell_path() -> Optional[str]:
    pwsh = shutil.which("pwsh")
    if pwsh:
        return pwsh
    ps = shutil.which("powershell")
    if ps:
        return ps
    if is_windows():
        for path in [
            r"C:\Program Files\PowerShell\7\pwsh.exe",
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        ]:
            if os.path.exists(path):
                return path
    return None


async def get_ps_provider() -> PowerShellShellProvider:
    ps_path = await find_powershell_path()
    if not ps_path:
        raise RuntimeError("PowerShell is not available")
    return PowerShellShellProvider(ps_path)


class ExecOptions:
    def __init__(
        self,
        timeout: Optional[float] = None,
        on_progress: Optional[Callable] = None,
        prevent_cwd_changes: bool = False,
        should_auto_background: bool = False,
        on_stdout: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.timeout = timeout
        self.on_progress = on_progress
        self.prevent_cwd_changes = prevent_cwd_changes
        self.should_auto_background = should_auto_background
        self.on_stdout = on_stdout


async def exec_command(
    command: str,
    abort_signal: AbortController,
    shell_type: ShellType = ShellType.BASH,
    options: Optional[ExecOptions] = None,
) -> ShellResult:
    if options is None:
        options = ExecOptions()

    cmd_timeout = options.timeout or DEFAULT_TIMEOUT_SECONDS
    cmd_id = format(random.randint(0, 0xFFFF), "04x")

    if shell_type == ShellType.BASH:
        config = await get_shell_config()
        provider = config.provider
    elif shell_type == ShellType.POWERSHELL:
        provider = await get_ps_provider()
    else:
        config = await get_shell_config()
        provider = config.provider

    cwd = os.getcwd()

    if abort_signal.aborted:
        return create_aborted_result(abort_signal.reason)

    build_result = await provider.build_exec_command(command, cmd_id)
    command_string = build_result.command_string
    shell_args = provider.get_spawn_args(command_string)
    env_overrides = await provider.get_environment_overrides(command)

    try:
        process = await asyncio.create_subprocess_exec(
            shell_args[0],
            *shell_args[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env={
                **os.environ,
                "SHELL": provider.shell_path if shell_type == ShellType.BASH else "",
                "GIT_EDITOR": "true",
                "CLAUDECODE": "1",
                **env_overrides,
            },
        )

        stdout_parts: List[str] = []
        stderr_parts: List[str] = []

        async def _read_stdout() -> None:
            assert process.stdout is not None
            while True:
                try:
                    line_bytes = await process.stdout.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace")
                    stdout_parts.append(line)
                    if options and options.on_stdout:
                        options.on_stdout(line)
                except Exception:
                    break

        async def _read_stderr() -> None:
            assert process.stderr is not None
            while True:
                try:
                    line_bytes = await process.stderr.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace")
                    stderr_parts.append(line)
                except Exception:
                    break

        async def _wait_process() -> int:
            return await process.wait()

        read_stdout_task = asyncio.create_task(_read_stdout())
        read_stderr_task = asyncio.create_task(_read_stderr())
        wait_task = asyncio.create_task(_wait_process())

        async def _abort_handler() -> None:
            await abort_signal.wait()
            await force_kill_process(process)

        abort_task = asyncio.create_task(_abort_handler())

        try:
            exit_code = await asyncio.wait_for(wait_task, timeout=cmd_timeout)
        except asyncio.TimeoutError:
            await force_kill_process(process)
            exit_code = -1
            timed_out = True
        else:
            timed_out = False
        finally:
            abort_task.cancel()
            try:
                await abort_task
            except asyncio.CancelledError:
                pass

        await asyncio.gather(read_stdout_task, read_stderr_task, return_exceptions=True)

        if abort_signal.aborted:
            return create_aborted_result(abort_signal.reason)

        return ShellResult(
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            exit_code=exit_code,
            aborted=abort_signal.aborted,
            timed_out=timed_out,
        )

    except Exception as e:
        log_for_debugging(f"Shell exec error: {e}")
        if abort_signal.aborted:
            return create_aborted_result(abort_signal.reason)
        return create_failed_result(str(e))


def set_cwd(path: str, relative_to: Optional[str] = None) -> None:
    if os.path.isabs(path):
        resolved = path
    else:
        resolved = os.path.abspath(
            os.path.join(relative_to or os.getcwd(), path)
        )

    try:
        physical_path = os.path.realpath(resolved)
    except OSError as e:
        if e.errno == 2:
            raise FileNotFoundError(f'Path "{resolved}" does not exist') from e
        raise

    os.chdir(physical_path)

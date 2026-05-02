from __future__ import annotations

import asyncio
import functools
import os
import random
import shlex
import shutil
import tempfile
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from server.utils.abort import AbortController, force_kill_process
from server.utils.log import log_error, log_for_debugging
from server.utils.platform import get_platform, is_windows


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


class ShellProvider(ABC):
    @property
    @abstractmethod
    def shell_type(self) -> ShellType: ...

    @property
    @abstractmethod
    def shell_path(self) -> str: ...

    @abstractmethod
    def build_exec_command(
        self, command: str, working_dir: Optional[str] = None
    ) -> List[str]: ...

    def get_environment_overrides(self, command: str) -> Dict[str, str]:
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

    def build_exec_command(
        self, command: str, working_dir: Optional[str] = None
    ) -> List[str]:
        cwd_tracker = self._build_cwd_tracker()
        full_command = f"{cwd_tracker}\n{command}"
        return [self._shell_path, "-c", full_command]

    @staticmethod
    def _build_cwd_tracker() -> str:
        if is_windows():
            tracker_path = _create_temp_tracker()
            return f"pwd -P >| {tracker_path}"
        else:
            tracker_path = _create_temp_tracker()
            return f"pwd -P >| {shlex.quote(tracker_path)}"

    def get_environment_overrides(self, command: str) -> Dict[str, str]:
        overrides: Dict[str, str] = {}
        if is_windows():
            overrides["HOME"] = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        return overrides

    @property
    def detached(self) -> bool:
        return False


class PowerShellShellProvider(ShellProvider):
    def __init__(self, shell_path: str) -> None:
        self._shell_path = shell_path

    @property
    def shell_type(self) -> ShellType:
        return ShellType.POWERSHELL

    @property
    def shell_path(self) -> str:
        return self._shell_path

    def build_exec_command(
        self, command: str, working_dir: Optional[str] = None
    ) -> List[str]:
        import base64

        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return [
            self._shell_path,
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ]

    @property
    def detached(self) -> bool:
        return False


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

    shell_paths = ["/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"]
    shell_order = ["bash", "zsh"] if prefer_bash else ["zsh", "bash"]

    candidate_shells: List[str] = []

    if is_env_shell_supported and _is_executable(env_shell):
        candidate_shells.append(env_shell)

    for shell_name in shell_order:
        for base_path in shell_paths:
            shell_path = os.path.join(base_path, shell_name)
            if shell_path not in candidate_shells:
                candidate_shells.append(shell_path)

    if is_windows():
        for git_bash in [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]:
            if git_bash not in candidate_shells:
                candidate_shells.append(git_bash)

    for shell_path in candidate_shells:
        if shell_path and _is_executable(shell_path):
            return shell_path

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


@functools.lru_cache(maxsize=1)
def _get_cached_shell_config() -> asyncio.Future:
    loop = asyncio.get_event_loop()
    return loop.create_task(_get_shell_config_impl())


async def get_shell_config() -> ShellConfig:
    return await _get_cached_shell_config()


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


async def get_ps_provider() -> ShellProvider:
    ps_path = await find_powershell_path()
    if not ps_path:
        raise RuntimeError("PowerShell is not available")
    return PowerShellShellProvider(ps_path)


_SHELL_RESOLVER: Dict[ShellType, Callable[[], Any]] = {
    "bash": lambda: get_shell_config().then(lambda c: c.provider),
    "powershell": lambda: get_ps_provider(),
}


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

    if shell_type == ShellType.BASH:
        config = await get_shell_config()
        provider = config.provider
    elif shell_type == ShellType.POWERSHELL:
        provider = await get_ps_provider()
    else:
        provider = (await get_shell_config()).provider

    cmd_id = format(random.randint(0, 0xFFFF), "04x")
    cwd = os.getcwd()

    if abort_signal.aborted:
        return create_aborted_result(abort_signal.reason)

    shell_args = provider.build_exec_command(command, working_dir=cwd)
    env_overrides = provider.get_environment_overrides(command)

    try:
        process = await asyncio.create_subprocess_exec(
            *shell_args,
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
            exit_code = await asyncio.wait_for(
                wait_task, timeout=cmd_timeout
            )
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

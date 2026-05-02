import base64
import os
from tempfile import gettempdir


def build_power_shell_args(cmd: str) -> list[str]:
    return ["-NoProfile", "-NonInteractive", "-Command", cmd]


def encode_power_shell_command(ps_command: str) -> str:
    return base64.b64encode(ps_command.encode("utf-16-le")).decode("ascii")


def create_power_shell_provider(shell_path: str):
    current_sandbox_tmp_dir: str | None = None

    def get_spawn_args(command_string: str) -> list[str]:
        return build_power_shell_args(command_string)

    async def get_environment_overrides(
        command: str = "",
    ) -> dict[str, str]:
        return {}

    class PowerShellShellProvider:
        def __init__(self):
            self.type = "powershell"
            self.shell_path = shell_path
            self.detached = False
            self.get_spawn_args = get_spawn_args
            self.get_environment_overrides = get_environment_overrides

        async def build_exec_command(
            self,
            command: str,
            opts: dict,
        ) -> dict:
            nonlocal current_sandbox_tmp_dir

            use_sandbox = opts.get("useSandbox", False)
            sandbox_tmp_dir = opts.get("sandboxTmpDir")
            cmd_id = opts["id"]

            current_sandbox_tmp_dir = sandbox_tmp_dir if use_sandbox else None

            if use_sandbox and sandbox_tmp_dir:
                cwd_file_path = os.path.join(sandbox_tmp_dir, f"claude-pwd-ps-{cmd_id}").replace(
                    "\\", "/"
                )
            else:
                cwd_file_path = os.path.join(gettempdir(), f"claude-pwd-ps-{cmd_id}")

            escaped_cwd_file_path = cwd_file_path.replace("'", "''")

            cwd_tracking = (
                "\n"
                "; $_ec = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } "
                "elseif ($?) { 0 } else { 1 }\n"
                "; (Get-Location).Path | Out-File -FilePath "
                f"'{escaped_cwd_file_path}' -Encoding utf8 -NoNewline\n"
                "; exit $_ec"
            )
            ps_command = command + cwd_tracking

            if use_sandbox:
                safe_shell_path = shell_path.replace("'", "'\\''")
                command_string = " ".join(
                    [
                        f"'{safe_shell_path}'",
                        "-NoProfile",
                        "-NonInteractive",
                        "-EncodedCommand",
                        encode_power_shell_command(ps_command),
                    ]
                )
            else:
                command_string = ps_command

            return {
                "commandString": command_string,
                "cwdFilePath": cwd_file_path,
            }

    return PowerShellShellProvider()

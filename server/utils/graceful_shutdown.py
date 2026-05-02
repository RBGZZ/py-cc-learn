import contextlib
import os
import signal
import subprocess
import time

from .platform import get_platform


def terminate_process_tree(pid: int) -> None:
    platform = get_platform()

    if platform == "windows":
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
    else:
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)

        time.sleep(2)

        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)

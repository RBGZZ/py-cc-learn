"""Cold start benchmark: measure Python import + FastAPI app creation time."""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request


def measure_import_time() -> float:
    start = time.perf_counter()
    subprocess.run(
        [sys.executable, "-c", "from server.main import app"],
        capture_output=True,
        timeout=30,
    )
    return time.perf_counter() - start


def measure_cli_help() -> float:
    start = time.perf_counter()
    subprocess.run(
        [sys.executable, "-m", "server.cli", "--help"],
        capture_output=True,
        timeout=30,
    )
    return time.perf_counter() - start


def measure_uvicorn_startup() -> float:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    start = time.perf_counter()
    deadline = start + 60.0
    try:
        while time.perf_counter() < deadline:
            try:
                urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=1)
                return time.perf_counter() - start
            except Exception:
                time.sleep(0.1)
        return -1.0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main():
    print("=== Cold Start Benchmark ===")

    # Warmup
    print("Warmup...")
    measure_import_time()

    # Measure (3 runs)
    times = []
    for i in range(3):
        t = measure_import_time()
        times.append(t)
        print(f"  Run {i+1}: {t:.4f}s")
    avg_import = sum(times) / len(times)
    print(f"  Average import+app: {avg_import:.4f}s")
    assert avg_import < 5.0, f"Cold start too slow: {avg_import:.3f}s"

    cli_time = measure_cli_help()
    print(f"  CLI --help: {cli_time:.4f}s")

    uvicorn_time = measure_uvicorn_startup()
    print(f"  Uvicorn startup: {uvicorn_time:.4f}s")

    print(f"\nPASS: cold_start={avg_import:.2f}s (target < 5s)")


if __name__ == "__main__":
    main()

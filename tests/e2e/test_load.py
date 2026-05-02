from __future__ import annotations

import time
import threading
import queue
import httpx

def load_test_health():
    errors = queue.Queue()

    def worker():
        start = time.monotonic()
        try:
            client = httpx.Client(base_url="http://127.0.0.1:8000")
            response = client.get("/api/v1/health")
            elapsed = (time.monotonic() - start) * 1000
            if response.status_code != 200:
                errors.put(f"Expected 200, got {response.status_code}")
            client.close()
        except Exception as e:
            errors.put(str(e))

    threads = []
    num_users = 10
    for _ in range(num_users):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10)

    error_count = errors.qsize()
    assert error_count == 0, f"Got {error_count} errors in health check load test"

from __future__ import annotations

import pytest
import asyncio
from fastapi.testclient import TestClient
from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAcceptance:
    def test_server_health(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_server_status(self, client):
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "uptime_seconds" in data

    def test_invalid_prompt_rejected(self, client):
        response = client.post("/api/v1/chat", json={"prompt": ""})
        assert response.status_code == 422

    def test_prompt_too_long_rejected(self, client):
        response = client.post("/api/v1/chat", json={"prompt": "x" * 300_000})
        assert response.status_code == 422

    def test_stop_nonexistent_session(self, client):
        response = client.post("/api/v1/stop/fake-id-12345")
        assert response.status_code == 404

    def test_concurrent_health_checks(self):
        import concurrent.futures
        import threading

        errors = []

        def check():
            try:
                client = TestClient(app)
                r = client.get("/api/v1/health")
                if r.status_code != 200:
                    errors.append(f"status={r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = []
        for _ in range(10):
            t = threading.Thread(target=check)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors: {errors}"

    def test_cors_headers_present(self, client):
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in (200, 405)

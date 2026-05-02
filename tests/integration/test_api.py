from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok"}

    def test_health_has_request_id(self, client):
        response = client.get("/api/v1/health")
        assert "x-request-id" in response.headers


class TestStatusEndpoint:
    def test_status_returns_200(self, client):
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "model" in data
        assert "permission_mode" in data
        assert "total_cost_usd" in data
        assert "context_limit" in data
        assert "uptime_seconds" in data


class TestChatEndpoint:
    def test_chat_empty_prompt(self, client):
        response = client.post("/api/v1/chat", json={"prompt": ""})
        assert response.status_code == 422

    def test_chat_prompt_too_long(self, client):
        response = client.post("/api/v1/chat", json={"prompt": "a" * 200_001})
        assert response.status_code == 422

    def test_chat_valid_prompt_requires_provider(self, client):
        response = client.post("/api/v1/chat", json={"prompt": "Hello"})
        assert response.status_code in (200, 500)


class TestUploadImageEndpoint:
    def test_upload_non_image(self, client):
        response = client.post(
            "/api/v1/upload/image",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
        assert response.status_code == 415

    def test_upload_empty_image(self, client):
        response = client.post(
            "/api/v1/upload/image",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert response.status_code == 422


class TestStopEndpoint:
    def test_stop_nonexistent_session(self, client):
        response = client.post("/api/v1/stop/nonexistent-id")
        assert response.status_code == 404

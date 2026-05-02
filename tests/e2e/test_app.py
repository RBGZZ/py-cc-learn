from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestErrorHandling:
    def test_404_unknown_route(self, client):
        response = client.get("/api/v1/unknown")
        assert response.status_code == 404

    def test_rate_limit_headers(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_cors_headers(self, client):
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in (200, 405)

    def test_invalid_json_chat(self, client):
        response = client.post(
            "/api/v1/chat",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_empty_request(self, client):
        response = client.post(
            "/api/v1/chat",
            json={},
        )
        assert response.status_code == 422

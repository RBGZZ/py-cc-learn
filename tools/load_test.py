"""Locust load test for /api/v1/chat endpoint."""
from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class ChatUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def chat(self):
        payload = {
            "prompt": "Say hello in one word.",
            "session_id": str(uuid.uuid4()),
        }
        headers = {"Content-Type": "application/json"}
        with self.client.post(
            "/api/v1/chat",
            json=payload,
            headers=headers,
            catch_response=True,
            stream=True,
            timeout=30,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return

            body = b""
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    body += chunk
                    if len(body) > 1_000_000:
                        response.failure("Response too large")
                        return

            text = body.decode("utf-8", errors="replace")
            if "event: error" in text:
                response.failure("Stream contained error event")
            else:
                response.success()

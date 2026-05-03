"""Production verify: Locust load test with configurable model."""
from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, events, task

MODEL_NAME = os.environ.get("LOAD_TEST_MODEL", "deepseek-v4-flash")


class ChatUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def chat(self):
        payload = {
            "prompt": "Say hello in one word.",
            "model": MODEL_NAME,
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
                if response.status_code == 429:
                    response.success()  # Rate-limited is expected under load
                    return
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


@events.init_command_line_parser.add_listener
def add_model_argument(parser):
    parser.add_argument(
        "--model", type=str, env_var="LOAD_TEST_MODEL",
        default="deepseek-v4-flash",
        help="Model name to use for load testing",
    )


@events.init.add_listener
def set_model(environment, **kwargs):
    global MODEL_NAME
    if hasattr(environment, "parsed_options") and environment.parsed_options:
        MODEL_NAME = getattr(
            environment.parsed_options, "model", "deepseek-v4-flash"
        )

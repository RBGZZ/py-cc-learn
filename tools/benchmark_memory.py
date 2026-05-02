"""Memory leak detection: run N query loops and check RSS."""
from __future__ import annotations

import asyncio
import os
import time
import uuid

import psutil

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.provider import ProviderConfig, StreamEvent


class NoopProvider:
    def __init__(self):
        self.config = ProviderConfig(model="noop", api_key="", max_tokens=100)

    def get_default_model(self):
        return "noop"

    async def stream_chat(self, messages, system_prompt=None, tools=None):
        yield StreamEvent(
            type="text_delta", data={"type": "text_delta", "text": "."}
        )
        yield StreamEvent(
            type="assistant",
            data={
                "type": "assistant",
                "uuid": str(uuid.uuid4()),
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "ok"}],
                    "model": "noop",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        )
        yield StreamEvent(type="message_stop", data={})

    def supports_thinking(self):
        return False


async def run_loops(n: int = 100):
    provider = NoopProvider()
    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=[], system_prompt="test", max_turns=1
    ))

    for i in range(n):
        events = []
        async for event in engine.submit_message(f"msg_{i}", is_meta=True):
            events.append(event)
        engine.state.messages = engine.state.messages[-10:]

    return engine


def get_rss_mb():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024


def main():
    print("=== Memory Benchmark ===")
    initial_rss = get_rss_mb()
    print(f"  Initial RSS: {initial_rss:.1f} MB")

    start = time.perf_counter()
    asyncio.run(run_loops(500))
    elapsed = time.perf_counter() - start

    final_rss = get_rss_mb()
    growth = final_rss - initial_rss
    print(f"  Final RSS: {final_rss:.1f} MB")
    print(f"  Growth: {growth:.1f} MB")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Per-loop: {elapsed*1000/500:.2f}ms")

    assert growth < 500, f"Memory growth too high: {growth:.1f} MB"
    print(f"\nPASS: memory_growth={growth:.1f}MB (target < 500MB)")


if __name__ == "__main__":
    main()

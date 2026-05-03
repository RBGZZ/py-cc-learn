"""Multi-turn conversation benchmark using NoopProvider, N rounds."""
from __future__ import annotations

import asyncio
import os
import statistics
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


def get_rss_mb():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024


async def run_multiturn(n: int = 50):
    provider = NoopProvider()
    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=[], system_prompt="test", max_turns=50,
    ))

    latencies = []
    for i in range(n):
        start = time.perf_counter()
        async for _event in engine.submit_message(f"round_{i}", is_meta=True):
            pass
        latencies.append(time.perf_counter() - start)

    return latencies, engine


def main():
    n_rounds = 50
    print("=== Multi-Turn Benchmark ===")

    initial_rss = get_rss_mb()
    print(f"  Initial RSS: {initial_rss:.1f} MB")

    start = time.perf_counter()
    latencies, engine = asyncio.run(run_multiturn(n_rounds))
    elapsed = time.perf_counter() - start

    final_rss = get_rss_mb()
    growth = final_rss - initial_rss

    sorted_lat = sorted(latencies)
    mean_lat = statistics.mean(latencies)
    p50 = sorted_lat[int(n_rounds * 0.5)]
    p99 = sorted_lat[int(n_rounds * 0.99)]

    print(f"  Rounds: {n_rounds}")
    print(f"  Total time: {elapsed:.3f}s")
    print(f"  Mean latency: {mean_lat*1000:.2f}ms")
    print(f"  P50 latency: {p50*1000:.2f}ms")
    print(f"  P99 latency: {p99*1000:.2f}ms")
    print(f"  Final RSS: {final_rss:.1f} MB")
    print(f"  RSS growth: {growth:.1f} MB")
    print(f"  Avg RSS/round: {growth/n_rounds:.2f} MB")

    assert growth < 200, f"Memory growth too high: {growth:.1f} MB"
    print(
        f"\nPASS: mean_lat={mean_lat*1000:.1f}ms "
        f"p50={p50*1000:.1f}ms p99={p99*1000:.1f}ms "
        f"memory_growth={growth:.1f}MB"
    )


if __name__ == "__main__":
    main()

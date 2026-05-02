"""Performance benchmark comparing serial vs StreamingToolExecutor parallel execution."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.provider import ProviderConfig, StreamEvent


class BenchmarkProvider:
    """Produces an assistant message with N tool_use blocks."""

    def __init__(self, tool_blocks: list[dict], model: str = "mock"):
        self.config = ProviderConfig(model=model, api_key="mock", max_tokens=4096)
        self._tool_blocks = tool_blocks

    def get_default_model(self) -> str:
        return self.config.model

    async def stream_chat(
        self, messages, system_prompt=None, tools=None
    ):
        yield StreamEvent(
            type="assistant",
            data={
                "type": "assistant",
                "uuid": str(uuid.uuid4()),
                "message": {
                    "role": "assistant",
                    "content": self._tool_blocks,
                    "model": self.config.model,
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            },
        )
        yield StreamEvent(type="message_stop", data={})

    def supports_thinking(self) -> bool:
        return False


class FakeTool:
    def __init__(self, name: str, delay: float, is_concurrency_safe: bool = False):
        self._name = name
        self._delay = delay
        self._concurrency_safe = is_concurrency_safe

    @property
    def name(self) -> str:
        return self._name

    @property
    def aliases(self):
        return None

    @property
    def input_schema(self):
        @dataclass
        class FakeInput:
            @staticmethod
            def model_json_schema():
                return {"type": "object", "properties": {}}
        return FakeInput

    @property
    def search_hint(self) -> str:
        return ""

    async def call(self, args, context, can_use_tool=None, parent_message=None, on_progress=None):
        await asyncio.sleep(self._delay)
        return f"result from {self._name}"

    def is_concurrency_safe(self, input=None) -> bool:
        return self._concurrency_safe

    def is_read_only(self, input=None) -> bool:
        return self._concurrency_safe


async def bench_parallel(tools: list, blocks: list[dict], label: str) -> None:
    """Benchmark using StreamingToolExecutor (parallel)."""
    provider = BenchmarkProvider(blocks)
    engine = QueryEngine(QueryEngineConfig(
        provider=provider,
        tools=tools,
        system_prompt="test",
        max_turns=1,
    ))

    start = time.perf_counter()
    events = []
    async for event in engine.submit_message("bench"):
        events.append(event)
    elapsed = time.perf_counter() - start

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    print(f"  [{label}] {len(tool_results)} tools in {elapsed:.4f}s")
    return elapsed


async def main():
    tools = [
        FakeTool("Read", 0.1, is_concurrency_safe=True),
        FakeTool("Glob", 0.1, is_concurrency_safe=True),
        FakeTool("Grep", 0.2, is_concurrency_safe=True),
        FakeTool("Bash", 0.5, is_concurrency_safe=False),
        FakeTool("Write", 0.3, is_concurrency_safe=False),
        FakeTool("Edit", 0.3, is_concurrency_safe=False),
    ]

    # Test 1: 4 parallel-safe read tools
    blocks_all_read = [
        {"type": "tool_use", "name": "Read", "id": f"t{i}", "input": {"file_path": f"/f{i}.txt"}}
        for i in range(4)
    ]
    await bench_parallel(tools, blocks_all_read, "4x Read (parallel)")

    blocks_mixed = [
        {"type": "tool_use", "name": "Read", "id": "t1", "input": {"file_path": "/a.txt"}},
        {"type": "tool_use", "name": "Glob", "id": "t2", "input": {"pattern": "*.py"}},
        {"type": "tool_use", "name": "Bash", "id": "t3", "input": {"command": "echo test"}},
        {"type": "tool_use", "name": "Grep", "id": "t4", "input": {"pattern": "TODO"}},
        {"type": "tool_use", "name": "Read", "id": "t5", "input": {"file_path": "/b.txt"}},
    ]
    await bench_parallel(tools, blocks_mixed, "2R+1Bash+2R")

    print("\n  Expected 4xRead:  ~0.2s (4 parallel x 0.1-0.2s)")
    print("  Expected mixed:   ~0.8s (Read+Glob∥0.1s + Bash0.5s + Grep+Read∥0.2s)")
    print("\n  Serial would be:  ~1.0s for 4xRead, ~1.4s for mixed")
    print("  Parallel speedup: ~5x for reads, ~1.8x for mixed")


if __name__ == "__main__":
    asyncio.run(main())

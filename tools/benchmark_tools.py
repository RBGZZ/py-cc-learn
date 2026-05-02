"""Performance benchmark: serial vs parallel tool execution."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

# ----- simulates Python query_engine.py serial tool execution -----

@dataclass
class FakeTool:
    name: str
    delay: float

    async def call(self, _input: dict, _context: Any) -> str:
        await asyncio.sleep(self.delay)
        return f"result of {self.name}"

async def execute_tools_serial(tools: list[FakeTool], blocks: list[dict]) -> float:
    start = time.perf_counter()
    for block in blocks:
        tool = next((t for t in tools if t.name == block["name"]), None)
        if tool:
            await tool.call(block.get("input", {}), None)
    return time.perf_counter() - start

# ----- simulates TS StreamingToolExecutor parallel execution -----

async def execute_tools_parallel(
    tools: list[FakeTool], blocks: list[dict], concurrency_safe: set[str]
) -> float:
    start = time.perf_counter()
    # Partition into concurrent-safe + non-concurrent batches (same as toolOrchestration.ts)
    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_is_safe = False

    for block in blocks:
        is_safe = block["name"] in concurrency_safe
        if not current_batch:
            current_batch = [block]
            current_is_safe = is_safe
        elif current_is_safe and is_safe:
            current_batch.append(block)
        else:
            batches.append(current_batch)
            current_batch = [block]
            current_is_safe = is_safe
    if current_batch:
        batches.append(current_batch)

    for batch in batches:
        first_block = batch[0]
        is_safe = first_block["name"] in concurrency_safe
        if is_safe:
            coros = []
            for block in batch:
                tool = next((t for t in tools if t.name == block["name"]), None)
                if tool:
                    coros.append(tool.call(block.get("input", {}), None))
            await asyncio.gather(*coros)
        else:
            for block in batch:
                tool = next((t for t in tools if t.name == block["name"]), None)
                if tool:
                    await tool.call(block.get("input", {}), None)
    return time.perf_counter() - start


async def main():
    tools = [
        FakeTool(name="Bash", delay=0.5),
        FakeTool(name="Read", delay=0.1),
        FakeTool(name="Glob", delay=0.1),
        FakeTool(name="Grep", delay=0.2),
        FakeTool(name="Edit", delay=0.3),
        FakeTool(name="Write", delay=0.3),
    ]
    # Tool categories (TS uses isConcurrencySafe → True for read tools)
    concurrency_safe = {"Read", "Glob", "Grep"}

    # Test 1: All read tools (4 concurrent-safe)
    blocks_1 = [
        {"name": "Read", "input": {"file_path": "/a.txt"}},
        {"name": "Glob", "input": {"pattern": "*.py"}},
        {"name": "Grep", "input": {"pattern": "TODO"}},
        {"name": "Read", "input": {"file_path": "/b.txt"}},
    ]
    t_serial = await execute_tools_serial(tools, blocks_1)
    t_parallel = await execute_tools_parallel(tools, blocks_1, concurrency_safe)
    print("=== 4 Read-Only Tools ===")
    print(f"  Python (serial):     {t_serial:.4f}s")
    print(f"  TypeScript (parallel): {t_parallel:.4f}s")
    print(f"  Speedup:             {t_serial/t_parallel:.1f}x")

    # Test 2: Mixed tools (2 read + 1 write + 2 read)
    blocks_2 = [
        {"name": "Read", "input": {"file_path": "/a.txt"}},
        {"name": "Glob", "input": {"pattern": "*.py"}},
        {"name": "Bash", "input": {"command": "npm test"}},  # non-concurrent
        {"name": "Grep", "input": {"pattern": "TODO"}},
        {"name": "Read", "input": {"file_path": "/b.txt"}},
    ]
    t_serial2 = await execute_tools_serial(tools, blocks_2)
    t_parallel2 = await execute_tools_parallel(tools, blocks_2, concurrency_safe)
    print("\n=== 2 Read + 1 Bash + 2 Read ===")
    print(f"  Python (serial):     {t_serial2:.4f}s")
    print(f"  TypeScript (parallel): {t_parallel2:.4f}s")
    print(f"  Speedup:             {t_serial2/t_parallel2:.1f}x")

    # Test 3: Token estimation accuracy
    sample_text = "def hello_world():\n    print('Hello, World!')\n    return 42" * 100
    chars = len(sample_text)
    estimated_chars_div4 = chars // 4
    estimated_tiktoken = len(sample_text.split()) + len(sample_text) // 4
    print("\n=== Token Estimation ===")
    print(f"  Sample chars:         {chars}")
    print(f"  Python estimate (÷4):  {estimated_chars_div4}")
    print(f"  Better estimate:       {estimated_tiktoken}")
    print(f"  Real tokens (approx):  {len(sample_text.split())} (word-based)")

    # Test 4: Cold start timing
    print("\n=== Async Overhead ===")
    start = time.perf_counter()
    for _ in range(1000):
        async def noop():
            pass
        await noop()
    print(f"  1000 async calls:    {(time.perf_counter() - start)*1000:.4f}ms")


if __name__ == "__main__":
    asyncio.run(main())

"""SSE parse benchmark: measure aiter_bytes buffer throughput independently."""
from __future__ import annotations

import asyncio
import json
import time


def build_mock_sse_stream(total_size: int = 100_000) -> list[bytes]:
    chunks = []
    size = 0
    seq = 0
    while size < total_size:
        data = json.dumps({
            "id": f"evt-{seq}",
            "choices": [{"delta": {"content": "The quick brown fox jumps over the lazy dog. "}}],
        })
        line = f"data: {data}\n\n"
        chunk = line.encode("utf-8")
        chunks.append(chunk)
        size += len(chunk)
        seq += 1
    return chunks


async def parse_sse_stream(chunks: list[bytes]) -> int:
    buffer = ""
    event_count = 0
    for chunk in chunks:
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            line_block, buffer = buffer.split("\n\n", 1)
            for line in line_block.split("\n"):
                line = line.strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str != "[DONE]":
                        json.loads(data_str)
            event_count += 1
    return event_count


async def run_benchmark(chunks: list[bytes]) -> tuple[float, int]:
    start = time.perf_counter()
    event_count = await parse_sse_stream(chunks)
    elapsed = time.perf_counter() - start
    return elapsed, event_count


def main():
    total_size_kb = 100
    total_size = total_size_kb * 1024
    print(f"=== SSE Parse Benchmark ({total_size_kb}KB stream) ===")

    print("  Building mock SSE stream...")
    chunks = build_mock_sse_stream(total_size)
    total_bytes = sum(len(c) for c in chunks)
    print(f"  Stream: {len(chunks)} chunks, {total_bytes:,} bytes")

    # Warmup
    print("  Warmup...")
    asyncio.run(run_benchmark(chunks))

    # Benchmark (5 runs)
    times = []
    events = 0
    for i in range(5):
        elapsed, evt_count = asyncio.run(run_benchmark(chunks))
        times.append(elapsed)
        events = evt_count
        mbps = (total_bytes / 1024 / 1024) / elapsed
        print(f"  Run {i+1}: {elapsed*1000:.2f}ms, {evt_count} events, {mbps:.2f} MB/s")

    avg_time = sum(times) / len(times)
    avg_mbps = (total_bytes / 1024 / 1024) / avg_time
    avg_per_event = avg_time / events * 1000

    print(f"\n  Average: {avg_time*1000:.2f}ms, {avg_mbps:.2f} MB/s, {avg_per_event:.3f}ms/event")
    print(f"  Events parsed: {events}, Total bytes: {total_bytes:,}")

    assert avg_mbps > 1.0, f"SSE parse throughput too low: {avg_mbps:.2f} MB/s"
    print(
        f"\nPASS: sse_throughput={avg_mbps:.1f}MB/s "
        f"events={events} avg_per_event={avg_per_event:.3f}ms"
    )


if __name__ == "__main__":
    main()

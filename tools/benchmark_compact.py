"""Compact pipeline benchmark: measure snip, microcompact, and auto-compact."""
from __future__ import annotations

import time

from server.services.compact import (
    get_compact_prompt,
    microcompact_messages,
    rough_token_count_for_messages,
)


def build_mock_messages(token_target: int = 180_000) -> list[dict]:
    filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 200

    messages = []
    total = 0
    turn = 0
    while total < token_target:
        user_msg = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": f"Question {turn}: {filler[:500]}"}],
            },
        }

        assistant_content = [
            {"type": "text", "text": f"Answer {turn}: {filler[:2000]}"},
            {
                "type": "tool_use",
                "name": "Read",
                "id": f"tool_{turn}",
                "input": {"file_path": f"/data/file_{turn}.txt"},
            },
        ]
        assistant_msg = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": assistant_content,
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 100, "output_tokens": 100},
            },
        }

        tool_result = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"tool_{turn}",
                        "content": filler[:10000],
                    }
                ],
            },
        }

        messages.append(user_msg)
        messages.append(assistant_msg)
        messages.append(tool_result)

        total = rough_token_count_for_messages(messages, use_tiktoken=False)
        turn += 1

    return messages


def main():
    print("=== Compact Pipeline Benchmark ===")

    print("  Building 180K token mock message list...")
    build_start = time.perf_counter()
    messages = build_mock_messages(180_000)
    build_time = time.perf_counter() - build_start

    token_count = rough_token_count_for_messages(messages, use_tiktoken=False)
    print(f"  Built {len(messages)} messages, ~{token_count:,} tokens in {build_time:.2f}s")

    # 1. Micro-Compact (snip)
    print("  Running microcompact...")
    mc_start = time.perf_counter()
    mc_result = microcompact_messages(messages)
    mc_time = time.perf_counter() - mc_start
    print(f"  Microcompact: {mc_time*1000:.1f}ms, tokens_saved={mc_result['tokens_saved']:,}")

    # 2. Compact prompt assembly
    print("  Assembling compact prompt...")
    cp_start = time.perf_counter()
    prompt = get_compact_prompt()
    prompt_msg = {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
    }
    prompt_tokens = rough_token_count_for_messages([prompt_msg], use_tiktoken=False)
    cp_time = time.perf_counter() - cp_start
    print(f"  Compact prompt assembly: {cp_time*1000:.1f}ms, ~{prompt_tokens} tokens")

    # 3. Token counting overhead (simulates auto-compact check)
    print("  Measuring token count overhead...")
    tc_start = time.perf_counter()
    for _ in range(5):
        rough_token_count_for_messages(messages, use_tiktoken=False)
    tc_time = (time.perf_counter() - tc_start) / 5
    print(f"  Token count (avg 5 runs): {tc_time*1000:.1f}ms")

    total_ms = (mc_time + cp_time + tc_time) * 1000
    print(
        f"\n  Summary: snip={mc_time*1000:.1f}ms microcompact={mc_time*1000:.1f}ms "
        f"auto-compact_prompt={cp_time*1000:.1f}ms token_count={tc_time*1000:.1f}ms"
    )
    print(f"  Total compact pipeline: {total_ms:.1f}ms")

    assert token_count > 100_000, f"Token count too low: {token_count:,}"
    print(f"\nPASS: compact_pipeline={total_ms:.0f}ms tokens={token_count:,}")


if __name__ == "__main__":
    main()

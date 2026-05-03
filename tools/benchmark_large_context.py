"""Large context benchmark: measure build, serialize, and token count for 150K+ token messages."""
from __future__ import annotations

import json
import time

from server.services.compact import rough_token_count_for_messages


def build_large_message_list(token_target: int = 150_000) -> list[dict]:
    filler = "Lorem ipsum dolor sit amet, " * 500

    messages = []
    turn = 0
    while True:
        user_msg = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Turn {turn}: Explain the concept of {filler[:100]}.",
                    }
                ],
            },
        }

        assistant_msg = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": filler[:3000]},
                ],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 100, "output_tokens": 100},
            },
        }

        messages.append(user_msg)
        messages.append(assistant_msg)

        current_tokens = rough_token_count_for_messages(messages, use_tiktoken=False)
        if current_tokens >= token_target:
            break
        turn += 1

    return messages


def main():
    target = 150_000
    print("=== Large Context Benchmark ===")

    # Phase 1: Build
    print(f"  Building ~{target:,} token message list...")
    build_start = time.perf_counter()
    messages = build_large_message_list(target)
    build_time = time.perf_counter() - build_start
    print(f"  Built {len(messages)} messages in {build_time:.3f}s")

    # Phase 2: Token count
    print("  Counting tokens...")
    tc_start = time.perf_counter()
    token_count = rough_token_count_for_messages(messages, use_tiktoken=False)
    tc_time = time.perf_counter() - tc_start
    print(f"  Token count: ~{token_count:,} tokens in {tc_time*1000:.1f}ms")

    # Phase 3: Serialization
    print("  Serializing to JSON...")
    ser_start = time.perf_counter()
    payload = json.dumps(messages, ensure_ascii=False)
    ser_time = time.perf_counter() - ser_start
    payload_kb = len(payload) / 1024
    print(f"  Serialized: {payload_kb:.1f} KB in {ser_time*1000:.1f}ms")

    # Phase 4: Deserialization
    print("  Deserializing from JSON...")
    deser_start = time.perf_counter()
    _parsed = json.loads(payload)
    deser_time = time.perf_counter() - deser_start
    print(f"  Deserialized in {deser_time*1000:.1f}ms")

    total_ms = (build_time + tc_time + ser_time + deser_time) * 1000
    print(
        f"\n  Summary: build={build_time*1000:.0f}ms serialize={ser_time*1000:.0f}ms "
        f"deserialize={deser_time*1000:.0f}ms token_count={tc_time*1000:.0f}ms"
    )
    print(
        f"  Total: {total_ms:.0f}ms, Payload: {payload_kb:.0f}KB, "
        f"Estimated tokens: {token_count:,}"
    )

    assert token_count >= 100_000, f"Token count too low: {token_count:,}"
    assert payload_kb > 10, "Payload too small"
    print(
        f"\nPASS: large_context={total_ms:.0f}ms "
        f"tokens={token_count:,} payload={payload_kb:.0f}KB"
    )


if __name__ == "__main__":
    main()

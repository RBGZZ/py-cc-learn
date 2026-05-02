"""E2E verification script using real DeepSeek API."""
from __future__ import annotations

import asyncio
import uuid

from dotenv import load_dotenv

load_dotenv()

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.provider_factory import ProviderFactory


async def test_single_turn():
    provider = ProviderFactory.get_provider()
    if not provider:
        print("SKIP: No API key configured")
        return False

    engine = QueryEngine(QueryEngineConfig(
        provider=provider,
        tools=[],
        system_prompt="You are a helpful assistant.",
        max_turns=1,
    ))

    print("Sending: Hello")
    events = []
    text_parts = []
    async for event in engine.submit_message("Hello"):
        events.append(event)
        if event.get("type") == "text_delta":
            text_parts.append(event.get("text", ""))
        elif event.get("type") == "assistant":
            msg = event.get("data", event)
            content = msg.get("message", msg).get("content", [])
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))

    response = "".join(text_parts)
    print(f"Response: {response[:200]}")
    print(f"Events: {len(events)}")

    result = [e for e in events if e.get("type") == "result"]
    stop_reason = result[0].get("stop_reason") if result else "unknown"
    print(f"Stop reason: {stop_reason}")

    assert len(text_parts) > 0, "No text in response"
    assert stop_reason in ("completed",), f"Unexpected stop reason: {stop_reason}"
    return True


async def main():
    ok = await test_single_turn()
    print(f"\n{'PASS' if ok else 'FAIL'}: E2E single-turn verification")


if __name__ == "__main__":
    asyncio.run(main())

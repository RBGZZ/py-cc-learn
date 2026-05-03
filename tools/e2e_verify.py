"""E2E verification script — supports provider selection via --provider."""
from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.provider import ProviderType
from server.services.provider_factory import ProviderFactory


PROVIDER_MAP = {
    "anthropic": ProviderType.ANTHROPIC,
    "openai": ProviderType.OPENAI,
    "deepseek": ProviderType.DEEPSEEK,
    "google": ProviderType.GOOGLE,
    "qwen": ProviderType.QWEN,
}


async def test_single_turn(provider_type: ProviderType | None = None):
    provider = ProviderFactory.get_provider(provider_type=provider_type)
    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=[], system_prompt="You are a helpful assistant.", max_turns=1,
    ))
    label = provider_type.value if provider_type else "auto"
    print(f"[{label}] Sending: Hello")
    text_parts = []
    async for event in engine.submit_message("Hello"):
        if event.get("type") == "text_delta":
            text_parts.append(event.get("text", ""))
        elif event.get("type") == "assistant":
            msg = event.get("data", event)
            content = msg.get("message", msg).get("content", [])
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
    response = "".join(text_parts)
    print(f"[{label}] Response: {response[:200].encode('ascii', 'replace').decode('ascii')}")
    assert len(text_parts) > 0, "No text in response"
    return True


async def main():
    provider_type = None
    if len(sys.argv) > 1:
        key = sys.argv[1].replace("--provider=", "").replace("--provider", "").lstrip("=").strip().lower()
        provider_type = PROVIDER_MAP.get(key)
        if provider_type is None:
            print(f"Unknown provider: {key}. Options: {list(PROVIDER_MAP)}")
            return
    try:
        ok = await test_single_turn(provider_type)
        print(f"\nPASS: E2E single-turn verification")
    except Exception as exc:
        print(f"\nFAIL: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

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
        await test_compact_with_qwen()
    except Exception as exc:
        print(f"\nFAIL: {exc}")


async def test_compact_with_qwen():
    import os
    key = os.environ.get("QWEN_API_KEY")
    if not key:
        print("SKIP: compact model test (no QWEN_API_KEY)")
        return
    from server.services.qwen_provider import QwenProvider
    from server.services.provider import ProviderConfig
    from server.services.compact import get_compact_prompt

    config = ProviderConfig(model="qwen3.6-flash", api_key=key, max_tokens=200)
    provider = QwenProvider(config)
    prompt = get_compact_prompt()
    msgs = [
        {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "User asked to build a calculator app"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "I created a calculator with add/sub/mul/div"}]}},
        {"type": "user", "message": {"role": "user", "content": prompt}},
    ]
    text_parts = []
    try:
        async for event in provider.stream_chat(msgs, system_prompt="You are a helpful assistant."):
            if event.type == "text_delta":
                text_parts.append(event.data.get("text", ""))
            elif event.type == "assistant":
                content = event.data.get("message", {}).get("content", [])
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
    except Exception as e:
        print(f"Compact model test FAIL: {e}")
        return
    result = "".join(text_parts)
    print(f"  [compact qwen3.6-flash] {result[:150]}")
    assert len(text_parts) > 0, "No compact output"


if __name__ == "__main__":
    asyncio.run(main())

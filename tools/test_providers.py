"""Test all configured providers in sequence."""
from __future__ import annotations

import asyncio
import time

from dotenv import load_dotenv

load_dotenv()

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.provider import ProviderConfig, ProviderType
from server.services.provider_factory import ProviderFactory


PROVIDER_NAMES = [ProviderType.ANTHROPIC, ProviderType.OPENAI, ProviderType.DEEPSEEK, ProviderType.GOOGLE, ProviderType.QWEN]


async def test_provider(provider_type: ProviderType) -> dict:
    from server.utils.settings import get_settings
    settings = get_settings()
    key_attrs: dict[ProviderType, str] = {
        ProviderType.ANTHROPIC: "anthropic_api_key",
        ProviderType.OPENAI: "openai_api_key",
        ProviderType.DEEPSEEK: "deepseek_api_key",
        ProviderType.GOOGLE: "google_api_key",
        ProviderType.QWEN: "qwen_api_key",
    }
    key_val = getattr(settings, key_attrs[provider_type], None)
    if not key_val or key_val in ("your_key_here", "your_token_here", "your_qwen_key_here", ""):
        return {"provider": provider_type.value, "status": "skipped", "reason": "no key"}

    provider = ProviderFactory.get_provider(provider_type=provider_type)
    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=[], system_prompt="Be concise. Answer in one sentence.", max_turns=1,
    ))
    text_parts = []
    start = time.perf_counter()
    async for event in engine.submit_message("Hello, please respond concisely."):
        if event.get("type") == "text_delta":
            text_parts.append(event.get("text", ""))
        elif event.get("type") == "assistant":
            msg = event.get("data", event)
            content = msg.get("message", msg).get("content", [])
            for block in (content if isinstance(content, list) else []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
    elapsed = time.perf_counter() - start
    response = "".join(text_parts)
    return {"provider": provider_type.value, "model": provider.config.model, "status": "passed", "elapsed_s": round(elapsed, 2), "response": response[:120].encode('ascii', 'replace').decode('ascii')}


async def main():
    print("=== Multi-Provider E2E Test ===\n")
    results = []
    for pt in PROVIDER_NAMES:
        label = f"{pt.value:>12}"
        try:
            r = await test_provider(pt)
            if r["status"] == "skipped":
                print(f"  -   {label}: SKIP ({r['reason']})")
            else:
                print(f"  OK  {label} [{r['model']}]: {r['elapsed_s']}s — \"{r['response'][:80]}\"")
        except Exception as exc:
            print(f"  FAIL {label}: FAIL — {exc}")
            results.append({"provider": pt.value, "status": "failed", "error": str(exc)})
            continue
        results.append(r)

    passed = sum(1 for r in results if r["status"] == "passed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\n---\n{passed} passed, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    asyncio.run(main())

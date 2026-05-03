"""Production verify: multi-turn tool call chain with deepseek-v4-flash."""
from __future__ import annotations

import asyncio
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from server.engine.query_engine import QueryEngine, QueryEngineConfig
from server.services.provider import ProviderType
from server.services.provider_factory import ProviderFactory


async def test_chain(name: str, prompt: str, provider, tools: list):
    print(f"\n{'=' * 60}")
    print(f"  Test: {name}")
    print(f"  Prompt: {prompt[:80]}...")
    print(f"{'=' * 60}")

    engine = QueryEngine(QueryEngineConfig(
        provider=provider, tools=tools,
        system_prompt="You are a helpful coding assistant. Be concise.",
        max_turns=3,
    ))

    events = []
    start = time.perf_counter()
    try:
        async for event in engine.submit_message(prompt):
            events.append(event)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False, str(e)
    elapsed = time.perf_counter() - start

    tool_uses = [e for e in events if e.get("type") in ("tool_use",)]
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assistant_events = [e for e in events if e.get("type") == "assistant"]
    texts = []
    for e in events:
        if e.get("type") == "text_delta":
            texts.append(e.get("text", "") or e.get("data", {}).get("text", ""))
        elif e.get("type") == "assistant":
            content = e.get("message", {}) or e.get("data", {}).get("message", {})
            cb = content.get("content", []) if isinstance(content, dict) else e.get("data", {}).get("content", [])
            if isinstance(cb, list):
                for b in cb:
                    if isinstance(b, dict) and b.get("type") == "text":
                        texts.append(b.get("text", ""))
            elif isinstance(cb, str):
                texts.append(cb)

    # Also detect tool use from assistant event content
    if not tool_uses:
        for ae in assistant_events:
            data = ae.get("data", {})
            msg = data.get("message", data)
            content = msg.get("content", []) if isinstance(msg, dict) else []
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_uses.append(b)

    response = "".join(texts)[:200]
    print(f"  Tool calls: {len(tool_uses)}")
    print(f"  Tool results: {len(tool_results)}")
    print(f"  Response: {response}")
    print(f"  Time: {elapsed:.2f}s")

    return True, response


async def main():
    provider_type = ProviderType.DEEPSEEK
    for _i, arg in enumerate(sys.argv):
        if arg.startswith("--provider="):
            key = arg.split("=", 1)[1].strip().lower()
            provider_type = {
                "deepseek": ProviderType.DEEPSEEK,
                "qwen": ProviderType.QWEN,
            }.get(key, ProviderType.DEEPSEEK)

    api_key_env = {
        ProviderType.DEEPSEEK: "DEEPSEEK_API_KEY",
        ProviderType.QWEN: "QWEN_API_KEY",
    }.get(provider_type)
    if api_key_env and not os.environ.get(api_key_env):
        print(f"SKIP: {api_key_env} not set")
        return

    print(f"=== Tool Chain E2E: {provider_type.value} ===\n")

    from server.main import _get_tools
    tools = _get_tools()

    provider = ProviderFactory.get_provider(provider_type=provider_type)
    provider.config.model = "deepseek-v4-flash"
    print(f"Model: {provider.config.model}")

    results = []
    passed = 0

    ok, resp = await test_chain(
        "File Creation",
        "Create a file named /tmp/test_hello.txt with content 'Hello from py-cc-learn!'",
        provider, tools,
    )
    results.append(("File Creation", ok))
    if ok: passed += 1

    ok, resp = await test_chain(
        "Directory Listing",
        "List all files in the /tmp directory",
        provider, tools,
    )
    results.append(("Directory Listing", ok))
    if ok: passed += 1

    ok, resp = await test_chain(
        "File Reading",
        "Read the content of /tmp/test_hello.txt",
        provider, tools,
    )
    results.append(("File Reading", ok))
    if ok: passed += 1

    ok, resp = await test_chain(
        "Code Search",
        'Search for all Python files in the current directory that contain "import"',
        provider, tools,
    )
    results.append(("Code Search", ok))
    if ok: passed += 1

    ok, resp = await test_chain(
        "Full Programming Chain",
        "Create a Python script /tmp/hello.py that prints 'Hello World' and then run it",
        provider, tools,
    )
    results.append(("Full Chain", ok))
    if ok: passed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{len(results)} passed")
    for name, ok in results:
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())

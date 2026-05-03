"""Production verify: prompt caching effect benchmark with deepseek-v4-flash."""
from __future__ import annotations

import asyncio
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()


async def run_caching_test(enabled: bool, rounds: int = 3) -> list[dict]:
    from server.engine.query_engine import QueryEngine, QueryEngineConfig
    from server.services.provider import ProviderType
    from server.services.provider_factory import ProviderFactory

    mode = "ENABLED" if enabled else "DISABLED"
    print(f"\n{'=' * 60}")
    print(f"  Prompt Caching: {mode}")
    print(f"  Model: deepseek-v4-flash, Rounds: {rounds}")
    print(f"{'=' * 60}")

    if enabled:
        os.environ["CLAUDE_CODE_PROMPT_CACHING_ENABLED"] = "1"
    else:
        os.environ.pop("CLAUDE_CODE_PROMPT_CACHING_ENABLED", None)

    provider = ProviderFactory.get_provider(provider_type=ProviderType.DEEPSEEK)
    provider.config.model = "deepseek-v4-flash"

    results = []
    for i in range(rounds):
        engine = QueryEngine(QueryEngineConfig(
            provider=provider, tools=[],
            system_prompt="Be concise.", max_turns=1,
        ))

        start = time.perf_counter()
        ttft = None
        usage = {}
        texts = []

        try:
            async for event in engine.submit_message(
                "Explain what prompt caching is in 2-3 sentences."
            ):
                et = event.get("type", "")
                if et == "text_delta" and ttft is None:
                    ttft = time.perf_counter() - start
                if et == "text_delta":
                    texts.append(event.get("text", ""))
                elif et == "assistant":
                    msg = event.get("message", {})
                    usage = msg.get("usage", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                texts.append(b.get("text", ""))
        except Exception as e:
            print(f"  Round {i + 1} ERROR: {e}")
            continue

        elapsed = time.perf_counter() - start
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        result = {
            "round": i + 1,
            "ttft_ms": round((ttft or 0) * 1000, 1),
            "total_ms": round(elapsed * 1000, 1),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        results.append(result)

        print(
            f"  Round {i + 1}: ttft={result['ttft_ms']}ms "
            f"total={result['total_ms']}ms "
            f"input={result['input_tokens']} output={result['output_tokens']}"
        )

    return results


async def main():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("SKIP: DEEPSEEK_API_KEY not set")
        return

    results_off = await run_caching_test(enabled=False, rounds=3)
    results_on = await run_caching_test(enabled=True, rounds=3)

    if results_off and results_on:
        avg_input_off = sum(r["input_tokens"] for r in results_off) / len(results_off)
        avg_input_on = sum(r["input_tokens"] for r in results_on) / len(results_on)
        avg_ttft_off = sum(r["ttft_ms"] for r in results_off) / len(results_off)
        avg_ttft_on = sum(r["ttft_ms"] for r in results_on) / len(results_on)

        token_saved = avg_input_off - avg_input_on
        ttft_improved = avg_ttft_off - avg_ttft_on

        print(f"\n{'=' * 60}")
        print(f"  Caching Comparison Report")
        print(f"{'=' * 60}")
        print(f"  Avg input tokens (off): {avg_input_off:.0f}")
        print(f"  Avg input tokens (on):  {avg_input_on:.0f}")
        if avg_input_off > 0:
            print(f"  Tokens saved:          {token_saved:.0f} "
                  f"({token_saved / avg_input_off * 100:.1f}%)")
        print(f"  Avg TTFT (off):        {avg_ttft_off:.0f}ms")
        print(f"  Avg TTFT (on):         {avg_ttft_on:.0f}ms")
        if avg_ttft_off > 0:
            print(f"  TTFT improvement:      {ttft_improved:.0f}ms "
                  f"({ttft_improved / avg_ttft_off * 100:.1f}%)")

        report = {
            "model": "deepseek-v4-flash",
            "caching_off": results_off,
            "caching_on": results_on,
            "summary": {
                "avg_input_off": round(avg_input_off),
                "avg_input_on": round(avg_input_on),
                "tokens_saved": round(token_saved),
                "token_save_pct": round(token_saved / avg_input_off * 100, 1) if avg_input_off else 0,
                "avg_ttft_off_ms": round(avg_ttft_off, 1),
                "avg_ttft_on_ms": round(avg_ttft_on, 1),
                "ttft_improvement_ms": round(ttft_improved, 1),
            },
        }
        report_path = os.path.join(
            os.path.dirname(__file__), "..", "audit", "caching-report.json"
        )
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report saved: audit/caching-report.json")


if __name__ == "__main__":
    asyncio.run(main())

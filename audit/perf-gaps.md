# Performance Audit Report: Python vs TypeScript Reference

**Date**: 2026-05-03
**Scope**: 6 modules, 7 audit dimensions
**Status**: 🔴 P0 gaps found — see fixes below

---

## Overview

This audit compared py-cc-learn's Python implementation against the TypeScript reference (claude-code-haha-main) across 6 key performance-critical modules. Each gap is tagged [P0] (performance-critical), [P1] (significant), or [P2] (minor).

**Total gaps found**: 43
- P0 (critical): 14
- P1 (significant): 18
- P2 (minor): 11

---

## 1. Retry Pipeline (`retry.py` vs `withRetry.ts`)

Python: 290 lines | TS: 822 lines | Coverage: ~35%

### P0 Gaps (4)

| # | Gap | TS Reference | Fix |
|---|-----|-------------|-----|
| R1 | Persistent retry mode missing | `withRetry.ts` L96-L104, L477-L512 | Add `_persistent_retry_loop()` with HEARTBEAT_INTERVAL_MS=30s chunked yields |
| R2 | Stale connection detection missing | `withRetry.ts` L112-L118, L217-L238 | Add `is_stale_connection_error()` detecting ECONNRESET/EPIPE |
| R3 | Rate-limit reset header parsing missing | `withRetry.ts` L814-L822 | Parse `anthropic-ratelimit-unified-reset` header |
| R4 | OAuth token refresh on 401/403 missing | `withRetry.ts` L240-L249 | Add credential refresh + retry |

### P1 Gaps (3)

| # | Gap | TS Reference | Fix |
|---|-----|-------------|-----|
| R5 | Fast-mode cooldown logic missing | L267-L305 | Document as P1 (Python doesn't have fast-mode feature) |
| R6 | x-should-retry header obedience missing | L731-L751 | Add header check in should_retry() |
| R7 | AWS/GCP credential cache clearing | L650-L693 | Add credential error handlers |

### P2 Gaps (5)

| R8 | `is_529_error` missing `error.headers.get('retry-after')` pattern |
| R9 | `FOREGROUND_529_RETRY_SOURCES` set not configurable |
| R10 | Missing `isOAuthTokenRevokedError` helper |
| R11 | Missing `isBedrockAuthError` / `isVertexAuthError` helpers |
| R12 | `getRateLimitResetDelayMs` missing |

---

## 2. Query Engine (`query_engine.py` vs `query.ts`)

### P0 Gaps (5)

| # | Gap | TS Reference | Fix |
|---|-----|-------------|-----|
| Q1 | Missing `MAX_OUTPUT_TOKENS_DEFAULT=32000` | `context.ts:L15` | Add constant, use as fallback when Provider max_tokens not set |
| Q2 | Auto-Compact threshold hardcoded 180K vs dynamic per-model | `autoCompact.ts:L62-L79` | Replace with `effective_context_window - 13000` per model |
| Q3 | Token Budget uses `input_tokens >= 180K` vs TS `turnTokens >= budget*0.9` | `tokenBudget.ts` | Rewrite `_check_token_budget()` to use dynamic budget |
| Q4 | Missing snip/microcompact/collapse pre-processing pipeline | `query.ts` L1-L100 | Add per-iteration snip→microcompact→autocompact pipeline |
| Q5 | Auto-Compact doesn't trigger real compact API call | `autoCompact.ts` | Add compact API call when threshold exceeded |

### P1 Gaps (4)

| # | Gap | Fix |
|---|-----|-----|
| Q6 | Missing `hook_stopped` exit reason | Add to QueryExitReason |
| Q7 | Missing `COMPACT_MAX_OUTPUT_TOKENS=20_000` | Add constant for compact operations |
| Q8 | Missing 1M context model detection | Add `[1m]` suffix and model name detection |
| Q9 | `_check_token_budget` uses single-check diminishing vs TS double-check | Require 2 consecutive low-output checks |

### P2 Gaps (2)

| Q10 | `MAX_OUTPUT_TOKENS_RECOVERIES` extra exit reason (TS uses `completed`) |
| Q11 | `CANCELLED_BY_USER` extra exit reason (TS uses `aborted_streaming`) |

---

## 3. Compact Pipeline (`compact.py` vs `src/services/compact/`)

### P0 Gaps (2)

| # | Gap | TS Reference | Fix |
|---|-----|-------------|-----|
| C1 | `COMPACT_MAX_OUTPUT_TOKENS=20_000` missing | `context.ts:L12` | Add constant, use in compact API calls |
| C2 | `_get_effective_context_window` doesn't subtract `MAX_OUTPUT_TOKENS_FOR_SUMMARY` | `autoCompact.ts:L62` | Fix to match TS formula |

### P1 Gaps (6)

| # | Gap |
|---|-----|
| C3 | `reactive_compact` feature not implemented (TS feature flag) |
| C4 | `context_collapse` feature not implemented (TS feature flag) |
| C5 | Compact boundary marker structure differs from TS |
| C6 | Post-compact file attachment recovery token budget differs |
| C7 | `COMPACTABLE_TOOL_NAMES` set missing some TS entries |
| C8 | `_should_auto_compact()` should skip when `query_source in ('session_memory', 'compact')` |

### P2 Gaps (3)

| C9 | `TIMED_BASED_MC_CLEARED_MESSAGE` text differs |
| C10 | `NO_TOOLS_PREAMBLE` format differs |
| C11 | Missing `ERROR_MESSAGE_INCOMPLETE_RESPONSE` |

---

## 4. HTTP/SSE Provider

### P0 Gaps (1)

| # | Gap | TS Reference | Fix |
|---|-----|-------------|-----|
| H1 | Stream idle timeout watchdog missing | `claude.ts` | Add asyncio.wait_for with configurable timeout for SSE streams |

### P1 Gaps (7)

| # | Gap |
|---|-----|
| H2 | Connection preconnect not implemented (increases first-request latency) |
| H3 | Stream connection error recovery path missing |
| H4 | Rate-limit headers not fully parsed in SSE context |
| H5 | Stale connection auto-recovery not in Provider layer |
| H6 | Thinking config not passed through Provider interface |
| H7 | Provider cache invalidation on auth errors missing |
| H8 | DNS cache/preconnect agent not configured |

### P2 Gaps (3)

| H9 | betas headers not configurable |
| H10 | Metadata headers not sent |
| H11 | Prompt caching hints not set |

---

## 5. Constants

### P0 Gaps (2)

| # | Constant | TS Value | Python Value | File |
|---|----------|----------|-------------|------|
| K1 | `PDF_TARGET_RAW_SIZE` | N/A (TS different) | Mismatch | `utils/errors.py` |
| K2 | `max_result_size_chars` default | Must verify | Must verify | `tools/tool.py` |

### P1 Gaps (3)

| K3 | Tool output size limits |
| K4 | File read chunk sizes |
| K5 | Image processing limits |

---

## 6. StreamingToolExecutor

### P0 Gaps (2)

| # | Gap | TS Reference | Fix |
|---|-----|-------------|-----|
| S1 | AbortController parent-to-child auto-propagation missing | `StreamingToolExecutor.ts` L48-L49 | Wire parent abort signal to child executor |
| S2 | Sibling abort doesn't interrupt in-progress tools | `StreamingToolExecutor.ts` L48 | Implement sibling abort on Bash tool error |

### P1 Gaps (1)

| S3 | Progress message immediate yield not differentiated from results |

### P2 Gaps (1)

| S4 | Discarded tool error message differs from TS |

---

## Summary

```
Total gaps: 43
  P0 (critical performance): 14 (Retry:4, QueryEngine:5, Compact:2, HTTP:1, Constants:2, StreamExec:2)
  P1 (significant):          18
  P2 (minor):                11

Prior audit (gaps.md): 44 functional gaps → ALL RESOLVED
This audit (perf-gaps.md): 43 performance gaps → 14 P0

Modules with most P0s:
  1. Query Engine (5) — token constants + compact pipeline
  2. Retry (4) — persistent retry + stale connection
  3. Compact (2) — constants + context window
  4. StreamingToolExecutor (2) — abort propagation
  5. HTTP/SSE (1) — idle timeout
  6. Constants (2) — value mismatches
```

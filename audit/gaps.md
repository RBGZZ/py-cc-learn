# Audit Report: Python Rewrite vs TypeScript Reference

**Date**: 2026-05-02
**Scope**: Full module-by-module comparison of `server/` vs `src/`, plus `frontend/` vs `src/components/`

---

## P0 - Blocking Gaps (17 engine + 3 frontend = 20)

### Engine Layer

| # | Gap | Severity | Python Location | TS Reference |
|---|-----|----------|----------------|-------------|
| U1 | `_make_interruption_message` returns stream_event not user message, no toolUse flag | P0 | [query_engine.py:L801-L809](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L801-L809) | [messages.ts:L545-L560](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/utils/messages.ts#L545-L560) |
| U2 | streaming_fallback recovery path missing | P0 | [query_engine.py:L318-L363](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L318-L363) | [query.ts:L678-L741](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query.ts#L678-L741) |
| U3 | prompt_too_long withhold+recover missing | P0 | none | [query.ts:L1085-L1183](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query.ts#L1085-L1183) |
| U4 | collapse_drain_retry enum exists, no implementation | P0 | [query_engine.py:L41](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L41) | [query.ts:L1089-L1117](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query.ts#L1089-L1117) |
| U5 | reactive_compact_retry enum exists, no implementation | P0 | [query_engine.py:L42](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L42) | [query.ts:L1119-L1166](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query.ts#L1119-L1166) |
| U6 | stop_hook_blocking not triggered (stop hooks return ignored) | P0 | [query_engine.py:L684-L687](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L684-L687) | [query.ts:L1282-L1306](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query.ts#L1282-L1306) |
| U7 | Stop hooks infra: no TeammateIdle/TaskCompleted, no progress yield | P0 | [query_engine.py:L684-L687](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L684-L687) | [stopHooks.ts:L65-L473](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query/stopHooks.ts#L65-L473) |
| U8 | Token budget: return value ignored on L418, no BudgetTracker | P0 | [query_engine.py:L731-L749](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L731-L749) | [tokenBudget.ts:L45-L93](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query/tokenBudget.ts#L45-L93) |
| U9 | Compact boundary index never updated, no microcompact/snip/collapse | P0 | [query_engine.py:L102](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L102) | [query.ts:L412-L543](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query.ts#L412-L543) |
| U10 | yieldMissingToolResultBlocks doesn't yield to caller | P0 | [query_engine.py:L656-L677](file:///d:/agent_learn/py-cc/py-cc-learn/server/engine/query_engine.py#L656-L677) | [query.ts:L123-L149](file:///d:/agent_learn/py-cc/claude-code-haha-main/src/query.ts#L123-L149) |

### Tool System

| # | Gap | Severity | Description |
|---|-----|----------|-------------|
| T1 | AgentTool ~88% missing | P0 | TS 1398 lines, Python 170 lines: missing subagent lifecycle, sandbox, skill discovery, agent spawn/teardown |
| T2 | Tool base class field count | P0 | TS `Tool.ts`: name(required), inputSchema(Zod), call, description, prompt, userFacingName, toAutoClassifierInput, mapToolResultToToolResultBlockParam, renderToolUseMessage, maxResultSizeChars, isMCP, isLSP, shouldDefer, alwaysLoad, strict + 27 optional properties. Python missing some optional fields. |
| T3 | StreamingToolExecutor: missing `withMemoryCorrectionHint`, `runToolUse` import pattern differs | P0 | Python `set_run_tool_use_fn` pattern different from TS direct import |

### Frontend Layer

| # | Gap | Description |
|---|-----|-------------|
| F1 | Permission dialog system | 15+ TS components, 0 in Python |
| F2 | Message preprocessing pipeline | normalize/group/collapse/reorder missing |
| F3 | Message grouping | GroupedToolUse + CollapsedReadSearch missing |

---

## P1 - Experience Gaps (14 engine + 10 frontend = 24)

### Engine Layer

| # | Gap | Severity | Description |
|---|-----|----------|-------------|
| U11 | buildQueryConfig missing | P1 | No runtime feature gates (sessionId, gates map) |
| U12 | max_output_tokens_escalate incomplete | P1 | Missing capEnabled gate + CAPPED_DEFAULT_MAX_TOKENS (8000) |
| U13 | Post-sampling hooks context insufficient | P1 | Only passes assistant_msgs, missing systemPrompt/userContext |
| U14 | Streaming executor: no discard+rebuild on fallback | P1 | Missing TS L730-L740 flow on streamingFallbackOccured |
| U15 | Streaming executor: getCompletedResults called less frequently | P1 | Only on assistant/text_delta, TS checks after all events |

### Tool System

| # | Gap | Description |
|---|-----|-------------|
| T4-T10 | Missing tools | TS has 45+ tools, Python has 20. See tool audit for full list |

### Frontend Layer

| # | Gap | Description |
|---|-----|-------------|
| F4-F10 | Input/Display gaps | Command system, history nav, virtual scroll, input viewport, message queue, meta filter, Bash output expand missing |

---

## P2 - Documentation Gaps

| # | Gap |
|---|-----|
| P2-1 | Language-idiom differences (Python async vs TS async generators) documented |
| P2-2 | Provider abstraction layer differences (multi-vendor vs Anthropic-only) accepted |
| P2-3 | Vue 3 component model vs React/Ink terminal UI - design rationale documented |

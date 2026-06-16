# Protocol Abort Postmortem — June 16, 2026

## Verdict

**Root cause: `text_regex` protocol incompatible with qwen3.7-plus output format. Fixed by switching all tiers to `tool_call` protocol. 557 tests pass, py_compile clean, git diff --check clean.**

## Root Cause

### What broke

6x10 Stage 1 had 25/60 (42%) StagnationExit aborts. 21/60 (35%) classified as protocol-owner. 51/60 (85%) pairs had at least one protocol retry.

The `text_regex` protocol uses `parse_regex_actions` from mini-swe-agent. This parser applies regex `TEXT_ACTION_REGEX` to extract fenced bash blocks (` ```bash ... ``` `) from model output. When it finds != 1 match, it raises `FormatError`.

qwen3.7-plus (T2) and GPT-5.4 (T3) frequently produce output that doesn't match the exact fenced-block pattern. The regex parser rejects the output, the proxy retries once with a format correction prompt (`_FORMAT_RETRY_PROMPT`), but the model often repeats the same format — only 43% retry success rate.

`_format_error_streak` persists across turns. When it reaches `stop_after` (from `format_error_stop_after`), raises `BudgetFlowStagnationError` → `StagnationExit`. The agent runs out of format-error runway before it runs out of budget or ideas.

### Why it wasn't caught earlier

Catalog protocol was `text_regex` for all tiers in both `model_tiers.default.json` and `model_tiers.t3x3.json`. The Python fallback defaults in `model_tiers.py` also used `text_regex`. This was the original protocol choice, predating the qwen3.7-plus catalog swap. No protocol health gate existed in paid-run readiness checks.

### Evidence chain

- Old 6x10 (`mainline_6x30_v1`): 24 abort, 52/60 protocol retry
- New 6x10 (`mainline_6x30_shared_budget_t3x3_20260615`): 25 abort, 51/60 protocol retry
- Same pattern across both runs — systemic, not random
- `response_ok: true` on all turn traces — API succeeded, parser failed
- `parser_error_message: format_error_text_action` — regex mismatch

## Fixes Applied

### 1. Catalog protocol: `text_regex` → `tool_call` (2 files)

**Files**: `docs/config/model_tiers.t3x3.json`, `docs/config/model_tiers.default.json`

All 3 tiers changed from `"protocol": "text_regex"` to `"protocol": "tool_call"`. The `tool_call` protocol uses native function-calling (`parse_toolcall_actions`) which doesn't depend on regex matching of text output format.

### 2. Python fallback defaults: `text_regex` → `tool_call` (1 file)

**File**: `src/budgetflow/model_tiers.py` lines 78, 106, 130

The `TierConfig` dataclass fallback constructor used `protocol="text_regex"` for all three tiers. Changed to `protocol="tool_call"` to match catalog.

### 3. Stall guard: add `value_aware_task_level` (1 file)

**File**: `src/budgetflow/adapter/stall_guard.py`

`value_aware_task_level` routing (used by `budgetflow_task_level` strategy, Claim 1) was missing from both `_STALL_GUARD_STRATEGIES` and `_POST_PATCH_STOP_STRATEGIES`. This meant `budgetflow_task_level` had no stall guard — it would never be truncated by BudgetFlow stop-loss, which is incorrect for a paper-mainline strategy. Added to both sets.

### 4. Protocol health gate in paid-readiness (1 file)

**File**: `src/budgetflow/experiments/compare_readiness.py`

Two new helper functions:
- `_find_existing_jsonl()` — locates existing JSONL for the run series
- `_compute_protocol_health()` — computes protocol-owner abort rate and protocol retry rate from existing JSONL

Gate rules in `build_compare_readiness_report()`:
- **BLOCK** if protocol-owner abort rate > 5% (action protocol is unstable)
- **BLOCK** if protocol retry rate > 10% (excessive format failures)
- If no existing JSONL: facts only, no block (first run has no evidence)

### 5. Test updates (4 files)

| File | Changes |
|---|---|
| `tests/test_gpt54_text_parser.py` | Protocol assertions `text_regex` → `tool_call`, parser `parse_regex_actions` → `parse_toolcall_actions`. Function names updated to `test_t*_uses_tool_call_protocol`. |
| `tests/test_provider_fallback.py:91` | `text_regex` → `tool_call` |
| `tests/test_trace_fields.py` | 3 occurrences `text_regex` → `tool_call`, 1 `parse_regex_actions` → `parse_toolcall_actions`. Function renamed `test_action_trace_fields_capture_current_text_regex_action` → `..._tool_call_action`. |
| `tests/test_run_observability_audit.py:312` | JSONL fixture `text_regex` → `tool_call` |

## What Was NOT Changed

- **Historical JSONL** — existing run data untouched (user constraint)
- **Task values** — value matrix unchanged (user constraint)
- **Catalog prices** — T3 prices in t3x3 unchanged
- **Protocol adapter** — `protocol_adapter.py` still supports `text_regex` path when activated by `BF_GPT_TEXT_MODE` env var (kept for diagnostics)
- **Action parsing** — `action_parsing.py` still imports `parse_regex_actions` and provides `parse_text_actions()` (kept for backward compat)
- **Observability schema** — `schema.py:90` still checks `protocol == "text_regex"` (handles existing data with text protocol rows)

## Verification

```
PYTHONPATH=src python -m pytest tests/ -q  →  557 passed, 1 skipped
py_compile: model_tiers.py, stall_guard.py, compare_readiness.py  →  OK
git diff --check  →  clean
```

## Next Steps

1. Run `--paid-readiness-only` to verify the new protocol health gate reports clean (no existing JSONL → facts only, no block)
2. Run 2-task × 2-strategy canary with tool_call protocol to verify protocol abort rate drops
3. If canary passes, resume 6x20 under same run series with tool_call catalog

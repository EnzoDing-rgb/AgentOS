# 012 — Trace Pipeline Audit: turn_traces End-to-End Verification

Date: 2026-06-03

## Summary

Verified the `--trace-turns` (now default True) pipeline end-to-end. No bugs found. Traces will appear in JSONL output on the next experiment run.

## Pipeline Diagram

```
argparse
  │  parser.set_defaults(trace_turns=True)          # line 1127
  │  → args.trace_turns
  ▼
_run_one_batch()                                     # line 574
  │  enable_turn_trace = args.trace_turns            # line 1542
  │  passes to _run_one()                            # line 689
  ▼
_run_one()                                           # line 226
  │  enable_turn_trace=enable_turn_trace             # line 252
  │  passes to run_mini_swe_task()
  ▼
run_mini_swe_task()                                  # line 114 (runner.py)
  │  passes to BudgetFlowLitellmModel(               # line 155
  │      enable_turn_trace=enable_turn_trace)
  ▼
BudgetFlowLitellmModel.__init__()                    # lines 373-374 (mini_swe_proxy.py)
  │  self._enable_turn_trace = enable_turn_trace
  │  self.turn_traces = []
  ▼
Per-turn call sites (3 total):                       # lines 542, 616, 664
  │  if self._enable_turn_trace:
  │      self.turn_traces.append(_build_turn_trace(...))
  │  Each call site corresponds to a different outcome:
  │    (a) provider error (line 542)  → error_type set, response_ok=False
  │    (b) parser error (line 616)    → error_type set, response_ok=True
  │    (c) success (line 664)         → error_type=None, response_ok=True
  ▼
After task completes:
  │  runner.py lines 284-285:
  │    turn_trace_count = len(model.turn_traces)
  │    turn_traces = list(model.turn_traces) if model.turn_traces else None
  ▼
_run_one() record construction:                      # lines 295-297
  │  "turn_trace_count": result.turn_trace_count,
  │  "turn_traces": _truncate_turn_traces(...)
  │      if enable_turn_trace and result.turn_traces else None,
  ▼
JSONL output file                                    # line 1552
```

## _build_turn_trace() Data Shape

Produces a dict with ~44 keys. Major groups:

| Group | Keys | Notes |
|-------|------|-------|
| Identity | step, agent_phase, stage | turn number, locate/repair, LOC/REP |
| Cost | input_tokens, prompt_tokens, completion_tokens, actual_cost, billable_cost, expected_costs | per-turn billing |
| Backend | backend_chosen, escalated_backend, final_backend, backend_tier | routing decision |
| Pressure | base_pressure, effective_pressure | governor state |
| Progress | has_progress, progress_reason, no_progress_streak, no_progress_on_tier, turns_on_tier | stagnation tracking |
| Error | response_ok, error_type | failure mode |
| P0: Provider | provider, model, provider_status_code, provider_error_body, provider_request_id | provider identity + errors |
| P0: Protocol | text_mode, protocol, parser, parser_input_snippet, parser_error_type, parser_error_message | parsing evidence |
| P0: Router | router_reason, router_scores, router_pressure, router_branch | routing introspection |
| P0: Reservation | reservation_id, reserved_cost, reservation_released, reservation_settled | governor reservation lifecycle |
| Adaptive | adaptive_ttl, adaptive_floor, adaptive_boost, rescue_evidence_turns | when adaptive routing is active |
| Digest | bash_digest (truncated to 120 chars) | what the agent ran |

## Truncation

`_truncate_turn_traces()` (line 198) applies two limits:
- **max_turns** (default 200): keeps only the last N traces per task if trace count exceeds N.
- **truncate_chars** (default 120): trims `bash_digest` to N characters.

These are safety measures against oversized JSONL lines. They do not drop traces entirely unless count > 200 (unlikely: most tasks finish in <100 turns).

## Filtering That Could Drop Traces

| Condition | Effect | Risk |
|-----------|--------|------|
| `enable_turn_trace=False` | traces never collected; `turn_traces=null` | **Fixed**: default is now True. Only drops if user passes `--no-trace-turns`. |
| `result.turn_traces is None` | guard at line 297: `if enable_turn_trace and result.turn_traces else None` | **Correct**: None only when no turns executed (agent crashed before any LLM call). trace_count=0 still written. |
| Zero-turn runs | `model.turn_traces` is `[]` → `result.turn_traces = None` → JSONL field is `null` | **Expected**: no LLM calls, nothing to trace. |

No bugs found. No unintended trace drops.

## Verification

### Smoke test (passed)

```python
from budgetflow.adapter.mini_swe_proxy import _build_turn_trace
trace = _build_turn_trace(step_index=1, ...)
# Produces 44 keys including all P0 fields
# step=1, stage=LOC, bash_digest="ls", provider="deepseek", reservation_id="res-123"
```

### Argparse default verification (passed)

```
Default --trace-turns: True     # no flags → traces enabled
--no-trace-turns: False          # explicit disable works
--trace-turns: True              # explicit enable works
```

### Dataclass field check (passed)

`MiniSweRunResult` has both `turn_trace_count: int = 0` and `turn_traces: list[dict] | None = None` fields.

### Downstream consumers

- `check_consistency.py` line 114: checks `turn_trace_count` for zero across all rows (warns if all-zero).
- `failure_classification.py` lines 84-95: reads `turn_traces` to extract per-turn `error_type` for forensic diagnosis.
- `failure_classification.py` line 176: flags `turn_traces` as missing evidence if absent.

All downstream code already handles the `turn_traces` field correctly.

## Conclusion

- **Pipeline is intact.** `_build_turn_trace()` is called during agent execution at 3 call sites (provider error, parser error, success). Data propagates through `MiniSweRunResult` → `_run_one` → JSONL.
- **Default is True.** Next experiment will produce non-zero `turn_trace_count` for every task that has at least 1 LLM turn.
- **No fixes needed.** Zero bugs found.

## Next Experiment

Run with `--trace-turns` (default) and verify:
1. `turn_trace_count > 0` for all rows
2. BudgetFlow selector decisions visible in `router_reason`, `backend_chosen`, `backend_tier`
3. Per-turn cost attribution via `actual_cost`, `provider`, `model`

Run `check_consistency.py` afterward to confirm no zero-trace rows.

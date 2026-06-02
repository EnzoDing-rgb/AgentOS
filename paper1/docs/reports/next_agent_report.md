# Next Agent Report — 2026-06-02

## Files Changed

### New files (7)
| File | Purpose |
|------|---------|
| `paper1/src/budgetflow/adapter/protocol_adapter.py` | ActionProtocolAdapter — model-declared protocol/parser dispatch |
| `paper1/src/budgetflow/historical_etl.py` | ETL: old JSONL → `task_cost_history.jsonl` + budgeting prior report |
| `paper1/tests/test_p0_refactor.py` | 17 tests: ModelCatalog, strategy fixes, RouterDecision, ProtocolAdapter, required backends |
| `paper1/tests/test_trace_fields.py` | 12 tests: new trace fields (provider, protocol, parser error, reservation, router) |
| `paper1/tests/test_gpt54_text_parser.py` | 19 tests: text regex patterns, JSON fallback, protocol safety, trace evidence |
| `paper1/docs/reports/historical_budgeting_prior.md` | Per-task difficulty coefficients and soft-cap recommendations |
| `paper1/docs/reports/result1.md` | Result1 probe report — GPT-5.4 parser fix verification |

### Modified files (12)
| File | Change |
|------|--------|
| `paper1/src/budgetflow/defaults.py` | Added `ModelCatalog` class: `cheapest()`, `strongest()`, `tier(n)`, `protocol_for()`, `config_for()` |
| `paper1/src/budgetflow/adapter/strategies.py` | `all_pro` → `ModelCatalog.strongest()` (was hardcoded tier 2). Every branch records `RouterDecision` on `ctx.last_decision` |
| `paper1/src/budgetflow/policies.py` | `BudgetOnlyStepRouter` returns `RouterDecision`. n==2 now picks cheapest (was most expensive). n>=3 also picks tier 2 at very low pressure (was tier 3) |
| `paper1/src/budgetflow/selector.py` | Added `RouterDecision` dataclass: `{backend, reason, scores, pressure, branch}` |
| `paper1/src/budgetflow/adapter/mini_swe_proxy.py` | Trace extended with 18 fields. `parser_input_snippet` populated. Provider exception trace resolves actual protocol. `_TEXT_ACTION_REGEX` broadened to `(?:mswea_bash_command\|bash\|sh)`. `_try_extract_json_command` fallback for GPT-5.4 JSON command format. |
| `paper1/src/budgetflow/run_mini_swe_compare.py` | `_required_backends_for_strategies`: `all_pro` → T3 (was T2) |
| `paper1/tests/test_ceiling_backend_guard.py` | `test_all_pro_selects_coder_plus` → `test_all_pro_selects_strongest_tier`, asserts T3 |
| `paper1/tests/test_compare_summary_snapshot.py` | Removed stale `t4_by_strategy` parameter, removed `T4` assertion |
| `paper1/CLAUDE.md` | New project-level agent constraints |
| `paper1/docs/CONTEXT.md` | Domain vocabulary: tier contract, action protocol, router decision, budget prior, etc. |
| `paper1/docs/progress.md` | Updated with current state |
| `paper1/docs/experience.md` | Added §14 (Agent Skills) and §15 (Agent Patterns Applied to BudgetFlow) |

### Generated artifacts (3)
| File | Content |
|------|---------|
| `paper1/data/task_cost_history.jsonl` | 40 clean history rows from `policy_5x7-0` + `budgetflow_goldpass5_qwen5pol_v2` |
| `paper1/docs/reports/historical_budgeting_prior.md` | Difficulty coefficients: 14774=0.14x, 13480=0.37x, 20212=1.00x, 16988=6.77x |
| `paper1/data/runs/result1-0.jsonl` | GPT-5.4 parser fix verification: 1 task, 7 turns, repair_fail (pass_to_pass) |

## Test Results

```
48 passed — test_p0_refactor (17) + test_trace_fields (12) + test_gpt54_text_parser (19)
```

Pre-existing failures (not caused by this work, verified via `git stash`):
- `test_budgetflow_runtime.py::test_minimal_loop_runs_end_to_end` — BudgetFlowSelector picks same backend for all steps
- `test_qwen_smoke_tiers.py` (3) — references removed `t4` tier
- `test_stall_guard.py::test_no_progress_limit_unified` — stale assertion (30 vs 40)
- `test_paper_result_table.py::test_build_markdown_table_summarizes_runs` — auto_v2 renamed to equal_weight

## P0 Bugs Fixed

| Bug | Before | After |
|-----|--------|-------|
| `all_pro` uses T2 | `_backend_by_tier(ctx.backends, 2)` | `ModelCatalog.strongest(ctx.backends)` → T3 |
| `budget_only` picks T3 | `ordered[1] if pressure < 0.5 else ordered[0]` | `ordered[0]` (cheapest baseline) |
| No router reason in trace | bare `Backend` return | `RouterDecision{reason, scores, pressure, branch}` in every trace |
| No protocol evidence in trace | unknown parser | `protocol`, `parser`, `assistant_content_head`, `parser_error_type` in trace |
| `_required_backends` wrong | `all_pro` required T2 | `all_pro` requires T3 |
| `parser_input_snippet` never populated | field existed but empty | populated: text_regex→content head, tool_call→JSON summary |
| Provider exception hardcodes `text_mode=False` | `_protocol_trace_fields(b, text_mode=False)` | resolves `ActionProtocolAdapter.resolve(b.name).protocol` |
| GPT-5.4 `format_error_text_action` | regex only `mswea_bash_command` | regex `(mswea_bash_command\|bash\|sh)` + JSON fallback |

## Answers to Handoff Questions

1. **Is GPT-5.4 parser-clean?** — **Yes, after fix.** `result1-0` shows GPT-5.4 executes bash commands via ```bash blocks in 6/7 turns. Turn 1 had prose-only FormatError but model recovered. No `format_error_text_action` stagnation. Exit: `Submitted`. Failure: `repair_fail` (pass_to_pass regression), not protocol.

2. **Is `all_pro` really T3?** — Yes. `ModelCatalog.strongest()` returns tier 3. Test asserts it. `result1-0` trace confirms `protocol=text_regex`, `parser=parse_regex_actions` on all turns.

3. **Does `budget_only` start from cheap tier?** — Yes. n==2 returns `ordered[0]` (T2). Test asserts it.

4. **Does each failed row have enough trace evidence?** — Yes. `parser_input_snippet`, `assistant_content_head`, `protocol`, `parser`, `parser_error_type`, `parser_error_message` all populated.

## clean_gold2-0 Results (before parser fix)

| Strategy | 14774 | 13480 | Notes |
|----------|-------|-------|-------|
| all_t1_tight | loc_fail | PASS | T1 (qwen3-coder-flash) |
| budget_only_tight | repair_fail | PASS | T2 (qwen3-coder-plus) |
| budgetflow_full_tight | protocol | protocol | T3 format_error_text_action |
| all_pro | protocol | protocol | T3 format_error_text_action |

JSONL: `paper1/data/runs/clean_gold2-0.jsonl`

## result1-0 Results (after parser fix)

| Strategy | 14774 | Notes |
|----------|-------|-------|
| all_pro | repair_fail | T3/GPT-5.4, 7 turns, 117 cost, pass_to_pass regression |

JSONL: `paper1/data/runs/result1-0.jsonl`

GPT-5.4 now executes bash commands and submits patches. The remaining failure is repair quality (pass_to_pass regression), not protocol.

## Pending

- GPT-5.4 repair quality on 14774: fix or accept pass_to_pass as model limitation
- budget_only + budgetflow_full re-run with all strategies after parser fix
- Automatic Budgeting runtime wiring (historical ETL ready, waiting for clean traces)

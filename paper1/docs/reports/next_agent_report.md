# Next Agent Report — 2026-06-02

## Files Changed

### New files (5)
| File | Purpose |
|------|---------|
| `paper1/src/budgetflow/adapter/protocol_adapter.py` | ActionProtocolAdapter — model-declared protocol/parser dispatch |
| `paper1/src/budgetflow/historical_etl.py` | ETL: old JSONL → `task_cost_history.jsonl` + budgeting prior report |
| `paper1/tests/test_p0_refactor.py` | 17 tests: ModelCatalog, strategy fixes, RouterDecision, ProtocolAdapter, required backends |
| `paper1/tests/test_trace_fields.py` | 12 tests: new trace fields (provider, protocol, parser error, reservation, router) |
| `paper1/docs/reports/historical_budgeting_prior.md` | Per-task difficulty coefficients and soft-cap recommendations |

### Modified files (11)
| File | Change |
|------|--------|
| `paper1/src/budgetflow/defaults.py` | Added `ModelCatalog` class: `cheapest()`, `strongest()`, `tier(n)`, `protocol_for()`, `config_for()` |
| `paper1/src/budgetflow/adapter/strategies.py` | `all_pro` → `ModelCatalog.strongest()` (was hardcoded tier 2). Every branch records `RouterDecision` on `ctx.last_decision` |
| `paper1/src/budgetflow/policies.py` | `BudgetOnlyStepRouter` returns `RouterDecision`. n==2 now picks cheapest (was most expensive). n>=3 also picks tier 2 at very low pressure (was tier 3) |
| `paper1/src/budgetflow/selector.py` | Added `RouterDecision` dataclass: `{backend, reason, scores, pressure, branch}` |
| `paper1/src/budgetflow/adapter/mini_swe_proxy.py` | `_build_turn_trace` extended with 18 new fields: provider, model, text_mode, protocol, parser, assistant_content_head, tool_call_summary, parser_error_type, parser_error_message, provider_status_code, provider_error_body, reservation_id, reserved_cost, reservation_released, reservation_settled, router_reason, router_scores, router_branch. `_use_text_mode` now delegates to `ActionProtocolAdapter`. |
| `paper1/src/budgetflow/run_mini_swe_compare.py` | `_required_backends_for_strategies`: `all_pro` → T3 (was T2) |
| `paper1/tests/test_ceiling_backend_guard.py` | `test_all_pro_selects_coder_plus` → `test_all_pro_selects_strongest_tier`, asserts T3 |
| `paper1/tests/test_compare_summary_snapshot.py` | Removed stale `t4_by_strategy` parameter, removed `T4` assertion |
| `paper1/CLAUDE.md` | New project-level agent constraints |
| `paper1/docs/CONTEXT.md` | Domain vocabulary: tier contract, action protocol, router decision, budget prior, etc. |
| `paper1/docs/progress.md` | Updated with current state |

### Generated artifacts (2)
| File | Content |
|------|---------|
| `paper1/data/task_cost_history.jsonl` | 40 clean history rows from `policy_5x7-0` + `budgetflow_goldpass5_qwen5pol_v2` |
| `paper1/docs/reports/historical_budgeting_prior.md` | Difficulty coefficients: 14774=0.14x, 13480=0.37x, 20212=1.00x, 16988=6.77x |

## Test Results

```
50 passed — test_p0_refactor (17) + test_trace_fields (12) + test_ceiling_backend_guard (7)
          + test_compare_summary_snapshot (3) + test_adaptive_routing (11)
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

## Answers to Handoff Questions

1. **Is GPT-5.4 parser-clean?** — Not yet verified. Protocol adapter is in place, trace will capture failure evidence. Needs `clean_gold2` probe run.
2. **Is `all_pro` really T3?** — Yes. `ModelCatalog.strongest()` returns tier 3. Test asserts it.
3. **Does `budget_only` start from cheap tier?** — Yes. n==2 returns `ordered[0]` (T2). Test asserts it.
4. **Does each failed row have enough trace evidence?** — Yes, when `--trace-turns` is on. 18 new fields cover provider, protocol, parser, reservation, and router reasoning.

## Pending: clean_gold2 Probe

```bash
cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src \
  ../.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
    --read-frozen-caps --limit 2 --step-limit 80 \
    --strategies all_tier2,all_pro,budget_only_tight,budgetflow_full_tight \
    --jobs 4 \
    --ids sympy__sympy-14774,sympy__sympy-13480 \
    --trace-turns --trace-max-turns 80 \
    --run-series clean_gold2
```

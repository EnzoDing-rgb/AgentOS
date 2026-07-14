# Protocol, Budget, and Observability Slice - 2026-06-16

## Objective

Prepare the next paid 6x5 diagnostic by removing stale action-protocol paths,
binding model-tier catalog changes to budget artifacts, and making cost,
usage, provider, parser, and budget-plan evidence visible in current JSONL
records.

## Files Changed

- `docs/config/model_tiers.default.json`, `model_tiers.t3x2.json`, `model_tiers.t3x3.json`
- `src/budgetflow/model_tiers.py`, `recost.py`
- `src/budgetflow/adapter/action_parsing.py`, `mini_swe_proxy.py`, `runner.py`, `turn_trace.py`
- `src/budgetflow/experiments/compare_execution.py`, `compare_readiness.py`
- `src/budgetflow/run_observability/audit.py`, `report.py`, `schema.py`
- `docs/reports/mainline_6x5_budget_plan.json`, `mainline_6x30_budget_plan.json`
- focused tests for readiness, protocol retry, trace fields, tier frontier, and compare record schema

## Interface Decisions

- Active action protocol is native `tool_call` only.
- T2 mainline is `qwen3.7-plus`; T3 remains `gpt-5.4`.
- Catalog costs are normalized experimental units. Real provider invoices are
  spend-accounting context, not the routing unit.
- Rows and turn traces now expose provider usage versus estimated usage through
  `usage_source`, `cost_mode`, token source fields, protocol/parser fields, and
  provider error classification.
- Budget plans must exactly match the selected task list and order, strategy
  order, catalog revision/path/hash, and value source at readiness time. A 6x5
  run cannot use the 6x30 budget plan.

## Deleted Or Retired Paths

- Removed active text-regex/text-mode action parsing from current runtime and
  catalog configuration.
- Kept historical audit counters that read old JSONL only; they are not active
  runtime compatibility paths.

## Verification

- 6x5 paid readiness with `mainline_6x5_budget_plan.json`: PASS.
- Negative readiness check using the 6x30 budget plan for the same 6x5 task
  list: BLOCK as expected.
- `PYTHONPATH=paper1/src python -m pytest paper1/tests/test_compare_readiness.py paper1/tests/test_trace_fields.py paper1/tests/test_protocol_retry.py paper1/tests/test_compare_record_schema.py paper1/tests/test_tier_frontier.py paper1/tests/test_budget_binding.py -q`
  - `108 passed, 13 skipped`
- `python -m py_compile` on touched runtime, readiness, observability, catalog,
  and cost modules: PASS.
- `git diff --check`: PASS.

## Residual Risks

- Projected 90 percent budget pressure is a pre-run contract, not a guarantee
  that actual utilization will land near 90 percent. The next 6x5 paid
  diagnostic must audit actual utilization before any 6x10 or 6x30 run.
- The cleaner long-term architecture is a single pre-registered run manifest
  that owns task IDs, strategies, catalog, value matrix, frozen plan, and budget
  plan. Current readiness gates block known mismatches, but the CLI still
  accepts multiple artifact paths.

## Next Slice

Run the paid 6x5 diagnostic. Stop on provider/model access failure, broad
protocol/provider/harness infra failure, or actual budget utilization that is
too loose to support a scarcity claim.

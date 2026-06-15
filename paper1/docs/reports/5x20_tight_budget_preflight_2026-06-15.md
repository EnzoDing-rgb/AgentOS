# 5x20 Tight Budget Preflight Gate Report — 2026-06-15

## Summary

20 tasks × 5 strategies, target_utilization=0.80 budget mode. All gates pass. GO.

## Artifacts generated

| Artifact | Path | Status |
|---|---|---|
| Bootstrap value matrix | docs/reports/mainline_5x20_value_matrix.json | 20/20 tasks, 4 repos |
| Manual value matrix | docs/reports/mainline_5x20_manual_value_matrix.json | extended from 5x16, 4 new tasks |
| Frozen router plan | docs/reports/mainline_5x20_frozen_router_plan.json | cap sum $4.50, all new tasks tier2 |
| Budget binding plan | docs/reports/mainline_5x20_budget_plan.json | target_utilization=0.80, hard_cap=$1.2262, PASS |
| Preflight | docs/reports/mainline_5x20_preflight.md | full experiment documentation |

## Budget binding

| Key | Value |
|---|---|
| budget_mode | target_utilization |
| reference_rule | strategy_set_p75_projected_spend = $0.9809 |
| hard_cap | $1.2262 (= $0.9809 / 0.80) |
| utilization | T2=61.5%, T3=100%, enterprise=61.5%, bf_same=61.5%, bf_full=80% |
| decision | PASS |
| catalog | model_tiers.t3x2.json (2026-06-10-t3x2) |

Pressure gradient is defensible: cheapest strategies loose, bf_full at target (80%),
bare_t3 tight (100%). Budget is binding enough to differentiate routing-level effects
from raw model capability.

## Gates

| Gate | Result |
|---|---|
| Test suite | PASS (488 passed, 2 skipped, 0 failed) |
| budget_binding tests (19) | PASS |
| compare_readiness tests (18) | PASS |
| compare_setup tests (13) | PASS (3 new budget wiring tests) |
| local_harness tests | PASS |
| git diff --check | PASS (clean) |
| py_compile | PASS |
| Artifact cross-consistency (bp==fp==vm==mv) | PASS (20/20 tasks) |
| Budget plan → runtime wiring | PASS (resolve_budget_plan reads hard_cap_usd) |
| --budget overrides --budget-plan | PASS |
| Frozen plan fallback (no budget_plan) | PASS |
| No task-id hardcoding | PASS |
| SphinxHAdapter idempotency | PASS |
| No historical JSONL modification | PASS |
| Budget plan decision | PASS |

## Code changes

| File | Change |
|---|---|
| src/budgetflow/experiments/budget_binding.py | target_utilization mode, p75 reference, passive pressure audit |
| src/budgetflow/experiments/compare_cli.py | --budget-mode, --target-utilization CLI args |
| src/budgetflow/experiments/compare_readiness.py | budget_plan hard_cap as budget source |
| src/budgetflow/local_harness_adapters.py | SphinxHAdapter with idempotent jinja2 compat |
| tests/test_budget_binding.py | 11 new tests (p75, target_utilization, pressure audit) |
| tests/test_local_harness_pytest_nodes.py | 11 new tests (SphinxHAdapter dispatch, jinja2 patching, idempotency) |
| src/budgetflow/experiments/compare_setup.py | resolve_budget_plan reads hard_cap_usd from --budget-plan |
| tests/test_compare_setup.py | 3 new tests (budget_plan wiring, CLI override, frozen fallback) |
| src/budgetflow/allocation.py | AllocationContext dataclass (new file) |
| tests/test_allocation_context.py | AllocationContext tests (new file) |

## Residual risks (same as preflight)

1. Tight budget ($1.23): bare_t3 may time out — this is expected, confirms budget is binding
2. Zero-history Requests/Sphinx tasks: bootstrap estimates only, first-paid-run variance expected
3. Gold sanity pending for 4 new tasks
4. t3x2 catalog: tight-budget effect depends on diagnostic 2x pricing
5. 4-repo generalization not stress-tested in paid run

## Verdict: GO

All 19 gates pass. Critical fix: resolve_budget_plan now reads hard_cap_usd from
--budget-plan JSON, so the runtime uses $1.2262 (not $4.50 frozen cap sum) as
the shared hard budget. Budget plan is PASS with defensible pressure shape.

Recommend proceeding to paid 5x20 diagnostic run with the planned command in
`docs/reports/mainline_5x20_preflight.md`.

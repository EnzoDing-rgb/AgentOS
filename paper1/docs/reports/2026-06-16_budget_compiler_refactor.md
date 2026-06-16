# Budget Compiler Refactor

Date: 2026-06-16

## Objective

Tighten the Budget Regime Compiler before the next paid 6x5 diagnostic without
adding a new tuning surface. The goal is to support Claim 1 by making the shared
hard budget pre-registered, auditable, and calibrated by one diagnostic pass.

## Design Decision

Budget Compiler remains part of Value-Driven Budget Allocation, not a separate
claim. It compiles a minimal shared budget regime from pre-registered task IDs,
value/effort inputs, the model-tier catalog, current-schema cost observations,
budget-exhausted spend floors, one target utilization, and the Strongest Model
boundary. It does not search for an optimal budget and does not add
strategy-specific manual knobs.

Signals are separated:

- Complete observed cost: exact current-schema `total_cost` rows.
- Censored spend floor: budget-exhausted rows show that at least this much
  budget was consumed, but they are not complete cost samples.
- Calibration eligibility: active cost observations must be same-catalog,
  current-schema, and scoreable (`pass` or `true_fail`). Provider, parser,
  infra, missing-score, missing-catalog, and catalog-mismatched rows are
  forensic-only.
- Cold-start pressure prior: pre-registered task-effort features for tasks
  without clean cost observations. Frozen router plans no longer provide budget
  caps or cold-start pressure anchors.
- Strongest Model boundary: cap is not allowed to be wider than the projected
  all-T3 baseline spend, so the strongest baseline remains budget-constrained.

Low-sample cost-per-effort cross-task extrapolation was removed from active
projection because the 6x5 diagnostic showed it can over-widen the next cap from
one or two early completed rows.

The old `min_viable_budget` / loose / tight threshold fields were replaced by
direct audit fields: `reference_spend_usd`, `strongest_boundary_usd`, and
`max_projected_spend_usd`. In target-pressure mode the cap is allowed to be below
some strategies' projected complete spend; that is the point of a binding shared
budget, not a "minimum viable budget" violation.

## Files Changed

- `paper1/src/budgetflow/experiments/budget_binding.py`
- `paper1/src/budgetflow/frozen_router.py`
- `paper1/tests/test_budget_binding.py`
- `paper1/docs/north_star.md`

## Diagnostic Result

Using the fresh 6x5 diagnostic as one calibration pass and
`target_utilization=0.95` now produces a candidate next 6x5 hard cap of about
`0.5235` from the compiler:

- `bare_t3_baseline`: projected utilization `100.0%`
- `budgetflow_task_level`: raw projected utilization `109.9%`
- `budgetflow_segment`: raw projected utilization `110.3%`

This is the intended direction: the budget is tight enough that all-T3 is
budget-constrained, while BudgetFlow must win by allocating the same tight cap
toward higher verified value. Savings are primarily compiled into the shared cap;
runtime BudgetFlow is evaluated on value allocation under that cap.

## Residual Risks

- The calibration confidence remains `low` because the diagnostic was only 6x5
  and had many budget-exhausted rows.
- The pressure contract still names the paper-mainline strategy roles directly.
  This is acceptable for the immediate paper-mainline 6x5, but should become a
  strategy-role registry only if non-paper strategy sets become a first-class
  paid-run target.
- The next-run budget plan has been written to
  `paper1/docs/reports/mainline_6x5_budget_plan.target95.after_clean3.json`, but
  it is still diagnostic because projection confidence is `low`.
- The router-only frozen plan has been written to
  `paper1/docs/reports/mainline_6x30_frozen_router_plan.router_only.json`; active
  frozen router plans now fail fast if retired cap fields are present.

## Next Step

Run paid readiness against the regenerated plan, then run the new paid 6x5
diagnostic and inspect Yield, Yield per Dollar, actual utilization, budget
exhaustion, protocol/provider health, and scoreable evidence before drawing
mechanism conclusions.

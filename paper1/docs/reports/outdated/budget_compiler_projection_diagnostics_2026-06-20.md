# Budget Compiler Projection Diagnostics

Date: 2026-06-20

## Objective

Fix the paid-run blocker where the 4x25 budget plan still made
`budgetflow_task_level` look like a near-all-T2 policy, even after runtime
task-level routing was fixed to choose a task-fixed model tier before each
task starts.

## Root Cause

The Budget Regime Compiler and Runtime had different observability semantics.
The compiler generated the shared hard budget and per-task runway, but it did
not then audit how the current task-level runtime policy would behave under
those compiled task budgets. As a result, the budget plan projected
`budgetflow_task_level` at low spend, while the runtime decision probe expected
mixed T2/T3 use.

This was a diagnostic bug, not a reason to fit the cap to this task slice.

## Interface Decision

Keep the Budget Regime Compiler and BudgetFlow Runtime separate:

- `projected_spend_by_strategy` and `cap_generation_projected_spend_by_strategy`
  remain compiler budget-regime estimates.
- `planned_task_budget_by_strategy` remains the pre-registered per-task runway
  consumed by BudgetFlow active policies.
- `projection_diagnostics.budgetflow_task_level` is a readiness diagnostic. It
  mirrors current runtime task-start semantics to predict whether the compiled
  task budgets would make task-level BudgetFlow degenerate into a pure reference
  tier. It is not a cap source.

Readiness now blocks task-level BudgetFlow only when the structured diagnostic
reports `pure_reference_tier`. A low BudgetFlow utilization warning alone is
not treated as proof of mechanism failure, because BudgetFlow is allowed to
spend less than pure T3 when that is the value-efficient frontier.

## 4x25 Plan Check

Regenerated plan:
`paper1/docs/reports/mainline_4x25_tasklevel_fix_budget_plan_20260620.json`

Key fields:

- hard cap: `$21.5059`
- cap-generation projected spend:
  - bare T2: `$8.5142`
  - bare T3: `$21.7059`
  - enterprise router: `$8.9880`
  - budgetflow task-level: `$7.8991`
- task-level runtime projection diagnostic:
  - projected tier mix: `tier2=8`, `tier3=17`
  - projected spend if the runtime policy follows that mix: `$17.7665`
  - projected-to-T3 spend ratio: `0.8185`
  - degeneration: `mixed_or_strongest`

Paid readiness passed with this plan. It still warns that projection confidence
is unvalidated, so the next paid run should be treated as diagnostic evidence,
not final paper evidence.

## Verification

Commands:

```bash
PYTHONPATH=paper1/src pytest -q paper1/tests/test_budget_binding.py paper1/tests/test_compare_readiness.py paper1/tests/test_task_level_expected_cost.py paper1/tests/test_model_fit_estimator.py paper1/tests/test_compare_setup.py paper1/tests/test_compare_record_schema.py paper1/tests/test_run_guards.py

PYTHONPATH=paper1/src python paper1/src/budgetflow/run_mini_swe_compare.py \
  --ids "$TASK_IDS" \
  --strategies bare_t2_baseline,bare_t3_baseline,enterprise_router_baseline,budgetflow_task_level \
  --jobs 4 \
  --budget-plan paper1/docs/reports/mainline_4x25_tasklevel_fix_budget_plan_20260620.json \
  --frozen-plan paper1/docs/reports/mainline_4x25_glm51_frozen_router_plan_20260618.json \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix paper1/docs/reports/mainline_4x25_glm51_manual_value_matrix_20260618.json \
  --paid-readiness-only
```

Results:

- `192 passed`
- paid readiness result: `PASS`

## Residual Risk

The runtime policy projection is a deterministic readiness diagnostic, not an
exact spend predictor. The next paid run must still be monitored for actual
T2/T3 picks, actual utilization, provider health, harness trust, and Yield per
Dollar. If the run again shows all-T2 behavior, that is a Runtime/Allocation
bug, not a Budget Compiler cap-generation issue.

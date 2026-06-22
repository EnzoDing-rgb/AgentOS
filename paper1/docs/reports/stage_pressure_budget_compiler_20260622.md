# Stage-Pressure Budget Compiler Slice — 2026-06-22

## Objective

Make budget pressure a code-level compiler input instead of a hand-computed cap.
The immediate 4x30 need is a stage-1 pressure regime where the first 10 tasks'
reference spend consumes roughly 33%-35% of the total shared hard budget, so the
next clean paid stage can test both budget exhaustion behavior and Yield per
Dollar under tight enterprise-style budget pressure.

## Files Changed

- `paper1/src/budgetflow/experiments/budget_binding.py`
  - Added `BudgetPressureSpec`.
  - Added `stage_prefix_pressure` generation mode.
  - Added CLI flags:
    - `--stage-prefix-count`
    - `--stage-target-budget-fraction`
    - `--stage-reference-strategy`
  - Preserved `target_utilization` as the existing compiler mode.
  - Added `budget_pressure_spec` to budget plans and calibration audits.
  - Made pressure contract report `pressure_mode` and `target_pressure_fraction`.
- `paper1/src/budgetflow/experiments/compare_readiness.py`
  - Readiness now accepts the compiler-generated `stage_prefix_pressure` mode.
  - Readiness validates the required `budget_pressure_spec` fields.
  - Retired/unrecognized generation modes still block.
- `paper1/src/budgetflow/adapter/stall_guard.py`
  - Renamed `check_stagnation(planned_task_budget=...)` to
    `task_budget_cap=...` to match runtime semantics.
- `paper1/src/budgetflow/adapter/mini_swe_proxy.py`
  - Updated the stall guard call site to pass `allocation.effective_task_budget`
    as `task_budget_cap`.
- Tests:
  - `paper1/tests/test_budget_binding.py`
  - `paper1/tests/test_compare_readiness.py`
  - `paper1/tests/test_stall_guard.py`

## Interface Decisions

- Single entrypoint is still `budget_binding calibrate`.
- No manual cap path was added.
- `target_utilization` and `stage_prefix_pressure` are mutually exclusive
  compiler modes.
- Stage pressure formula:

```text
hard_cap_usd =
  sum(projected_task_cost[stage_reference_strategy][first N task_ids])
  / stage_target_budget_fraction
```

- The stage pressure mode intentionally does not apply the old strongest-runway
  floor. The purpose is to allow full-run projected oversubscription and verify
  budget-exhaustion termination under a tight shared hard budget.

## Deleted Stale Paths / Tests

- No stale runtime paths were deleted.
- The misleading stall guard keyword was removed from active tests and call
  sites rather than preserved as an alias.
- The suggested `remaining_task_ids` halted/skipped-task change was not applied:
  the cap is computed before each task starts, and after strategy halt the
  following tasks are skipped before `_effective_planned_task_cap` is called.

## New Artifacts

- `paper1/docs/reports/mainline_4x30_tasklevel_frontier_stage1_calibration_audit_20260622.json`
  - Audits the stopped 4x30 stage-1 run against the old cold budget plan.
  - Confidence: `unvalidated`.
  - Overall MAPE: 208.7%.
  - Key blocker: pure T3 stage-share utilization was 54.4%, below the 90%
    threshold, so the old budget regime was too loose.
- `paper1/docs/reports/mainline_4x30_stage_pressure35_budget_plan_20260622.json`
  - New 4x30 budget plan using `stage_prefix_pressure`.
  - Hard cap: `$9.6933`.
  - Pressure spec: first 10 tasks, reference strategy `bare_t3_baseline`,
    target budget fraction `0.35`.
  - First-10 projected budget shares:
    - bare T2: 85.74%
    - bare T3: 35.00%
    - enterprise router: 50.48%
    - BudgetFlow task-level: 35.00%
  - Full projected raw utilization:
    - bare T2: 275.11%
    - bare T3: 153.95%
    - enterprise router: 174.95%
    - BudgetFlow task-level: 153.95%

## Verification

- Red tests were observed before implementation for:
  - `calibrate_budget(... stage_prefix_count=...)`
  - `budget_binding calibrate --stage-prefix-count ...`
  - readiness accepting `stage_prefix_pressure`
  - stall guard accepting `task_budget_cap`
- Focused tests:

```bash
PYTHONPATH=paper1/src pytest -q \
  paper1/tests/test_budget_binding.py \
  paper1/tests/test_compare_readiness.py \
  paper1/tests/test_stall_guard.py
```

Result: `123 passed`.

- Broader no-paid gate:

```bash
PYTHONPATH=paper1/src pytest -q \
  paper1/tests/test_compare_record_schema.py \
  paper1/tests/test_budget_binding.py \
  paper1/tests/test_task_level_expected_cost.py \
  paper1/tests/test_stall_guard.py \
  paper1/tests/test_compare_readiness.py \
  paper1/tests/test_run_guards.py \
  paper1/tests/test_compare_setup.py \
  paper1/tests/test_run_series.py \
  paper1/tests/test_failure_classification.py \
  paper1/tests/test_model_tiers.py \
  paper1/tests/test_trace_fields.py \
  paper1/tests/test_recost.py
```

Result: `356 passed`.

- `py_compile` passed for edited modules.
- `git diff --check` passed.
- Paid-readiness-only with the new 35% stage-pressure plan passed and exited
  before provider signature checks.

## Residual Risks

- The new plan's task-level BudgetFlow projection is pure Strongest Model
  because the calibrated frontier is `strongest_cost_dominant`. This is allowed
  only as frontier-selection diagnostic evidence, not as proof of rich mixed
  routing.
- Projection confidence remains `unvalidated`; the next paid stage should be
  treated as diagnostic calibration evidence.
- The stopped run is historical diagnostic evidence only and must not be
  resumed.
- KV-cache discount remains sensitivity-only and is not in the mainline catalog.

## Next Recommended Slice

Run a clean paid 4x30 stage-1 restart with:

- `--budget-plan paper1/docs/reports/mainline_4x30_stage_pressure35_budget_plan_20260622.json`
- `--max-tasks-per-strategy 10`
- `--jobs 4`
- primary value matrix and frozen router unchanged
- live monitoring, stop on provider/billing/auth failures, and post-stage audit
  before any stage-2 continuation

The two outcomes to inspect first are:

1. Whether shared hard-budget exhaustion terminates cleanly.
2. Whether task-level frontier selection improves Yield per Dollar under the
   tighter `$9.6933` cap, even if it collapses to Strongest Model because the
   observed frontier says Strongest is cheaper in total.

# Task-Level Budget Cap And Stage-Prefix Audit

Date: 2026-06-22

## Objective

Fix no-paid blockers before the next clean 4x30 reset experiment. The slice
focuses on the two layers exposed by the 4x30 stage-1 audit and the historical
4x10 trace:

- planned task budget binding under a shared hard cap;
- 10+10+10 stage-prefix budget calibration;
- cold-start task-level frontier routing near the T2/T3 boundary.

No paid experiment was run.

## Artifact Diagnosis

The 4x30 stage-1 JSONL (`mainline_4x30_tasklevel_frontier_20260622-0.jsonl`)
shows a mechanism problem, not a provider/parser blocker:

- `bare_t3_baseline`: 6/10, Yield 6.0, cost $3.3926, Yield/$ 1.7685.
- `budgetflow_task_level`: 5/10, Yield 5.0, cost $3.1007, Yield/$ 1.6125.
- `enterprise_router_baseline`: 5/10, cost $4.4067.
- `bare_t2_baseline`: 4/8, cost $7.9403.

Rows are mostly harness-trusted and there were no billing/provider/parser aborts
driving the result. The T2 issue is long-tail turns and task-level misrouting,
not total T2 incapability.

The 6/17 4x10 forensic trace (`mainline_4x10_glm51_refit2_20260617-0.jsonl`)
is useful because BudgetFlow task-level won there:

- `budgetflow_task_level`: 7/10, cost $2.2869, Yield 8.1, Yield/$ 3.5419.
- `bare_t3_baseline`: 6/10, cost $2.2869, Yield 6.1, Yield/$ 2.6674.

The reusable lesson is not a task exception. It is the mechanism triple:
task-level routing, workload-level ModelFit / expected-total-cost reasoning,
and shared-cap-aware planned task budget binding.

## Fixes

1. Restored proportional planned-task-cap binding.

`_effective_planned_task_cap()` again allocates the current effective task cap
by current planned cap over remaining planned demand when planned caps exceed
shared remaining budget. This prevents one task from consuming budget that was
implicitly reserved for later tasks while still returning unused money to the
shared pool.

2. Split planned and effective task budget semantics.

`AllocationContext.planned_task_budget` now carries the compiler's original
task runway for routing decisions. `effective_task_budget` carries the runtime
cap after shared-budget rebalance and is used by the stall guard. This prevents
dynamic cap clipping from making routing think the task was intrinsically too
small for T3.

3. Added stage-prefix calibration audit.

`audit_calibration()` now compares actual spend with projected spend for the
completed task subset, not the whole 30-task plan. It also reports
`stage_budget_share` and `stage_share_actual_utilization`.

On the current 4x30 stage-1 audit, this now surfaces the budget problem
directly:

- pure T3 completed 10/30 tasks;
- stage budget share was $6.2426;
- actual pure T3 spend was $3.3926;
- stage-share utilization was 54.4%;
- recommendation: block/recompile because the budget regime is too loose for
  Yield per Dollar evidence.

4. Softened cold-start frontier effort boundary.

Cold-start uncertain-frontier probes now tolerate small Task Effort estimator
noise around the 20-effort boundary. Runtime and compiler projection use the
same 95% tolerance. This catches near-boundary hard SWE tasks without task-ID
rules and keeps trusted ModelFit behavior unchanged.

## Files Changed

- `paper1/src/budgetflow/experiments/compare_execution.py`
- `paper1/src/budgetflow/allocation.py`
- `paper1/src/budgetflow/adapter/mini_swe_proxy.py`
- `paper1/src/budgetflow/adapter/strategies.py`
- `paper1/src/budgetflow/experiments/budget_binding.py`
- `paper1/tests/test_compare_record_schema.py`
- `paper1/tests/test_budget_binding.py`
- `paper1/tests/test_task_level_expected_cost.py`

## Verification

- `PYTHONPATH=paper1/src pytest -q paper1/tests/test_compare_record_schema.py paper1/tests/test_budget_binding.py paper1/tests/test_task_level_expected_cost.py paper1/tests/test_stall_guard.py`
  - `148 passed`
- `PYTHONPATH=paper1/src pytest -q paper1/tests/test_compare_readiness.py paper1/tests/test_run_guards.py paper1/tests/test_compare_setup.py paper1/tests/test_run_series.py paper1/tests/test_failure_classification.py paper1/tests/test_model_tiers.py paper1/tests/test_trace_fields.py paper1/tests/test_recost.py`
  - `198 passed, 5 skipped`
- `python -m py_compile` on edited runtime/compiler modules
- `git diff --check`
- No paid process was running during the slice.

## Residual Risk

The next run still needs a clean regenerated budget plan. The current 4x30
stage-1 stopped run should not be resumed. The next no-paid gate should
generate a fresh plan whose pure T3 projected stage utilization is near the
binding 90%-95% regime, then run a clean staged 10+10+10 paid attempt.

# Task-Level T3 Regression Fix - 2026-06-20

## Objective

Fix the 4x25 regression where `budgetflow_task_level` silently degenerated into
100% T2 while the paid run continued. No paid experiment was run.

## Cause

The harness-v2 workspace-diff work improved scoring, but a separate mechanism
regression was already present in task-level routing:

- The Budget Compiler did produce both the shared hard budget and per-task
  `planned_task_budget`.
- Runtime threaded `planned_task_budget` into `AllocationContext`, but
  task-start T3 selection was dominated by a whole-task extra-cost marginal
  formula introduced in `103ca5d`.
- Recent calibration made workload Model Fit conservative
  (`tier2=0.81`, `tier3=0.85`). With whole-task extra cost in the denominator,
  the T3 score collapsed and every task chose T2.
- The 4x25 budget plan already warned `budgetflow_under_target`, but paid
  readiness treated that as non-blocking.
- The live guard watched infra/provider failures, but not the mechanism
  invariant that task-level routing must actually exercise the strongest tier
  when the plan expects a routing experiment.

## Files Changed

- `paper1/src/budgetflow/adapter/strategies.py`
- `paper1/src/budgetflow/experiments/compare_cli.py`
- `paper1/src/budgetflow/experiments/compare_readiness.py`
- `paper1/src/budgetflow/experiments/budget_binding.py`
- `paper1/src/budgetflow/run_guards.py`
- `paper1/src/budgetflow/defaults.py`
- Focused tests under `paper1/tests/`
- `paper1/docs/north_star.md`

## Interface Decisions

- Task-level routing remains task-fixed: it chooses one tier before the task
  starts. It does not rely on mid-task T2-to-T3 escalation.
- T3 task-start scoring again uses unit extra cost, while
  `planned_task_budget` remains the whole-task budget gate.
- `budgetflow_under_target` remains a compiler warning, but paid readiness now
  blocks primary paid runs using such a plan.
- The CLI step-limit default is now the paid mainline safety cap (`60`) instead
  of the old exploratory `150`; readiness blocks paper-mainline values above
  the cap.
- Live guards now stop a run if `budgetflow_task_level` completes several
  scoreable rows with zero Strongest Model usage.

## Verification

- `PYTHONPATH=paper1/src pytest -q paper1/tests/test_task_level_expected_cost.py paper1/tests/test_budget_binding.py paper1/tests/test_run_guards.py paper1/tests/test_compare_readiness.py`
  - `117 passed`
- `PYTHONPATH=paper1/src pytest -q paper1/tests/test_task_level_expected_cost.py paper1/tests/test_budget_binding.py paper1/tests/test_run_guards.py paper1/tests/test_compare_readiness.py paper1/tests/test_compare_setup.py paper1/tests/test_compare_record_schema.py`
  - `164 passed`
- `PYTHONPATH=paper1/src python paper1/src/budgetflow/run_mini_swe_compare.py ... --paid-readiness-only`
  - Existing 4x25 budget plan now fails before provider calls with
    `budgetflow_under_target`.
- Local no-provider mechanism probe with the 4x25 plan:
  - Before fix: task-level selected T2 for every observed row.
  - After fix: projected task-start choices are `tier3=17`, `tier2=8`.

## Residual Risk

The latest paid JSONL remains partial and should be treated as forensic
diagnostic evidence only. The next paid run should use a regenerated budget plan
that passes the new paid-readiness gate.

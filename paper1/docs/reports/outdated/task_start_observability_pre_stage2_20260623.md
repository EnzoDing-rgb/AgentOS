# Task-Start Observability Before Stage 2

## Objective

Preserve the current 3x30 paid run and improve BudgetFlow task-level diagnosis before resuming stage 2.

## Changes

- Added task-start decision fields to future `budgetflow_task_level` JSONL rows:
  - `task_start_selected_backend`
  - `task_start_selected_tier`
  - `task_start_reason`
  - `task_start_scores`
  - `task_start_confidence`
- Kept routing behavior unchanged.
- Split pre-cap and final tier observability so a budget safety cap cannot be misread as the original router choice.

## Stage-1 Evidence

Stage 1 is complete: 30/30 scoreable rows across 10 tasks and 3 policies.

- `budgetflow_task_level`: Yield 7.5, cost $1.9970, Yield/$ 3.7556
- `bare_t3_baseline`: Yield 5.5, cost $1.6549, Yield/$ 3.3235
- `bare_t2_baseline`: Yield 5.0, cost $2.2647, Yield/$ 2.2078

The signal is positive but not thick enough to justify changing routing mid-run.

## Verification

- `pytest -q paper1/tests/test_task_level_expected_cost.py paper1/tests/test_compare_record_schema.py paper1/tests/test_run_guards.py`
- `py_compile` on changed source files
- `git diff --check`

## Residual Risk

Stage-1 rows predate the new fields. Stage-2 rows will carry direct task-start tier/reason/scores.

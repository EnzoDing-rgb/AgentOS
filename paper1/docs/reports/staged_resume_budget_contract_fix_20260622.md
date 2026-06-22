# Staged resume budget contract fix (2026-06-22)

## Objective

Make the 30-task KV50 stage-prefix plan usable for cumulative 10+10+10 paid
execution without changing the compiled budget plan.

## Fix

- Runtime planned-task cap clipping now receives the budget plan task order and
  the compiled stage-prefix limit.
- Resume execution still runs only unfinished tasks, but cap rebalancing uses
  the same compiled prefix contract as the no-paid projection.
- Readiness now blocks only when `stage_prefix_count` is larger than the
  current staged run target. A `stage_prefix_count=10` plan can be reused for
  cumulative `--max-tasks-per-strategy 10`, `20`, and `30`.

## Verification

- `PYTHONPATH=paper1/src /root/anaconda3/bin/python3.11 -m pytest -q ...`
  focused suite: `236 passed`.
- `git diff --check`: clean.
- `py_compile` on changed runtime/readiness/routing files: pass.
- `--paid-readiness-only` passed for cumulative staged targets 10, 20, and 30
  using `mainline_4x30_stage_prefix10_kv50_budget_plan_20260622.json`.

## Residual Risk

The KV50 plan remains `projection_confidence=unvalidated`; it is a monitored
cold-start diagnostic, not final paper evidence.

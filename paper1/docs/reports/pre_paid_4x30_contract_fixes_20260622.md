# Pre-Paid 4x30 Contract Fixes — 2026-06-22

## Objective

Fix no-paid blockers before any next 4x30 paid candidate. This slice does not tune routing thresholds.

## Changes

- Removed the stale `handoff.md`.
- Made task-start effort scaling a shared compiler/runtime helper. The compiler no longer hardcodes `effort / 35`; it uses the active catalog reference runway.
- Fixed task-start score observability: traces now distinguish `planned_task_budget`, `effective_task_budget`, and the effective-first `runtime_task_budget`.
- Closed the active Task Effort schema path around `final_task_effort`. Runtime/compiler/frozen-router inputs reject retired `task_effort.bootstrap_heuristic` fallbacks.
- Regenerated the current 4x30 value matrix and frozen router artifacts with no retired effort field.

## Current Plan State

- Historical-calibrated stage-pressure plan: `BLOCK`, projected `budgetflow_task_level = 30 T3 / 0 T2`, correctly rejected as pure Strongest Model.
- Cold/no-history stage-pressure plan: `PASS`, projected `budgetflow_task_level = 15 T2 / 15 T3`, but `projection_confidence=unvalidated`.
- Frozen enterprise router remains `20 T2 / 10 T3`.

## Verification

- Focused no-paid suite: `268 passed`.
- Related value/model-fit/allocation suites: included in the same focused run.
- `py_compile`: passed for edited source files.
- `git diff --check`: passed.

## Recommendation

Do not run the historical-calibrated plan as paper evidence. If running tonight, use the cold plan as a diagnostic candidate and monitor `10+10+10` closely.

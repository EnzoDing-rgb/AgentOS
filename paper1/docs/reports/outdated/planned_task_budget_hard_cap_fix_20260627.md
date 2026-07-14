# Planned Task Budget Hard-Cap Fix - 2026-06-27

## Objective

Fix the bug where `effective_task_budget` was recorded and used for routing, but did not hard-stop execution before the next provider call. The bug allowed BudgetFlow task-level runs to continue spending on a single task after the planned task budget was exhausted.

## Root Cause

The shared `BudgetGovernor` enforced only the policy-level shared batch cap. `planned_task_budget` / `effective_task_budget` were threaded into `AllocationContext`, routing, stall checks, and records, but the adapter reserve path did not check per-task spent amount before provider calls.

## Interface Decisions

- `planned_task_budget` is the compiler's per-task demand/cap weight.
- `effective_task_budget` is the live per-task hard cap after clipping against remaining shared budget and remaining planned demand.
- Pure T2 and pure T3 controls keep the shared batch cap plus the global turn cap.
- RouteLLM-inspired learned router receives the same generic per-task hard cap as BudgetFlow, but not BudgetFlow's value-aware stall guard or escalation logic.
- The active budget mode is now `planned_task_budget`, not `budgetflow_planned_task_budget`, because the cap is no longer BudgetFlow-only.

## Files Changed

- `adapter/mini_swe_proxy.py`: tracks per-task spend, limits reserve output tokens by task remaining budget, blocks provider calls when the task cap is exhausted, and records `task_budget_exhausted` snapshots.
- `experiments/compare_setup.py`, `compare_execution.py`, `compare_readiness.py`, `budget_binding.py`: route planned task budgets to BudgetFlow and RouteLLM, require them for the 4-policy mainline, and remove BudgetFlow-only mode naming.
- `planned_task_budget.py`, `allocation.py`, `north_star.md`: clarify compiler/runtime semantics.
- Tests: added/updated regression coverage for task hard caps, RouteLLM planned caps, mainline contract, and BudgetFlow stall guard ownership.

## Deleted Stale Paths

No broad deletion was needed. The stale active mode name `budgetflow_planned_task_budget` was removed from active source/tests. Historical JSONL and reports were left immutable.

## Verification

- `PYTHONPATH=paper1/src:external/mini-swe-agent/src python -m py_compile ...` passed for touched runtime modules.
- `PYTHONPATH=paper1/src:external/mini-swe-agent/src pytest paper1/tests/test_gold_edit_stop_loss.py paper1/tests/test_stall_guard.py paper1/tests/test_compare_setup.py paper1/tests/test_compare_record_schema.py -q` -> `90 passed`.
- `PYTHONPATH=paper1/src pytest paper1/tests/test_budget_binding.py paper1/tests/test_compare_readiness.py -q` -> `111 passed`.
- `PYTHONPATH=paper1/src:external/mini-swe-agent/src pytest ...focused related set... -q` -> `324 passed`.

## Residual Risks

- Existing budget plans with mode `budgetflow_planned_task_budget` are stale and should block readiness for new paid runs. Regenerate the budget plan before resuming the clean evidence line.
- Because RouteLLM semantics now include generic per-task caps, old RouteLLM rows from before this fix are forensic-only for the new 4-policy evidence line.
- Provider bills can still exceed a reservation inside one provider response if actual usage exceeds the requested `max_tokens`/provider accounting behavior. The adapter now clamps future calls before spending continues.

## Next Slice

Regenerate the 4-policy budget plan, run no-paid readiness, then resume/rerun from the clean point before the polluted task under the new `planned_task_budget` contract.

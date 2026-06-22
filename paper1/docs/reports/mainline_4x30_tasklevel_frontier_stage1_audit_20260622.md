# Mainline 4x30 Task-Level Frontier Stage-1 Audit

Date: 2026-06-22

## Objective

Run the first `10+10+10` stage for the 4-policy task-level frontier probe, then
stop and inspect Yield per Dollar before continuing. The run was intentionally
stopped before stage 2 after the main comparison rows completed and the pure T2
tail had already exposed the relevant cost signal.

## Run State

- Run series: `mainline_4x30_tasklevel_frontier_20260622-0`
- JSONL: `paper1/data/runs/mainline_4x30_tasklevel_frontier_20260622-0.jsonl`
- Stage-1 expected shape: 10 task positions x 4 policies = 40 rows.
- Completed before stop: 38/40 rows.
- Completed policies: `budgetflow_task_level`, `bare_t3_baseline`,
  `enterprise_router_baseline` all reached 10/10. `bare_t2_baseline` reached
  8/10 and was stopped after repeated T2 long-tail evidence.
- Stop reason: manual stage audit stop, not provider/billing/auth failure.

No background paid process remained after stopping.

## Primary Result

| Strategy | Rows | Pass | Yield | Cost | Yield/$ | Turns |
|---|---:|---:|---:|---:|---:|---:|
| bare_t3_baseline | 10 | 6 | 6.0 | 3.3926 | 1.7685 | 85 |
| budgetflow_task_level | 10 | 5 | 5.0 | 3.1007 | 1.6125 | 117 |
| enterprise_router_baseline | 10 | 5 | 5.0 | 4.4067 | 1.1346 | 212 |
| bare_t2_baseline | 8 | 4 | 4.5 | 7.9403 | 0.5667 | 342 |

BudgetFlow task-level beat enterprise and the partial pure T2 baseline on
Yield per Dollar, but did not beat the pure T3 frontier. This is not positive
Claim 1 evidence yet.

## Mechanism Diagnosis

The main failure mode is not that T2 is completely incapable. T2 often finds a
patch or even resolves the task, but too many turns destroy value per dollar.

Clear T2 cost traps:

- `pylint-dev__pylint-7993`: pure T2 passed with 56 turns / $1.4654. BudgetFlow
  and pure T3 passed in 7-8 T3 turns at much lower cost.
- `sympy__sympy-18621`: pure T2 passed with 39 turns / $0.6301. Pure T3 passed
  in 7 turns / $0.1790.
- `sphinx-doc__sphinx-7738`: pure T2 failed at 60 turns / $1.7297. Pure T3 also
  failed, but only 11 turns / $0.4831.
- `django__django-11049`: BudgetFlow selected T2 and failed after 23 turns /
  $0.1993. Pure T3 passed after 9 turns / $0.3455. This is the clearest
  task-level frontier misroute in the completed BudgetFlow rows.

Positive T2 frontier examples still exist:

- `django__django-15851`: enterprise T2 passed at 12 turns / $0.0766, cheaper
  than the T3 rows.
- `mwaskom__seaborn-3010`: enterprise T2 passed at 13 turns / $0.1072, cheaper
  than BudgetFlow/pure T3. Pure T2 failed cheaply on the same task, so this row
  also shows agent-path variance rather than a deterministic model-fit fact.

Conclusion: the reusable mechanism is not "route everything to T3." The policy
needs stronger task-level frontier selection and earlier escape from T2
long-tail loops.

## KV-Cache Sensitivity

Mainline cost remains unchanged: no KV-cache discount in the default catalog.
This slice adds only offline recost sensitivity for T2/T3 multi-turn input-cache
discounts.

At 25% input KV discount after the first turn for both T2 and T3:

| Strategy | Rows | Pass | Yield | Re-cost | Yield/$ |
|---|---:|---:|---:|---:|---:|
| bare_t3_baseline | 10 | 6 | 6.0 | 2.6950 | 2.2263 |
| budgetflow_task_level | 10 | 5 | 5.0 | 2.4467 | 2.0436 |
| enterprise_router_baseline | 10 | 5 | 5.0 | 3.4429 | 1.4523 |
| bare_t2_baseline | 8 | 4 | 4.5 | 6.1105 | 0.7364 |

At 50% input KV discount after the first turn for both T2 and T3:

| Strategy | Rows | Pass | Yield | Re-cost | Yield/$ |
|---|---:|---:|---:|---:|---:|
| bare_t3_baseline | 10 | 6 | 6.0 | 1.9974 | 3.0039 |
| budgetflow_task_level | 10 | 5 | 5.0 | 1.7927 | 2.7891 |
| enterprise_router_baseline | 10 | 5 | 5.0 | 2.4811 | 2.0152 |
| bare_t2_baseline | 8 | 4 | 4.5 | 4.2807 | 1.0512 |

KV discount does not flip the primary direction. It lowers every multi-turn
strategy's cost, but BudgetFlow still trails pure T3 because it lost one
resolved task and had two completed T2-only misroutes.

## Files Changed

- `paper1/src/budgetflow/recost.py`
  - Added optional offline KV-cache sensitivity parameters.
  - Re-costs from per-turn traces when available instead of only average row
    token counts.
  - Applies explicit T2/T3 input-token KV discount after a configurable turn,
    leaving outputs undiscounted.
- `paper1/tests/test_recost.py`
  - Added regression tests for T2/T3 KV-cache sensitivity and CLI flags.
- `paper1/docs/reports/mainline_4x30_tasklevel_frontier_stage1_kv_sensitivity_20260622.json`
  - 25% KV discount sensitivity report.
- `paper1/docs/reports/mainline_4x30_tasklevel_frontier_stage1_kv50_sensitivity_20260622.json`
  - 50% KV discount sensitivity report.

## Next Recommended Slice

Do not continue to stage 2 with the current task-level policy. First fix the
frontier-selection diagnostic for T2 long-tail risk:

1. Use observed early-turn behavior or static task features to identify tasks
   where T2 is likely to consume many turns before resolution.
2. Add a task-level escape rule from T2 to T3 or a stop rule when the policy is
   spending T2 turns without patch-quality progress.
3. Re-run no-paid projection/readiness, then restart stage 1 cleanly rather
   than resuming this stopped paid run.


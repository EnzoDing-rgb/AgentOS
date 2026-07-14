# Stage 2+3 softgate result (2026-06-23)

Objective: finish the remaining 20 tasks of the low/medium/high 3x30 cycle after the task-start soft budget gate fix, without rerunning stage 1.

Run:
- JSONL: `paper1/data/runs/mainline_3x30_lhm_cycle_stage23_softgate_kv50_20260623.jsonl`
- Budget plan: `paper1/docs/reports/mainline_3x30_lhm_cycle_stage23_from_stage12_fit_softgate_budget_plan_20260623.json`
- Strategies: `bare_t2_baseline`, `bare_t3_baseline`, `budgetflow_task_level`
- Catalog: KV50 diagnostic catalog, T2/T3 cache discount enabled

Result:

| Segment | Strategy | Pass | Yield | Cost | Yield/$ |
| --- | --- | ---: | ---: | ---: | ---: |
| Stage 2 | bare T2 | 7/10 | 8.5 | 3.8384 | 2.2145 |
| Stage 2 | bare T3 | 5/10 | 6.0 | 2.6567 | 2.2585 |
| Stage 2 | BF task-level | 5/10 | 6.0 | 2.2158 | 2.7078 |
| Stage 3 | bare T2 | 0/10 | 0.0 | 1.0250 | 0.0000 |
| Stage 3 | bare T3 | 5/10 | 5.0 | 1.7425 | 2.8694 |
| Stage 3 | BF task-level | 4/10 | 4.0 | 1.9724 | 2.0280 |
| Stage 2+3 | bare T2 | 7/20 | 8.5 | 4.8634 | 1.7477 |
| Stage 2+3 | bare T3 | 10/20 | 11.0 | 4.3992 | 2.5005 |
| Stage 2+3 | BF task-level | 9/20 | 10.0 | 4.1882 | 2.3876 |

Mechanism diagnosis:
- Stage 2 has a real cost-efficiency signal: BF matched bare T3 Yield and spent less, mostly by avoiding long failure spend.
- Stage 3 is the reversal: BF selected T3 on all 10 tasks, so the loss is not a T2/T3 routing-ratio bug.
- The key negative delta is `sphinx-doc__sphinx-8801`: bare T3 passed, BF also used T3 but produced a corrupt patch and failed.
- In stage 3, BF is effectively "T3 plus BudgetFlow task-control", including task caps, pressure, stall observability, and stop/runway behavior. Pure T3 is vanilla fixed-tier control. Those paths are not identical rollouts.
- Therefore the stage 3 loss should be treated as a Claim 2 mechanism warning: when task-level routing degenerates to all T3, BF must either preserve pure T3 productivity or clearly save enough failed-task spend to compensate. This run did neither.

Recommended next step:
- Do not rerun stage 1.
- Do not start another paid rerun from this result alone.
- Before any further paid work, isolate whether `value_aware_task_level` should keep BudgetFlow stop/runway controls when the selected tier is already T3, or whether task-level routing evidence needs a cleaner "same T3 loop, different task-start tier" control.

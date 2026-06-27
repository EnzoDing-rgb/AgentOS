# 4x30 Clean Resume Manifest - 2026-06-27

## Objective

Create a policy-specific clean resume seed after the planned-task-budget hard-cap fix. Historical JSONL remains immutable; this seed copies only scoreable rows that are defensible under the current execution contract.

## Resume Points

| Strategy | Retained | Next Task | Retained Spend | First Excluded Reason |
|---|---:|---|---:|---|
| `bare_t2_baseline` | 12/30 | `sympy__sympy-22714` | $7.1084 | none |
| `bare_t3_baseline` | 20/30 | `sphinx-doc__sphinx-8801` | $6.0753 | none |
| `routellm_learned_router_baseline` | 1/30 | `mwaskom__seaborn-3190` | $0.0868 | scoreable_cost_exceeds_recomputed_effective_task_budget |
| `budgetflow_task_level` | 1/30 | `mwaskom__seaborn-3190` | $0.1401 | scoreable_cost_exceeds_recomputed_effective_task_budget |

## Files

- Seed JSONL: `paper1/data/runs/mainline_4x30_lhm_cycle_4policy_cleanresume_20260627.jsonl`
- Seed checkpoint: `paper1/data/runs/mainline_4x30_lhm_cycle_4policy_cleanresume_20260627.checkpoint.json`
- Budget plan: `paper1/docs/reports/mainline_4x30_lhm_cycle_4policy_planned_task_budget_regen_v2value_20260627.json`
- Machine manifest: `paper1/docs/reports/mainline_4x30_lhm_cycle_4policy_cleanresume_manifest_20260627.json`

## Decision

Resume from this new seed stem with `--resume --out-stem mainline_4x30_lhm_cycle_4policy_cleanresume_20260627`. The runner will skip the retained pairs and continue each policy from its own next task.

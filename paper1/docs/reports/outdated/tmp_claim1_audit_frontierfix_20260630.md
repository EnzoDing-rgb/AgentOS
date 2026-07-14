# Claim 1 Matrix And Task Order Audit

This is a no-paid audit of completed JSONL rows. It does not re-score patches or edit historical artifacts.

## Strategy Summary

| Strategy | Lane State | Rows | Scoreable | Abort | Resolved | Rate (planned) | Rate (scoreable) | Spend | Cost / Resolved | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | budget_exhausted | 24/30 | 24/30 | 0 | 11/30 | 36.7% | 45.8% | $9.95 | $0.90 | 12.00 | 1.21 |
| bare_t3_baseline | complete | 30/30 | 30/30 | 0 | 15/30 | 50.0% | 50.0% | $9.95 | $0.66 | 16.50 | 1.66 |
| routellm_learned_router_baseline | budget_exhausted | 29/30 | 29/30 | 0 | 15/30 | 50.0% | 51.7% | $9.95 | $0.66 | 17.00 | 1.71 |
| budget_only_baseline | budget_exhausted | 26/30 | 26/30 | 0 | 12/30 | 40.0% | 46.2% | $9.95 | $0.83 | 13.00 | 1.31 |
| budgetflow_task_level | complete | 30/30 | 30/30 | 0 | 16/30 | 53.3% | 53.3% | $9.95 | $0.62 | 18.00 | 1.81 |

## Execution Coverage

This separates planned tasks from tasks that actually consumed model budget. Zero-cost rows are usually budget-exhaustion placeholders, not failed model attempts.

| Strategy | Planned | Rows Written | Paid Attempts | Zero-Cost Rows | Missing Rows | Paid Resolved | Total Resolved | Spend |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | 30 | 24 | 18 | 6 | 6 | 11 | 11 | $9.95 |
| bare_t3_baseline | 30 | 30 | 25 | 5 | 0 | 15 | 15 | $9.95 |
| routellm_learned_router_baseline | 30 | 29 | 24 | 5 | 1 | 15 | 15 | $9.95 |
| budget_only_baseline | 30 | 26 | 19 | 7 | 4 | 12 | 12 | $9.95 |
| budgetflow_task_level | 30 | 30 | 24 | 6 | 0 | 16 | 16 | $9.95 |

## Value Sensitivity

Same resolved/not-resolved rows and same spend, rescored under alternate frozen Task Value profiles.

| Value Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|
| equal | bare_t2_baseline | 11/30 | $9.95 | 11.00 | 1.11 |
| equal | bare_t3_baseline | 15/30 | $9.95 | 15.00 | 1.51 |
| equal | routellm_learned_router_baseline | 15/30 | $9.95 | 15.00 | 1.51 |
| equal | budget_only_baseline | 12/30 | $9.95 | 12.00 | 1.21 |
| equal | budgetflow_task_level | 16/30 | $9.95 | 16.00 | 1.61 |
| criticality_value | bare_t2_baseline | 11/30 | $9.95 | 12.00 | 1.21 |
| criticality_value | bare_t3_baseline | 15/30 | $9.95 | 16.50 | 1.66 |
| criticality_value | routellm_learned_router_baseline | 15/30 | $9.95 | 17.00 | 1.71 |
| criticality_value | budget_only_baseline | 12/30 | $9.95 | 13.00 | 1.31 |
| criticality_value | budgetflow_task_level | 16/30 | $9.95 | 18.00 | 1.81 |
| compressed_criticality | bare_t2_baseline | 11/30 | $9.95 | 11.50 | 1.16 |
| compressed_criticality | bare_t3_baseline | 15/30 | $9.95 | 15.75 | 1.58 |
| compressed_criticality | routellm_learned_router_baseline | 15/30 | $9.95 | 16.00 | 1.61 |
| compressed_criticality | budget_only_baseline | 12/30 | $9.95 | 12.50 | 1.26 |
| compressed_criticality | budgetflow_task_level | 16/30 | $9.95 | 17.00 | 1.71 |
| expanded_criticality | bare_t2_baseline | 11/30 | $9.95 | 13.00 | 1.31 |
| expanded_criticality | bare_t3_baseline | 15/30 | $9.95 | 18.00 | 1.81 |
| expanded_criticality | routellm_learned_router_baseline | 15/30 | $9.95 | 19.00 | 1.91 |
| expanded_criticality | budget_only_baseline | 12/30 | $9.95 | 14.00 | 1.41 |
| expanded_criticality | budgetflow_task_level | 16/30 | $9.95 | 20.00 | 2.01 |

### BudgetFlow Margin Under Value Sensitivity

| Value Profile | Best Control By Value | BudgetFlow Value Delta | Best Control By Value/$ | BudgetFlow Value/$ Delta |
|---|---|---:|---|---:|
| equal | routellm_learned_router_baseline | +1.00 | routellm_learned_router_baseline | +0.10 |
| criticality_value | routellm_learned_router_baseline | +1.00 | routellm_learned_router_baseline | +0.10 |
| compressed_criticality | routellm_learned_router_baseline | +1.00 | routellm_learned_router_baseline | +0.10 |
| expanded_criticality | routellm_learned_router_baseline | +1.00 | routellm_learned_router_baseline | +0.10 |

### Value Permutation Diagnostic

This shuffles the same criticality-value multiset across the fixed task list. It is a diagnostic for value-placement dependence, not a replacement for the frozen main ValueSource.

| Samples | BudgetFlow Wins | Min Margin | P25 | Median | P75 | Max Margin |
|---:|---:|---:|---:|---:|---:|---:|
| 64 | 64/64 | +0.50 | +1.00 | +1.00 | +1.00 | +1.50 |

## Static Observed-Tier Oracle

- Skipped: complete pure T2 and pure T3 rows are required for all tasks.

## Task-Level Frontier Diagnostic

Pure T2 vs pure T3 counterfactuals on tasks where both tiers actually consumed model budget. This answers whether the batch contains a real T2-can-win frontier, rather than treating cheaper per-token pricing as enough.

- Comparable paid T2/T3 tasks: 18/30; skipped for missing or zero-cost tier row: 12.

| Frontier Bucket | Tasks | Total Value | Avg T2 Cost | Avg T3 Cost | Avg T2 Turns | Avg T3 Turns | Examples |
|---|---:|---:|---:|---:|---:|---:|---|
| T2 cheaper pass | 6 | 6.00 | $0.13 | $0.22 | 18.7 | 6.3 | `django__django-13447`, `sphinx-doc__sphinx-8595`, `mwaskom__seaborn-3010`, `django__django-15851` |
| T3 cheaper pass | 5 | 6.00 | $0.85 | $0.37 | 44.8 | 8.8 | `mwaskom__seaborn-3190`, `pylint-dev__pylint-7993`, `sympy__sympy-17655`, `django__django-11179` |
| T2-only pass | 0 | 0.00 | $0.00 | $0.00 | 0.0 | 0.0 | - |
| T3-only pass | 0 | 0.00 | $0.00 | $0.00 | 0.0 | 0.0 | - |
| both fail | 7 | 8.00 | $0.70 | $0.69 | 36.3 | 11.6 | `pallets__flask-4992`, `pallets__flask-4045`, `sphinx-doc__sphinx-7738`, `pylint-dev__pylint-6506` |

- Interpretation: T2 has 6 task-level opportunities and T3 has 5; BudgetFlow can win only if it captures the T2 opportunities without missing T3-only or T3-cheaper passes.

## Runtime CostSource Audit

- Runtime catalog paths: `/root/.dev/AgentOS/paper1/docs/config/model_tiers.default.json` (139 rows).
- Runtime turn-cache policy observed on paid turns: input_kv_cache_discount=0.0, after_turn=1, min_input_cost_fraction=1.0 (2369 turns).
- Runtime charged input fractions observed on paid turns: 1.0 (2369 turns).
- Interpretation: this run used runtime KV-cache discount 0.0; KV sensitivity below is no-paid recosting, not the executed runtime policy.

## KV Cache Sensitivity

No-paid CostSource sensitivity: outcomes stay fixed while repeated input-token cost is recomputed for T2/T3 turns. This does not simulate additional tasks becoming runnable under a cheaper runtime.

| KV Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|
| KV0 | bare_t2_baseline | 11/30 | $9.95 | 12.00 | 1.21 |
| KV0 | bare_t3_baseline | 15/30 | $9.95 | 16.50 | 1.66 |
| KV0 | routellm_learned_router_baseline | 15/30 | $9.95 | 17.00 | 1.71 |
| KV0 | budget_only_baseline | 12/30 | $9.95 | 13.00 | 1.31 |
| KV0 | budgetflow_task_level | 16/30 | $9.95 | 18.00 | 1.81 |
| KV50 | bare_t2_baseline | 11/30 | $5.26 | 12.00 | 2.28 |
| KV50 | bare_t3_baseline | 15/30 | $5.73 | 16.50 | 2.88 |
| KV50 | routellm_learned_router_baseline | 15/30 | $5.41 | 17.00 | 3.14 |
| KV50 | budget_only_baseline | 12/30 | $5.38 | 13.00 | 2.42 |
| KV50 | budgetflow_task_level | 16/30 | $5.53 | 18.00 | 3.26 |
| KV90 | bare_t2_baseline | 11/30 | $1.61 | 12.00 | 7.46 |
| KV90 | bare_t3_baseline | 15/30 | $2.34 | 16.50 | 7.06 |
| KV90 | routellm_learned_router_baseline | 15/30 | $1.89 | 17.00 | 8.98 |
| KV90 | budget_only_baseline | 12/30 | $1.73 | 13.00 | 7.52 |
| KV90 | budgetflow_task_level | 16/30 | $1.99 | 18.00 | 9.06 |
| KV98 | bare_t2_baseline | 11/30 | $0.88 | 12.00 | 13.63 |
| KV98 | bare_t3_baseline | 15/30 | $1.66 | 16.50 | 9.94 |
| KV98 | routellm_learned_router_baseline | 15/30 | $1.19 | 17.00 | 14.28 |
| KV98 | budget_only_baseline | 12/30 | $1.00 | 13.00 | 13.00 |
| KV98 | budgetflow_task_level | 16/30 | $1.28 | 18.00 | 14.08 |
| KV99 | bare_t2_baseline | 11/30 | $0.79 | 12.00 | 15.21 |
| KV99 | bare_t3_baseline | 15/30 | $1.58 | 16.50 | 10.47 |
| KV99 | routellm_learned_router_baseline | 15/30 | $1.10 | 17.00 | 15.41 |
| KV99 | budget_only_baseline | 12/30 | $0.91 | 13.00 | 14.31 |
| KV99 | budgetflow_task_level | 16/30 | $1.19 | 18.00 | 15.13 |

### BudgetFlow Margin Under KV Sensitivity

| KV Profile | Best Control By Value/$ | BudgetFlow Value/$ Delta | BudgetFlow vs Pure T3 Value/$ Delta |
|---|---|---:|---:|
| KV0 | routellm_learned_router_baseline | +0.10 | +0.15 |
| KV50 | routellm_learned_router_baseline | +0.11 | +0.37 |
| KV90 | routellm_learned_router_baseline | +0.09 | +2.00 |
| KV98 | routellm_learned_router_baseline | -0.20 | +4.14 |
| KV99 | routellm_learned_router_baseline | -0.29 | +4.66 |

## Dynamic KV Replay

No-paid sequential replay under cheaper KV profiles. The fixed-policy table replays each policy's observed task order and observed outcomes with recosted rows; it does not invent outcomes for tasks that never ran. The BudgetFlow tail upper-bound then asks how much extra value could be recovered if cheaper KV let the already-observed BudgetFlow lane reach later tasks and we fill those later tasks with pure T2/T3 observed counterfactuals.

- Shared hard budget: $9.9544.

### Fixed-Policy Replay

| KV Profile | Strategy | Covered Rows | Spend | Resolved | Total Resolved Value | Stop Reason |
|---|---|---:|---:|---:|---:|---|
| KV0 | bare_t2_baseline | 18/30 | $9.95 | 11/30 | 12.00 | zero_cost_placeholder |
| KV0 | bare_t3_baseline | 25/30 | $9.95 | 15/30 | 16.50 | zero_cost_placeholder |
| KV0 | routellm_learned_router_baseline | 23/30 | $9.95 | 15/30 | 17.00 | zero_cost_placeholder |
| KV0 | budget_only_baseline | 19/30 | $9.95 | 12/30 | 13.00 | zero_cost_placeholder |
| KV0 | budgetflow_task_level | 23/30 | $9.95 | 16/30 | 18.00 | zero_cost_placeholder |
| KV50 | bare_t2_baseline | 18/30 | $5.26 | 11/30 | 12.00 | zero_cost_placeholder |
| KV50 | bare_t3_baseline | 25/30 | $5.73 | 15/30 | 16.50 | zero_cost_placeholder |
| KV50 | routellm_learned_router_baseline | 23/30 | $5.41 | 15/30 | 17.00 | zero_cost_placeholder |
| KV50 | budget_only_baseline | 19/30 | $5.38 | 12/30 | 13.00 | zero_cost_placeholder |
| KV50 | budgetflow_task_level | 23/30 | $5.52 | 16/30 | 18.00 | zero_cost_placeholder |
| KV90 | bare_t2_baseline | 18/30 | $1.61 | 11/30 | 12.00 | zero_cost_placeholder |
| KV90 | bare_t3_baseline | 25/30 | $2.34 | 15/30 | 16.50 | zero_cost_placeholder |
| KV90 | routellm_learned_router_baseline | 23/30 | $1.89 | 15/30 | 17.00 | zero_cost_placeholder |
| KV90 | budget_only_baseline | 19/30 | $1.73 | 12/30 | 13.00 | zero_cost_placeholder |
| KV90 | budgetflow_task_level | 23/30 | $1.98 | 16/30 | 18.00 | zero_cost_placeholder |
| KV98 | bare_t2_baseline | 18/30 | $0.88 | 11/30 | 12.00 | zero_cost_placeholder |
| KV98 | bare_t3_baseline | 25/30 | $1.66 | 15/30 | 16.50 | zero_cost_placeholder |
| KV98 | routellm_learned_router_baseline | 23/30 | $1.19 | 15/30 | 17.00 | zero_cost_placeholder |
| KV98 | budget_only_baseline | 19/30 | $1.00 | 12/30 | 13.00 | zero_cost_placeholder |
| KV98 | budgetflow_task_level | 23/30 | $1.28 | 16/30 | 18.00 | zero_cost_placeholder |
| KV99 | bare_t2_baseline | 18/30 | $0.79 | 11/30 | 12.00 | zero_cost_placeholder |
| KV99 | bare_t3_baseline | 25/30 | $1.58 | 15/30 | 16.50 | zero_cost_placeholder |
| KV99 | routellm_learned_router_baseline | 23/30 | $1.10 | 15/30 | 17.00 | zero_cost_placeholder |
| KV99 | budget_only_baseline | 19/30 | $0.91 | 12/30 | 13.00 | zero_cost_placeholder |
| KV99 | budgetflow_task_level | 23/30 | $1.19 | 16/30 | 18.00 | zero_cost_placeholder |

### BudgetFlow Tail Upper-Bound

This is an optimistic diagnostic, not a deployable policy: after replaying BudgetFlow's observed rows under each KV profile, it spends any remaining budget on later tasks using observed pure T2/T3 pass outcomes and recosted costs.

| KV Profile | BF Fixed Value | Added Tail Tasks | Added Tail Value | Added Tail Spend | Upper-Bound Value | Upper-Bound Spend | Tail Actions |
|---|---:|---:|---:|---:|---:|---:|---|
| KV0 | 18.00 | 0 | 0.00 | $0.00 | 18.00 | $9.95 | - |
| KV50 | 18.00 | 0 | 0.00 | $0.00 | 18.00 | $5.52 | - |
| KV90 | 18.00 | 0 | 0.00 | $0.00 | 18.00 | $1.98 | - |
| KV98 | 18.00 | 0 | 0.00 | $0.00 | 18.00 | $1.28 | - |
| KV99 | 18.00 | 0 | 0.00 | $0.00 | 18.00 | $1.19 | - |

### Task-Boundary Runtime Implication

- Current evidence still has a task-boundary allocation problem: T2 wins some tasks, so a pure-T3 fallback should be gated by projected full-batch coverage and not replace value-aware allocation under scarcity.
- Comparable paid frontier counts: T2-favorable 6, T3-favorable 5.

## Budget Cap Sensitivity

No-paid replay over the fixed task order: each strategy keeps completed rows until the replay cap is exhausted. Outcomes and Task Value stay fixed.

| Cap | Strategy | Attempted | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---:|---|---:|---:|---:|---:|
| $2.99 | bare_t2_baseline | 6/30 | $2.94 | 5.50 | 1.87 |
| $2.99 | bare_t3_baseline | 9/30 | $2.65 | 7.50 | 2.83 |
| $2.99 | routellm_learned_router_baseline | 9/30 | $2.73 | 7.50 | 2.75 |
| $2.99 | budget_only_baseline | 8/30 | $2.91 | 6.00 | 2.06 |
| $2.99 | budgetflow_task_level | 11/30 | $2.78 | 7.50 | 2.70 |
| $3.98 | bare_t2_baseline | 8/30 | $3.10 | 7.50 | 2.42 |
| $3.98 | bare_t3_baseline | 11/30 | $3.90 | 8.50 | 2.18 |
| $3.98 | routellm_learned_router_baseline | 11/30 | $3.94 | 8.50 | 2.16 |
| $3.98 | budget_only_baseline | 9/30 | $3.27 | 6.00 | 1.84 |
| $3.98 | budgetflow_task_level | 12/30 | $3.04 | 9.00 | 2.96 |
| $4.98 | bare_t2_baseline | 9/30 | $4.17 | 7.50 | 1.80 |
| $4.98 | bare_t3_baseline | 14/30 | $4.72 | 11.00 | 2.33 |
| $4.98 | routellm_learned_router_baseline | 11/30 | $3.94 | 8.50 | 2.16 |
| $4.98 | budget_only_baseline | 11/30 | $4.48 | 7.00 | 1.56 |
| $4.98 | budgetflow_task_level | 14/30 | $4.61 | 10.00 | 2.17 |
| $5.97 | bare_t2_baseline | 11/30 | $5.43 | 8.50 | 1.57 |
| $5.97 | bare_t3_baseline | 16/30 | $5.36 | 12.00 | 2.24 |
| $5.97 | routellm_learned_router_baseline | 15/30 | $5.91 | 11.00 | 1.86 |
| $5.97 | budget_only_baseline | 14/30 | $5.91 | 9.50 | 1.61 |
| $5.97 | budgetflow_task_level | 16/30 | $5.79 | 11.00 | 1.90 |
| $7.47 | bare_t2_baseline | 14/30 | $7.36 | 11.00 | 1.49 |
| $7.47 | bare_t3_baseline | 16/30 | $5.36 | 12.00 | 2.24 |
| $7.47 | routellm_learned_router_baseline | 17/30 | $7.30 | 13.00 | 1.78 |
| $7.47 | budget_only_baseline | 16/30 | $7.36 | 10.50 | 1.43 |
| $7.47 | budgetflow_task_level | 17/30 | $7.46 | 12.00 | 1.61 |
| $9.95 | bare_t2_baseline | 17/30 | $9.94 | 12.00 | 1.21 |
| $9.95 | bare_t3_baseline | 24/30 | $9.56 | 16.50 | 1.73 |
| $9.95 | routellm_learned_router_baseline | 24/30 | $9.95 | 17.00 | 1.71 |
| $9.95 | budget_only_baseline | 18/30 | $8.89 | 13.00 | 1.46 |
| $9.95 | budgetflow_task_level | 22/30 | $9.73 | 17.00 | 1.75 |

## Scoring Evidence

| Strategy | Trusted Pass | Trusted True Fail | No-Patch True Fail | Abort | Suspect |
|---|---:|---:|---:|---:|---:|
| bare_t2_baseline | 11 | 5 | 8 | 0 | 0 |
| bare_t3_baseline | 15 | 10 | 5 | 0 | 0 |
| routellm_learned_router_baseline | 15 | 4 | 10 | 0 | 0 |
| budget_only_baseline | 12 | 6 | 8 | 0 | 0 |
| budgetflow_task_level | 16 | 6 | 8 | 0 | 0 |

Suspect means the row should be inspected before paper use: a pass without trusted harness evidence, or a non-pass row carrying resolved-looking harness evidence.

## Task Order Audit

- Task count: 30.
- Task order source: `paper1/docs/reports/mainline_5x30_claim1_learnedprior_final_budget_plan_20260630.json`.
- High-value tasks (Task Value >= 1.5): 6; early=2, mid=3, late=1.
- On high-value tasks, BudgetFlow resolves 4 tasks / value 6.00; pure T3 resolves 3 tasks / value 4.50.
- Early third: BudgetFlow 6 resolved / value 6.50; pure T3 7 resolved / value 7.50.
- Middle third: BudgetFlow 8 resolved / value 9.50; pure T3 6 resolved / value 7.00.
- Late third: BudgetFlow 2 resolved / value 2.00; pure T3 2 resolved / value 2.00.

## Per-Task Matrix

| # | Task | Value | T2 | T3 | Route | Budget-only | BF |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `django__django-13447` | 1.00 | P 0.18 T2 | P 0.22 T3 | P 0.14 T2 | P 0.23 T3 | P 0.16 T2 |
| 2 | `mwaskom__seaborn-3190` | 1.50 | P 1.04 T2 | P 0.55 T3 | P 0.40 T2 | F 0.29 T3 | P 0.46 T2 |
| 3 | `pallets__flask-4992` | 1.00 | F 0.09 T2 | F 0.13 T3 | F 0.12 T3 | F 0.08 T2 | F 0.17 T3 |
| 4 | `sphinx-doc__sphinx-8595` | 1.00 | P 0.16 T2 | P 0.28 T3 | P 0.20 T2 | P 0.13 T2 | P 0.12 T2 |
| 5 | `pylint-dev__pylint-7993` | 1.00 | P 0.42 T2 | P 0.37 T3 | P 0.76 T2 | P 0.55 T2 | P 0.50 T2 |
| 6 | `sympy__sympy-17655` | 1.00 | P 1.05 T2 | P 0.55 T3 | P 0.45 T2 | P 1.27 T2 | F 0.28 T2 |
| 7 | `django__django-11179` | 1.00 | P 0.09 T2 | P 0.09 T3 | P 0.09 T2 | P 0.25 T2 | P 0.20 T2 |
| 8 | `mwaskom__seaborn-3010` | 1.00 | P 0.06 T2 | P 0.25 T3 | P 0.14 T2 | P 0.11 T2 | P 0.10 T2 |
| 9 | `pallets__flask-4045` | 1.50 | F 1.07 T2 | F 0.23 T3 | F 0.43 T2 | F 0.36 T2 | F 0.37 T2 |
| 10 | `sphinx-doc__sphinx-7738` | 1.00 | F 1.16 T2 | F 1.15 T3 | F 1.08 T2 | F 1.12 T2 | F 0.33 T3 |
| 11 | `django__django-15851` | 1.00 | P 0.10 T2 | P 0.10 T3 | P 0.13 T3 | P 0.09 T2 | P 0.10 T3 |
| 12 | `mwaskom__seaborn-2848` | 1.50 | P 1.66 T2 | P 0.31 T3 | P 1.11 T2 | P 1.04 T2 | P 0.26 T3 |
| 13 | `sympy__sympy-22714` | 1.00 | P 0.16 T2 | P 0.30 T3 | P 0.15 T2 | P 0.21 T2 | P 1.35 T3 |
| 14 | `pylint-dev__pylint-6506` | 1.00 | F 0.11 T2 | F 0.21 T3 | F 0.22 T2 | F 0.19 T2 | F 0.22 T3 |
| 15 | `sphinx-doc__sphinx-7686` | 1.00 | F 1.27 T2 | F 0.48 T3 | F 0.50 T3 | F 1.27 T2 | F 1.05 T3 |
| 16 | `django__django-11049` | 1.00 | P 0.11 T2 | P 0.15 T3 | P 0.24 T3 | P 0.18 T2 | P 0.13 T3 |
| 17 | `sympy__sympy-15346` | 1.00 | F 1.20 T2 | F 2.22 T3 | P 1.14 T3 | P 1.07 T2 | P 1.67 T3 |
| 18 | `mwaskom__seaborn-3407` | 1.50 | F 0.01 T2 | F 0.42 T3 | P 0.45 T2 | P 0.45 T2 | P 0.98 T2 |
| 19 | `django__django-15814` | 1.00 | F 0.00 - | P 0.18 T3 | F 1.57 T2 | F 1.07 T2 | P 0.15 T3 |
| 20 | `sympy__sympy-13647` | 1.50 | F 0.00 - | P 0.15 T3 | P 0.15 T2 | F 0.00 - | P 0.15 T3 |
| 21 | `sphinx-doc__sphinx-8801` | 1.00 | F 0.00 - | P 0.46 T3 | P 0.46 T3 | F 0.00 - | P 0.75 T3 |
| 22 | `sympy__sympy-12171` | 1.00 | F 0.00 - | F 0.12 T3 | F 0.01 T3 | F 0.00 - | F 0.23 T3 |
| 23 | `django__django-12908` | 1.00 | F 0.00 - | P 0.12 T3 | F 0.01 T2 | F 0.00 - | P 0.22 T3 |
| 24 | `sphinx-doc__sphinx-8282` | 1.00 | F 0.00 - | F 0.53 T3 | F 0.00 - | F 0.00 - | F 0.00 - |
| 25 | `sympy__sympy-24102` | 1.00 | - | F 0.39 T3 | F 0.00 T2 | F 0.00 - | F 0.00 - |
| 26 | `django__django-13964` | 1.00 | - | F 0.00 - | F 0.00 - | F 0.00 - | F 0.00 - |
| 27 | `sphinx-doc__sphinx-7975` | 1.00 | - | F 0.00 - | F 0.00 - | - | F 0.00 - |
| 28 | `sympy__sympy-18621` | 1.00 | - | F 0.00 - | F 0.00 - | - | F 0.00 - |
| 29 | `sympy__sympy-13177` | 1.50 | - | F 0.00 - | F 0.00 - | - | F 0.00 T2 |
| 30 | `sphinx-doc__sphinx-8273` | 1.00 | - | F 0.00 - | - | - | F 0.00 - |

Cell format: `P/F/A cost first-tier`.

## Routing And Spin Diagnostics

| Strategy | Rows | T3 Start | T3 Start Pass | T3 Start True Fail | T3 Start Abort | T3 Start Other | All-T2 Rows | All-T2 Turns | Extra All-T2 Turns vs Pure T3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | 24 | 0 | 0 | 0 | 0 | 0 | 18 | 590 | 427.0 |
| bare_t3_baseline | 30 | 25 | 15 | 10 | 0 | 0 | 0 | 0 | 0.0 |
| routellm_learned_router_baseline | 29 | 7 | 4 | 3 | 0 | 0 | 17 | 485 | 352.0 |
| budget_only_baseline | 26 | 2 | 1 | 1 | 0 | 0 | 17 | 596 | 444.0 |
| budgetflow_task_level | 30 | 14 | 9 | 5 | 0 | 0 | 10 | 269 | 195.0 |

- BudgetFlow T3-start rows: 14; resolved 9; true-fail 5; abort 0.
- BudgetFlow all-T2 rows on tasks with pure T3 rows: 10; turns 269 vs pure T3 74.

## BudgetFlow vs Pure T3 Diffs

- Both pass: 14 tasks.
- BudgetFlow-only pass: 2 tasks, value 2.50.
- Pure-T3-only pass: 1 tasks, value 1.00.
- Neither pass: 13 tasks.
- BudgetFlow-only tasks: `sympy__sympy-15346`(1.00), `mwaskom__seaborn-3407`(1.50)
- Pure-T3-only tasks: `sympy__sympy-17655`(1.00)


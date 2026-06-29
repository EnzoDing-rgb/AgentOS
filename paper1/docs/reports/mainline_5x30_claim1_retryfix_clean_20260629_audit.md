# Mainline 5x30 Claim 1 Retryfix Clean Audit

This is a no-paid audit of completed JSONL rows. It does not re-score patches or edit historical artifacts.

## Strategy Summary

| Strategy | Lane State | Rows | Scoreable | Abort | Resolved | Rate (planned) | Rate (scoreable) | Spend | Cost / Resolved | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | budget_exhausted | 24/30 | 24/30 | 0 | 11/30 | 36.7% | 45.8% | $9.95 | $0.90 | 12.00 | 1.21 |
| bare_t3_baseline | complete | 30/30 | 30/30 | 0 | 17/30 | 56.7% | 56.7% | $9.95 | $0.59 | 20.00 | 2.01 |
| routellm_learned_router_baseline | budget_exhausted | 26/30 | 26/30 | 0 | 14/30 | 46.7% | 53.8% | $9.95 | $0.71 | 17.00 | 1.71 |
| budget_only_baseline | budget_exhausted | 24/30 | 24/30 | 0 | 11/30 | 36.7% | 45.8% | $9.95 | $0.90 | 12.00 | 1.21 |
| budgetflow_task_level | complete | 30/30 | 30/30 | 0 | 15/30 | 50.0% | 50.0% | $9.95 | $0.66 | 17.50 | 1.76 |

## Execution Coverage

This separates planned tasks from tasks that actually consumed model budget. Zero-cost rows are usually budget-exhaustion placeholders, not failed model attempts.

| Strategy | Planned | Rows Written | Paid Attempts | Zero-Cost Rows | Missing Rows | Paid Resolved | Total Resolved | Spend |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | 30 | 24 | 17 | 7 | 6 | 11 | 11 | $9.95 |
| bare_t3_baseline | 30 | 30 | 30 | 0 | 0 | 17 | 17 | $9.95 |
| routellm_learned_router_baseline | 30 | 26 | 21 | 5 | 4 | 14 | 14 | $9.95 |
| budget_only_baseline | 30 | 24 | 19 | 5 | 6 | 11 | 11 | $9.95 |
| budgetflow_task_level | 30 | 30 | 25 | 5 | 0 | 15 | 15 | $9.95 |

## Value Sensitivity

Same resolved/not-resolved rows and same spend, rescored under alternate frozen Task Value profiles.

| Value Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|
| equal | bare_t2_baseline | 11/30 | $9.95 | 11.00 | 1.11 |
| equal | bare_t3_baseline | 17/30 | $9.95 | 17.00 | 1.71 |
| equal | routellm_learned_router_baseline | 14/30 | $9.95 | 14.00 | 1.41 |
| equal | budget_only_baseline | 11/30 | $9.95 | 11.00 | 1.11 |
| equal | budgetflow_task_level | 15/30 | $9.95 | 15.00 | 1.51 |
| criticality_value | bare_t2_baseline | 11/30 | $9.95 | 12.00 | 1.21 |
| criticality_value | bare_t3_baseline | 17/30 | $9.95 | 20.00 | 2.01 |
| criticality_value | routellm_learned_router_baseline | 14/30 | $9.95 | 17.00 | 1.71 |
| criticality_value | budget_only_baseline | 11/30 | $9.95 | 12.00 | 1.21 |
| criticality_value | budgetflow_task_level | 15/30 | $9.95 | 17.50 | 1.76 |
| compressed_criticality | bare_t2_baseline | 11/30 | $9.95 | 11.50 | 1.16 |
| compressed_criticality | bare_t3_baseline | 17/30 | $9.95 | 18.25 | 1.83 |
| compressed_criticality | routellm_learned_router_baseline | 14/30 | $9.95 | 15.25 | 1.53 |
| compressed_criticality | budget_only_baseline | 11/30 | $9.95 | 11.50 | 1.16 |
| compressed_criticality | budgetflow_task_level | 15/30 | $9.95 | 16.00 | 1.61 |
| expanded_criticality | bare_t2_baseline | 11/30 | $9.95 | 13.00 | 1.31 |
| expanded_criticality | bare_t3_baseline | 17/30 | $9.95 | 24.00 | 2.41 |
| expanded_criticality | routellm_learned_router_baseline | 14/30 | $9.95 | 21.00 | 2.11 |
| expanded_criticality | budget_only_baseline | 11/30 | $9.95 | 13.00 | 1.31 |
| expanded_criticality | budgetflow_task_level | 15/30 | $9.95 | 21.00 | 2.11 |

### BudgetFlow Margin Under Value Sensitivity

| Value Profile | Best Control By Value | BudgetFlow Value Delta | Best Control By Value/$ | BudgetFlow Value/$ Delta |
|---|---|---:|---|---:|
| equal | bare_t3_baseline | -2.00 | bare_t3_baseline | -0.20 |
| criticality_value | bare_t3_baseline | -2.50 | bare_t3_baseline | -0.25 |
| compressed_criticality | bare_t3_baseline | -2.25 | bare_t3_baseline | -0.23 |
| expanded_criticality | bare_t3_baseline | -3.00 | bare_t3_baseline | -0.30 |

### Value Permutation Diagnostic

This shuffles the same criticality-value multiset across the fixed task list. It is a diagnostic for value-placement dependence, not a replacement for the frozen main ValueSource.

| Samples | BudgetFlow Wins | Min Margin | P25 | Median | P75 | Max Margin |
|---:|---:|---:|---:|---:|---:|---:|
| 64 | 1/64 | -5.50 | -3.50 | -3.00 | -2.50 | +1.00 |

## Static Observed-Tier Oracle

- Skipped: complete pure T2 and pure T3 rows are required for all tasks.

## Task-Level Frontier Diagnostic

Pure T2 vs pure T3 counterfactuals on tasks where both tiers actually consumed model budget. This answers whether the batch contains a real T2-can-win frontier, rather than treating cheaper per-token pricing as enough.

- Comparable paid T2/T3 tasks: 17/30; skipped for missing or zero-cost tier row: 13.

| Frontier Bucket | Tasks | Total Value | Avg T2 Cost | Avg T3 Cost | Avg T2 Turns | Avg T3 Turns | Examples |
|---|---:|---:|---:|---:|---:|---:|---|
| T2 cheaper pass | 4 | 4.00 | $0.19 | $0.23 | 20.8 | 6.8 | `sphinx-doc__sphinx-8595`, `mwaskom__seaborn-3010`, `django__django-15851`, `django__django-11049` |
| T3 cheaper pass | 5 | 5.50 | $0.51 | $0.19 | 31.2 | 6.0 | `django__django-13447`, `pylint-dev__pylint-7993`, `django__django-11179`, `mwaskom__seaborn-2848` |
| T2-only pass | 2 | 2.50 | $0.79 | $0.31 | 49.5 | 7.5 | `mwaskom__seaborn-3190`, `sympy__sympy-17655` |
| T3-only pass | 0 | 0.00 | $0.00 | $0.00 | 0.0 | 0.0 | - |
| both fail | 6 | 10.50 | $0.85 | $0.54 | 39.7 | 9.2 | `pallets__flask-4992`, `pallets__flask-4045`, `sphinx-doc__sphinx-7738`, `pylint-dev__pylint-6506` |

- Interpretation: T2 has 6 task-level opportunities and T3 has 5; BudgetFlow can win only if it captures the T2 opportunities without missing T3-only or T3-cheaper passes.

## Runtime CostSource Audit

- Runtime catalog paths: `/root/.dev/AgentOS/paper1/docs/config/model_tiers.default.json` (134 rows).
- Runtime turn-cache policy observed on paid turns: input_kv_cache_discount=0.0, after_turn=1, min_input_cost_fraction=1.0 (2459 turns).
- Runtime charged input fractions observed on paid turns: 1.0 (2459 turns).
- Interpretation: this run used runtime KV-cache discount 0.0; KV sensitivity below is no-paid recosting, not the executed runtime policy.

## KV Cache Sensitivity

No-paid CostSource sensitivity: outcomes stay fixed while repeated input-token cost is recomputed for T2/T3 turns. This does not simulate additional tasks becoming runnable under a cheaper runtime.

| KV Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|
| KV0 | bare_t2_baseline | 11/30 | $9.95 | 12.00 | 1.21 |
| KV0 | bare_t3_baseline | 17/30 | $9.95 | 20.00 | 2.01 |
| KV0 | routellm_learned_router_baseline | 14/30 | $9.95 | 17.00 | 1.71 |
| KV0 | budget_only_baseline | 11/30 | $9.95 | 12.00 | 1.21 |
| KV0 | budgetflow_task_level | 15/30 | $9.95 | 17.50 | 1.76 |
| KV50 | bare_t2_baseline | 11/30 | $5.27 | 12.00 | 2.28 |
| KV50 | bare_t3_baseline | 17/30 | $5.85 | 20.00 | 3.42 |
| KV50 | routellm_learned_router_baseline | 14/30 | $5.40 | 17.00 | 3.15 |
| KV50 | budget_only_baseline | 11/30 | $5.22 | 12.00 | 2.30 |
| KV50 | budgetflow_task_level | 15/30 | $5.42 | 17.50 | 3.23 |
| KV90 | bare_t2_baseline | 11/30 | $1.88 | 12.00 | 6.39 |
| KV90 | bare_t3_baseline | 17/30 | $2.55 | 20.00 | 7.83 |
| KV90 | routellm_learned_router_baseline | 14/30 | $1.94 | 17.00 | 8.78 |
| KV90 | budget_only_baseline | 11/30 | $1.87 | 12.00 | 6.42 |
| KV90 | budgetflow_task_level | 15/30 | $2.08 | 17.50 | 8.41 |
| KV98 | bare_t2_baseline | 11/30 | $1.20 | 12.00 | 10.00 |
| KV98 | bare_t3_baseline | 17/30 | $1.90 | 20.00 | 10.55 |
| KV98 | routellm_learned_router_baseline | 14/30 | $1.24 | 17.00 | 13.68 |
| KV98 | budget_only_baseline | 11/30 | $1.20 | 12.00 | 10.02 |
| KV98 | budgetflow_task_level | 15/30 | $1.41 | 17.50 | 12.39 |
| KV99 | bare_t2_baseline | 11/30 | $1.11 | 12.00 | 10.77 |
| KV99 | bare_t3_baseline | 17/30 | $1.81 | 20.00 | 11.03 |
| KV99 | routellm_learned_router_baseline | 14/30 | $1.16 | 17.00 | 14.70 |
| KV99 | budget_only_baseline | 11/30 | $1.11 | 12.00 | 10.77 |
| KV99 | budgetflow_task_level | 15/30 | $1.33 | 17.50 | 13.16 |

### BudgetFlow Margin Under KV Sensitivity

| KV Profile | Best Control By Value/$ | BudgetFlow Value/$ Delta | BudgetFlow vs Pure T3 Value/$ Delta |
|---|---|---:|---:|
| KV0 | bare_t3_baseline | -0.25 | -0.25 |
| KV50 | bare_t3_baseline | -0.19 | -0.19 |
| KV90 | routellm_learned_router_baseline | -0.37 | +0.58 |
| KV98 | routellm_learned_router_baseline | -1.29 | +1.83 |
| KV99 | routellm_learned_router_baseline | -1.54 | +2.13 |

## Dynamic KV Replay

No-paid sequential replay under cheaper KV profiles. The fixed-policy table replays each policy's observed task order and observed outcomes with recosted rows; it does not invent outcomes for tasks that never ran. The BudgetFlow tail upper-bound then asks how much extra value could be recovered if cheaper KV let the already-observed BudgetFlow lane reach later tasks and we fill those later tasks with pure T2/T3 observed counterfactuals.

- Shared hard budget: $9.9544.

### Fixed-Policy Replay

| KV Profile | Strategy | Covered Rows | Spend | Resolved | Total Resolved Value | Stop Reason |
|---|---|---:|---:|---:|---:|---|
| KV0 | bare_t2_baseline | 17/30 | $9.95 | 11/30 | 12.00 | zero_cost_placeholder |
| KV0 | bare_t3_baseline | 30/30 | $9.95 | 17/30 | 20.00 | completed_observed_order |
| KV0 | routellm_learned_router_baseline | 20/30 | $9.95 | 14/30 | 17.00 | zero_cost_placeholder |
| KV0 | budget_only_baseline | 19/30 | $9.95 | 11/30 | 12.00 | zero_cost_placeholder |
| KV0 | budgetflow_task_level | 25/30 | $9.95 | 15/30 | 17.50 | zero_cost_placeholder |
| KV50 | bare_t2_baseline | 17/30 | $5.27 | 11/30 | 12.00 | zero_cost_placeholder |
| KV50 | bare_t3_baseline | 30/30 | $5.85 | 17/30 | 20.00 | completed_observed_order |
| KV50 | routellm_learned_router_baseline | 20/30 | $5.40 | 14/30 | 17.00 | zero_cost_placeholder |
| KV50 | budget_only_baseline | 19/30 | $5.22 | 11/30 | 12.00 | zero_cost_placeholder |
| KV50 | budgetflow_task_level | 25/30 | $5.42 | 15/30 | 17.50 | zero_cost_placeholder |
| KV90 | bare_t2_baseline | 17/30 | $1.88 | 11/30 | 12.00 | zero_cost_placeholder |
| KV90 | bare_t3_baseline | 30/30 | $2.55 | 17/30 | 20.00 | completed_observed_order |
| KV90 | routellm_learned_router_baseline | 20/30 | $1.93 | 14/30 | 17.00 | zero_cost_placeholder |
| KV90 | budget_only_baseline | 19/30 | $1.87 | 11/30 | 12.00 | zero_cost_placeholder |
| KV90 | budgetflow_task_level | 25/30 | $2.08 | 15/30 | 17.50 | zero_cost_placeholder |
| KV98 | bare_t2_baseline | 17/30 | $1.20 | 11/30 | 12.00 | zero_cost_placeholder |
| KV98 | bare_t3_baseline | 30/30 | $1.90 | 17/30 | 20.00 | completed_observed_order |
| KV98 | routellm_learned_router_baseline | 20/30 | $1.24 | 14/30 | 17.00 | zero_cost_placeholder |
| KV98 | budget_only_baseline | 19/30 | $1.20 | 11/30 | 12.00 | zero_cost_placeholder |
| KV98 | budgetflow_task_level | 25/30 | $1.41 | 15/30 | 17.50 | zero_cost_placeholder |
| KV99 | bare_t2_baseline | 17/30 | $1.11 | 11/30 | 12.00 | zero_cost_placeholder |
| KV99 | bare_t3_baseline | 30/30 | $1.81 | 17/30 | 20.00 | completed_observed_order |
| KV99 | routellm_learned_router_baseline | 20/30 | $1.15 | 14/30 | 17.00 | zero_cost_placeholder |
| KV99 | budget_only_baseline | 19/30 | $1.11 | 11/30 | 12.00 | zero_cost_placeholder |
| KV99 | budgetflow_task_level | 25/30 | $1.33 | 15/30 | 17.50 | zero_cost_placeholder |

### BudgetFlow Tail Upper-Bound

This is an optimistic diagnostic, not a deployable policy: after replaying BudgetFlow's observed rows under each KV profile, it spends any remaining budget on later tasks using observed pure T2/T3 pass outcomes and recosted costs.

| KV Profile | BF Fixed Value | Added Tail Tasks | Added Tail Value | Added Tail Spend | Upper-Bound Value | Upper-Bound Spend | Tail Actions |
|---|---:|---:|---:|---:|---:|---:|---|
| KV0 | 17.50 | 0 | 0.00 | $0.00 | 17.50 | $9.95 | - |
| KV50 | 17.50 | 3 | 3.00 | $0.72 | 20.50 | $6.14 | `django__django-13964` T3 $0.19, `sphinx-doc__sphinx-7975` T3 $0.38, `sympy__sympy-18621` T3 $0.15 |
| KV90 | 17.50 | 3 | 3.00 | $0.31 | 20.50 | $2.39 | `django__django-13964` T3 $0.08, `sphinx-doc__sphinx-7975` T3 $0.16, `sympy__sympy-18621` T3 $0.07 |
| KV98 | 17.50 | 3 | 3.00 | $0.23 | 20.50 | $1.64 | `django__django-13964` T3 $0.06, `sphinx-doc__sphinx-7975` T3 $0.12, `sympy__sympy-18621` T3 $0.05 |
| KV99 | 17.50 | 3 | 3.00 | $0.22 | 20.50 | $1.55 | `django__django-13964` T3 $0.06, `sphinx-doc__sphinx-7975` T3 $0.11, `sympy__sympy-18621` T3 $0.05 |

### Task-Boundary Runtime Implication

- Current evidence supports a compiler-level strongest-frontier fallback: when projected pure T3 can cover the remaining batch inside the shared cap, BudgetFlow should be allowed to choose the T3 frontier instead of forcing T2 savings. In this run, pure T3 covered the full batch under the cap and beat BudgetFlow on Total Resolved Value.
- Comparable paid frontier counts: T2-favorable 6, T3-favorable 5.

## Budget Cap Sensitivity

No-paid replay over the fixed task order: each strategy keeps completed rows until the replay cap is exhausted. Outcomes and Task Value stay fixed.

| Cap | Strategy | Attempted | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---:|---|---:|---:|---:|---:|
| $2.99 | bare_t2_baseline | 5/30 | $2.51 | 4.50 | 1.79 |
| $2.99 | bare_t3_baseline | 9/30 | $1.89 | 5.00 | 2.64 |
| $2.99 | routellm_learned_router_baseline | 6/30 | $2.94 | 8.00 | 2.72 |
| $2.99 | budget_only_baseline | 8/30 | $2.40 | 7.50 | 3.13 |
| $2.99 | budgetflow_task_level | 7/30 | $2.94 | 5.00 | 1.70 |
| $3.98 | bare_t2_baseline | 8/30 | $3.73 | 7.50 | 2.01 |
| $3.98 | bare_t3_baseline | 12/30 | $3.75 | 7.50 | 2.00 |
| $3.98 | routellm_learned_router_baseline | 9/30 | $3.86 | 10.00 | 2.59 |
| $3.98 | budget_only_baseline | 9/30 | $3.02 | 7.50 | 2.48 |
| $3.98 | budgetflow_task_level | 9/30 | $3.36 | 6.00 | 1.79 |
| $4.98 | bare_t2_baseline | 9/30 | $4.05 | 7.50 | 1.85 |
| $4.98 | bare_t3_baseline | 16/30 | $4.85 | 9.50 | 1.96 |
| $4.98 | routellm_learned_router_baseline | 11/30 | $4.75 | 12.00 | 2.53 |
| $4.98 | budget_only_baseline | 11/30 | $4.54 | 8.50 | 1.87 |
| $4.98 | budgetflow_task_level | 12/30 | $4.70 | 8.50 | 1.81 |
| $5.97 | bare_t2_baseline | 12/30 | $5.93 | 10.00 | 1.69 |
| $5.97 | bare_t3_baseline | 17/30 | $5.75 | 9.50 | 1.65 |
| $5.97 | routellm_learned_router_baseline | 11/30 | $4.75 | 12.00 | 2.53 |
| $5.97 | budget_only_baseline | 12/30 | $5.72 | 10.00 | 1.75 |
| $5.97 | budgetflow_task_level | 15/30 | $5.88 | 9.50 | 1.61 |
| $7.47 | bare_t2_baseline | 14/30 | $7.07 | 11.00 | 1.56 |
| $7.47 | bare_t3_baseline | 23/30 | $7.42 | 17.00 | 2.29 |
| $7.47 | routellm_learned_router_baseline | 15/30 | $7.22 | 14.50 | 2.01 |
| $7.47 | budget_only_baseline | 14/30 | $6.66 | 11.00 | 1.65 |
| $7.47 | budgetflow_task_level | 18/30 | $7.16 | 11.50 | 1.61 |
| $9.95 | bare_t2_baseline | 16/30 | $9.14 | 12.00 | 1.31 |
| $9.95 | bare_t3_baseline | 29/30 | $9.76 | 20.00 | 2.05 |
| $9.95 | routellm_learned_router_baseline | 19/30 | $9.95 | 17.00 | 1.71 |
| $9.95 | budget_only_baseline | 18/30 | $9.95 | 12.00 | 1.21 |
| $9.95 | budgetflow_task_level | 24/30 | $9.91 | 17.50 | 1.77 |

## Scoring Evidence

| Strategy | Trusted Pass | Trusted True Fail | No-Patch True Fail | Abort | Suspect |
|---|---:|---:|---:|---:|---:|
| bare_t2_baseline | 11 | 5 | 8 | 0 | 0 |
| bare_t3_baseline | 17 | 13 | 0 | 0 | 0 |
| routellm_learned_router_baseline | 14 | 4 | 8 | 0 | 0 |
| budget_only_baseline | 11 | 4 | 9 | 0 | 0 |
| budgetflow_task_level | 15 | 8 | 7 | 0 | 0 |

Suspect means the row should be inspected before paper use: a pass without trusted harness evidence, or a non-pass row carrying resolved-looking harness evidence.

## Task Order Audit

- Task count: 30.
- Task order source: `bare_t3_baseline`.
- High-value tasks (Task Value >= 1.5): 10; early=3, mid=4, late=3.
- On high-value tasks, BudgetFlow resolves 3 tasks / value 5.50; pure T3 resolves 4 tasks / value 7.00.
- Early third: BudgetFlow 6 resolved / value 6.00; pure T3 5 resolved / value 5.00.
- Middle third: BudgetFlow 7 resolved / value 8.00; pure T3 7 resolved / value 8.50.
- Late third: BudgetFlow 2 resolved / value 3.50; pure T3 5 resolved / value 6.50.

## Per-Task Matrix

| # | Task | Value | T2 | T3 | Route | Budget-only | BF |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `django__django-13447` | 1.00 | P 0.29 T2 | P 0.19 T3 | P 0.14 T2 | P 0.14 T3 | P 0.36 T2 |
| 2 | `mwaskom__seaborn-3190` | 1.50 | P 0.65 T2 | F 0.24 T3 | P 1.13 T2 | P 0.17 T3 | F 0.26 T3 |
| 3 | `pallets__flask-4992` | 2.50 | F 0.09 T2 | F 0.19 T3 | P 0.20 T3 | F 0.25 T3 | F 0.23 T3 |
| 4 | `sphinx-doc__sphinx-8595` | 1.00 | P 0.22 T2 | P 0.24 T3 | P 0.13 T2 | P 0.12 T2 | P 0.25 T2 |
| 5 | `pylint-dev__pylint-7993` | 1.00 | P 1.26 T2 | P 0.13 T3 | P 0.69 T2 | P 0.87 T2 | P 0.81 T2 |
| 6 | `sympy__sympy-17655` | 1.00 | P 0.94 T2 | F 0.37 T3 | P 0.65 T2 | P 0.65 T2 | P 0.98 T2 |
| 7 | `django__django-11179` | 1.00 | P 0.10 T2 | P 0.09 T3 | P 0.19 T2 | P 0.11 T2 | P 0.06 T2 |
| 8 | `mwaskom__seaborn-3010` | 1.00 | P 0.18 T2 | P 0.19 T3 | P 0.10 T2 | P 0.08 T2 | P 0.09 T2 |
| 9 | `pallets__flask-4045` | 2.50 | F 0.32 T2 | F 0.25 T3 | F 0.62 T2 | F 0.63 T2 | F 0.33 T3 |
| 10 | `sphinx-doc__sphinx-7738` | 1.00 | F 1.16 T2 | F 1.43 T3 | P 0.79 T2 | F 1.45 T2 | F 1.01 T2 |
| 11 | `django__django-15851` | 1.00 | P 0.12 T2 | P 0.14 T3 | P 0.10 T3 | P 0.07 T2 | P 0.06 T2 |
| 12 | `mwaskom__seaborn-2848` | 1.50 | P 0.61 T2 | P 0.29 T3 | P 1.47 T2 | P 1.19 T2 | P 0.26 T3 |
| 13 | `sympy__sympy-22714` | 1.00 | P 0.28 T2 | P 0.27 T3 | P 0.16 T2 | P 0.35 T2 | P 0.33 T2 |
| 14 | `pylint-dev__pylint-6506` | 1.00 | F 0.86 T2 | F 0.23 T3 | F 0.33 T2 | F 0.58 T2 | F 0.50 T2 |
| 15 | `sphinx-doc__sphinx-7686` | 2.50 | F 1.84 T2 | F 0.24 T3 | F 0.53 T3 | F 1.78 T2 | F 0.36 T3 |
| 16 | `django__django-11049` | 1.00 | P 0.23 T2 | P 0.35 T3 | P 0.27 T3 | P 0.18 T2 | P 0.21 T2 |
| 17 | `sympy__sympy-15346` | 1.00 | F 0.82 T2 | F 0.90 T3 | F 1.63 T3 | F 1.32 T2 | P 0.85 T2 |
| 18 | `mwaskom__seaborn-3407` | 1.50 | F 0.00 - | P 0.39 T3 | P 0.47 T2 | F 0.02 T2 | F 0.21 T3 |
| 19 | `django__django-15814` | 1.00 | F 0.00 - | P 0.34 T3 | F 0.36 T2 | F 0.00 T2 | P 1.28 T2 |
| 20 | `sympy__sympy-13647` | 1.50 | F 0.00 - | P 0.18 T3 | F 0.00 T2 | F 0.00 - | P 0.21 T3 |
| 21 | `sphinx-doc__sphinx-8801` | 2.50 | F 0.00 - | P 0.27 T3 | F 0.00 - | F 0.00 - | P 0.41 T3 |
| 22 | `sympy__sympy-12171` | 1.00 | F 0.00 - | F 0.24 T3 | F 0.00 - | F 0.00 - | F 0.37 T2 |
| 23 | `django__django-12908` | 1.00 | F 0.00 - | P 0.25 T3 | F 0.00 T2 | F 0.00 - | P 0.18 T2 |
| 24 | `sphinx-doc__sphinx-8282` | 2.50 | F 0.00 - | F 0.56 T3 | F 0.00 - | F 0.00 - | F 0.30 T3 |
| 25 | `sympy__sympy-24102` | 1.00 | - | F 0.41 T3 | F 0.00 - | - | F 0.04 T2 |
| 26 | `django__django-13964` | 1.00 | - | P 0.32 T3 | F 0.00 - | - | F 0.00 - |
| 27 | `sphinx-doc__sphinx-7975` | 1.00 | - | P 0.66 T3 | - | - | F 0.00 - |
| 28 | `sympy__sympy-18621` | 1.00 | - | P 0.24 T3 | - | - | F 0.00 - |
| 29 | `sympy__sympy-13177` | 1.50 | - | F 0.14 T3 | - | - | F 0.00 - |
| 30 | `sphinx-doc__sphinx-8273` | 1.00 | - | F 0.19 T3 | - | - | F 0.00 - |

Cell format: `P/F/A cost first-tier`.

## Routing And Spin Diagnostics

| Strategy | Rows | T3 Start | T3 Start Pass | T3 Start True Fail | T3 Start Abort | T3 Start Other | All-T2 Rows | All-T2 Turns | Extra All-T2 Turns vs Pure T3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | 24 | 0 | 0 | 0 | 0 | 0 | 17 | 576 | 449.0 |
| bare_t3_baseline | 30 | 30 | 17 | 13 | 0 | 0 | 0 | 0 | 0.0 |
| routellm_learned_router_baseline | 26 | 5 | 3 | 2 | 0 | 0 | 16 | 433 | 314.0 |
| budget_only_baseline | 24 | 3 | 2 | 1 | 0 | 0 | 16 | 502 | 375.0 |
| budgetflow_task_level | 30 | 9 | 3 | 6 | 0 | 0 | 16 | 480 | 349.0 |

- BudgetFlow T3-start rows: 9; resolved 3; true-fail 6; abort 0.
- BudgetFlow all-T2 rows on tasks with pure T3 rows: 16; turns 480 vs pure T3 131.

## BudgetFlow vs Pure T3 Diffs

- Both pass: 13 tasks.
- BudgetFlow-only pass: 2 tasks, value 2.00.
- Pure-T3-only pass: 4 tasks, value 4.50.
- Neither pass: 11 tasks.
- BudgetFlow-only tasks: `sympy__sympy-17655`(1.00), `sympy__sympy-15346`(1.00)
- Pure-T3-only tasks: `mwaskom__seaborn-3407`(1.50), `django__django-13964`(1.00), `sphinx-doc__sphinx-7975`(1.00), `sympy__sympy-18621`(1.00)


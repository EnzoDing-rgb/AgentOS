# Claim 1 Matrix And Task Order Audit

This is a no-paid audit of completed JSONL rows. It does not re-score patches or edit historical artifacts.

## Strategy Summary

| Strategy | Lane State | Rows | Scoreable | Abort | Resolved | Rate (planned) | Rate (scoreable) | Spend | Cost / Resolved | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | budget_exhausted | 26/30 | 26/30 | 0 | 13/30 | 43.3% | 50.0% | $9.95 | $0.77 | 14.50 | 1.46 |
| bare_t3_baseline | complete | 30/30 | 30/30 | 0 | 17/30 | 56.7% | 56.7% | $9.95 | $0.59 | 18.50 | 1.86 |
| routellm_learned_router_baseline | complete | 30/30 | 30/30 | 0 | 19/30 | 63.3% | 63.3% | $9.95 | $0.52 | 21.00 | 2.11 |
| budget_only_baseline | budget_exhausted | 26/30 | 26/30 | 0 | 13/30 | 43.3% | 50.0% | $9.95 | $0.77 | 14.50 | 1.46 |
| budgetflow_task_level | budget_exhausted | 29/30 | 29/30 | 0 | 14/30 | 46.7% | 48.3% | $9.95 | $0.71 | 15.00 | 1.51 |

## Execution Coverage

This separates planned tasks from tasks that actually consumed model budget. Zero-cost rows are usually budget-exhaustion placeholders, not failed model attempts.

| Strategy | Planned | Rows Written | Paid Attempts | Zero-Cost Rows | Missing Rows | Paid Resolved | Total Resolved | Spend |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | 30 | 26 | 18 | 8 | 4 | 13 | 13 | $9.95 |
| bare_t3_baseline | 30 | 30 | 27 | 3 | 0 | 17 | 17 | $9.95 |
| routellm_learned_router_baseline | 30 | 30 | 23 | 7 | 0 | 19 | 19 | $9.95 |
| budget_only_baseline | 30 | 26 | 18 | 8 | 4 | 13 | 13 | $9.95 |
| budgetflow_task_level | 30 | 29 | 21 | 8 | 1 | 14 | 14 | $9.95 |

## Value Sensitivity

Same resolved/not-resolved rows and same spend, rescored under alternate frozen Task Value profiles.

| Value Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|
| equal | bare_t2_baseline | 13/30 | $9.95 | 13.00 | 1.31 |
| equal | bare_t3_baseline | 17/30 | $9.95 | 17.00 | 1.71 |
| equal | routellm_learned_router_baseline | 19/30 | $9.95 | 19.00 | 1.91 |
| equal | budget_only_baseline | 13/30 | $9.95 | 13.00 | 1.31 |
| equal | budgetflow_task_level | 14/30 | $9.95 | 14.00 | 1.41 |
| criticality_value | bare_t2_baseline | 13/30 | $9.95 | 14.50 | 1.46 |
| criticality_value | bare_t3_baseline | 17/30 | $9.95 | 18.50 | 1.86 |
| criticality_value | routellm_learned_router_baseline | 19/30 | $9.95 | 21.00 | 2.11 |
| criticality_value | budget_only_baseline | 13/30 | $9.95 | 14.50 | 1.46 |
| criticality_value | budgetflow_task_level | 14/30 | $9.95 | 15.00 | 1.51 |
| compressed_criticality | bare_t2_baseline | 13/30 | $9.95 | 13.75 | 1.38 |
| compressed_criticality | bare_t3_baseline | 17/30 | $9.95 | 17.75 | 1.78 |
| compressed_criticality | routellm_learned_router_baseline | 19/30 | $9.95 | 20.00 | 2.01 |
| compressed_criticality | budget_only_baseline | 13/30 | $9.95 | 13.75 | 1.38 |
| compressed_criticality | budgetflow_task_level | 14/30 | $9.95 | 14.50 | 1.46 |
| expanded_criticality | bare_t2_baseline | 13/30 | $9.95 | 16.00 | 1.61 |
| expanded_criticality | bare_t3_baseline | 17/30 | $9.95 | 20.00 | 2.01 |
| expanded_criticality | routellm_learned_router_baseline | 19/30 | $9.95 | 23.00 | 2.31 |
| expanded_criticality | budget_only_baseline | 13/30 | $9.95 | 16.00 | 1.61 |
| expanded_criticality | budgetflow_task_level | 14/30 | $9.95 | 16.00 | 1.61 |

### BudgetFlow Margin Under Value Sensitivity

| Value Profile | Best Control By Value | BudgetFlow Value Delta | Best Control By Value/$ | BudgetFlow Value/$ Delta |
|---|---|---:|---|---:|
| equal | routellm_learned_router_baseline | -5.00 | routellm_learned_router_baseline | -0.50 |
| criticality_value | routellm_learned_router_baseline | -6.00 | routellm_learned_router_baseline | -0.60 |
| compressed_criticality | routellm_learned_router_baseline | -5.50 | routellm_learned_router_baseline | -0.55 |
| expanded_criticality | routellm_learned_router_baseline | -7.00 | routellm_learned_router_baseline | -0.70 |

### Value Permutation Diagnostic

This shuffles the same criticality-value multiset across the fixed task list. It is a diagnostic for value-placement dependence, not a replacement for the frozen main ValueSource.

| Samples | BudgetFlow Wins | Min Margin | P25 | Median | P75 | Max Margin |
|---:|---:|---:|---:|---:|---:|---:|
| 64 | 0/64 | -6.00 | -5.50 | -5.50 | -5.00 | -5.00 |

## Static Observed-Tier Oracle

- Skipped: complete pure T2 and pure T3 rows are required for all tasks.

## Task-Level Frontier Diagnostic

Pure T2 vs pure T3 counterfactuals on tasks where both tiers actually consumed model budget. This answers whether the batch contains a real T2-can-win frontier, rather than treating cheaper per-token pricing as enough.

- Comparable paid T2/T3 tasks: 18/30; skipped for missing or zero-cost tier row: 12.

| Frontier Bucket | Tasks | Total Value | Avg T2 Cost | Avg T3 Cost | Avg T2 Turns | Avg T3 Turns | Examples |
|---|---:|---:|---:|---:|---:|---:|---|
| T2 cheaper pass | 6 | 6.00 | $0.25 | $0.50 | 22.0 | 9.0 | `django__django-13447`, `sphinx-doc__sphinx-8595`, `mwaskom__seaborn-3010`, `sympy__sympy-22714` |
| T3 cheaper pass | 5 | 6.00 | $0.74 | $0.24 | 37.8 | 7.0 | `pylint-dev__pylint-7993`, `django__django-11179`, `django__django-15851`, `mwaskom__seaborn-2848` |
| T2-only pass | 2 | 2.50 | $0.84 | $0.41 | 53.0 | 9.5 | `mwaskom__seaborn-3190`, `sympy__sympy-17655` |
| T3-only pass | 1 | 1.00 | $0.11 | $0.13 | 16.0 | 5.0 | `pallets__flask-4992` |
| both fail | 4 | 4.50 | $0.74 | $0.27 | 42.0 | 7.0 | `pallets__flask-4045`, `sphinx-doc__sphinx-7738`, `pylint-dev__pylint-6506`, `sphinx-doc__sphinx-7686` |

- Interpretation: T2 has 8 task-level opportunities and T3 has 6; BudgetFlow can win only if it captures the T2 opportunities without missing T3-only or T3-cheaper passes.

## Runtime CostSource Audit

- Runtime catalog paths: `/root/.dev/AgentOS/paper1/docs/config/model_tiers.default.json` (141 rows).
- Runtime turn-cache policy observed on paid turns: input_kv_cache_discount=0.0, after_turn=1, min_input_cost_fraction=1.0 (2545 turns).
- Runtime charged input fractions observed on paid turns: 1.0 (2545 turns).
- Interpretation: this run used runtime KV-cache discount 0.0; KV sensitivity below is no-paid recosting, not the executed runtime policy.

## KV Cache Sensitivity

No-paid CostSource sensitivity: outcomes stay fixed while repeated input-token cost is recomputed for T2/T3 turns. This does not simulate additional tasks becoming runnable under a cheaper runtime.

| KV Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|
| KV0 | bare_t2_baseline | 13/30 | $9.95 | 14.50 | 1.46 |
| KV0 | bare_t3_baseline | 17/30 | $9.95 | 18.50 | 1.86 |
| KV0 | routellm_learned_router_baseline | 19/30 | $9.95 | 21.00 | 2.11 |
| KV0 | budget_only_baseline | 13/30 | $9.95 | 14.50 | 1.46 |
| KV0 | budgetflow_task_level | 14/30 | $9.95 | 15.00 | 1.51 |
| KV50 | bare_t2_baseline | 13/30 | $5.31 | 14.50 | 2.73 |
| KV50 | bare_t3_baseline | 17/30 | $5.72 | 18.50 | 3.24 |
| KV50 | routellm_learned_router_baseline | 19/30 | $5.48 | 21.00 | 3.83 |
| KV50 | budget_only_baseline | 13/30 | $5.30 | 14.50 | 2.73 |
| KV50 | budgetflow_task_level | 14/30 | $5.45 | 15.00 | 2.75 |
| KV90 | bare_t2_baseline | 13/30 | $1.61 | 14.50 | 9.02 |
| KV90 | bare_t3_baseline | 17/30 | $2.33 | 18.50 | 7.95 |
| KV90 | routellm_learned_router_baseline | 19/30 | $1.94 | 21.00 | 10.81 |
| KV90 | budget_only_baseline | 13/30 | $1.69 | 14.50 | 8.59 |
| KV90 | budgetflow_task_level | 14/30 | $1.83 | 15.00 | 8.18 |
| KV98 | bare_t2_baseline | 13/30 | $0.87 | 14.50 | 16.71 |
| KV98 | bare_t3_baseline | 17/30 | $1.65 | 18.50 | 11.21 |
| KV98 | routellm_learned_router_baseline | 19/30 | $1.24 | 21.00 | 17.00 |
| KV98 | budget_only_baseline | 13/30 | $0.96 | 14.50 | 15.05 |
| KV98 | budgetflow_task_level | 14/30 | $1.11 | 15.00 | 13.49 |
| KV99 | bare_t2_baseline | 13/30 | $0.78 | 14.50 | 18.71 |
| KV99 | bare_t3_baseline | 17/30 | $1.57 | 18.50 | 11.82 |
| KV99 | routellm_learned_router_baseline | 19/30 | $1.15 | 21.00 | 18.32 |
| KV99 | budget_only_baseline | 13/30 | $0.87 | 14.50 | 16.60 |
| KV99 | budgetflow_task_level | 14/30 | $1.02 | 15.00 | 14.69 |

### BudgetFlow Margin Under KV Sensitivity

| KV Profile | Best Control By Value/$ | BudgetFlow Value/$ Delta | BudgetFlow vs Pure T3 Value/$ Delta |
|---|---|---:|---:|
| KV0 | routellm_learned_router_baseline | -0.60 | -0.35 |
| KV50 | routellm_learned_router_baseline | -1.08 | -0.48 |
| KV90 | routellm_learned_router_baseline | -2.63 | +0.23 |
| KV98 | routellm_learned_router_baseline | -3.51 | +2.28 |
| KV99 | bare_t2_baseline | -4.02 | +2.87 |

## Dynamic KV Replay

No-paid sequential replay under cheaper KV profiles. The fixed-policy table replays each policy's observed task order and observed outcomes with recosted rows; it does not invent outcomes for tasks that never ran. The BudgetFlow tail upper-bound then asks how much extra value could be recovered if cheaper KV let the already-observed BudgetFlow lane reach later tasks and we fill those later tasks with pure T2/T3 observed counterfactuals.

- Shared hard budget: $9.9544.

### Fixed-Policy Replay

| KV Profile | Strategy | Covered Rows | Spend | Resolved | Total Resolved Value | Stop Reason |
|---|---|---:|---:|---:|---:|---|
| KV0 | bare_t2_baseline | 18/30 | $9.95 | 13/30 | 14.50 | zero_cost_placeholder |
| KV0 | bare_t3_baseline | 27/30 | $9.95 | 17/30 | 18.50 | zero_cost_placeholder |
| KV0 | routellm_learned_router_baseline | 23/30 | $9.95 | 19/30 | 21.00 | zero_cost_placeholder |
| KV0 | budget_only_baseline | 18/30 | $9.95 | 13/30 | 14.50 | zero_cost_placeholder |
| KV0 | budgetflow_task_level | 21/30 | $9.95 | 14/30 | 15.00 | zero_cost_placeholder |
| KV50 | bare_t2_baseline | 18/30 | $5.31 | 13/30 | 14.50 | zero_cost_placeholder |
| KV50 | bare_t3_baseline | 27/30 | $5.72 | 17/30 | 18.50 | zero_cost_placeholder |
| KV50 | routellm_learned_router_baseline | 23/30 | $5.48 | 19/30 | 21.00 | zero_cost_placeholder |
| KV50 | budget_only_baseline | 18/30 | $5.30 | 13/30 | 14.50 | zero_cost_placeholder |
| KV50 | budgetflow_task_level | 21/30 | $5.45 | 14/30 | 15.00 | zero_cost_placeholder |
| KV90 | bare_t2_baseline | 18/30 | $1.61 | 13/30 | 14.50 | zero_cost_placeholder |
| KV90 | bare_t3_baseline | 27/30 | $2.33 | 17/30 | 18.50 | zero_cost_placeholder |
| KV90 | routellm_learned_router_baseline | 23/30 | $1.94 | 19/30 | 21.00 | zero_cost_placeholder |
| KV90 | budget_only_baseline | 18/30 | $1.69 | 13/30 | 14.50 | zero_cost_placeholder |
| KV90 | budgetflow_task_level | 21/30 | $1.83 | 14/30 | 15.00 | zero_cost_placeholder |
| KV98 | bare_t2_baseline | 18/30 | $0.87 | 13/30 | 14.50 | zero_cost_placeholder |
| KV98 | bare_t3_baseline | 27/30 | $1.65 | 17/30 | 18.50 | zero_cost_placeholder |
| KV98 | routellm_learned_router_baseline | 23/30 | $1.24 | 19/30 | 21.00 | zero_cost_placeholder |
| KV98 | budget_only_baseline | 18/30 | $0.96 | 13/30 | 14.50 | zero_cost_placeholder |
| KV98 | budgetflow_task_level | 21/30 | $1.11 | 14/30 | 15.00 | zero_cost_placeholder |
| KV99 | bare_t2_baseline | 18/30 | $0.78 | 13/30 | 14.50 | zero_cost_placeholder |
| KV99 | bare_t3_baseline | 27/30 | $1.57 | 17/30 | 18.50 | zero_cost_placeholder |
| KV99 | routellm_learned_router_baseline | 23/30 | $1.15 | 19/30 | 21.00 | zero_cost_placeholder |
| KV99 | budget_only_baseline | 18/30 | $0.87 | 13/30 | 14.50 | zero_cost_placeholder |
| KV99 | budgetflow_task_level | 21/30 | $1.02 | 14/30 | 15.00 | zero_cost_placeholder |

### BudgetFlow Tail Upper-Bound

This is an optimistic diagnostic, not a deployable policy: after replaying BudgetFlow's observed rows under each KV profile, it spends any remaining budget on later tasks using observed pure T2/T3 pass outcomes and recosted costs.

| KV Profile | BF Fixed Value | Added Tail Tasks | Added Tail Value | Added Tail Spend | Upper-Bound Value | Upper-Bound Spend | Tail Actions |
|---|---:|---:|---:|---:|---:|---:|---|
| KV0 | 15.00 | 0 | 0.00 | $0.00 | 15.00 | $9.95 | - |
| KV50 | 15.00 | 2 | 2.00 | $0.30 | 17.00 | $5.75 | `django__django-12908` T3 $0.13, `django__django-13964` T3 $0.16 |
| KV90 | 15.00 | 2 | 2.00 | $0.12 | 17.00 | $1.96 | `django__django-12908` T3 $0.06, `django__django-13964` T3 $0.07 |
| KV98 | 15.00 | 2 | 2.00 | $0.09 | 17.00 | $1.20 | `django__django-12908` T3 $0.04, `django__django-13964` T3 $0.05 |
| KV99 | 15.00 | 2 | 2.00 | $0.08 | 17.00 | $1.10 | `django__django-12908` T3 $0.04, `django__django-13964` T3 $0.04 |

### Task-Boundary Runtime Implication

- Current evidence still has a task-boundary allocation problem: T2 wins some tasks, so a pure-T3 fallback should be gated by projected full-batch coverage and not replace value-aware allocation under scarcity.
- Comparable paid frontier counts: T2-favorable 8, T3-favorable 6.

## Budget Cap Sensitivity

No-paid replay over the fixed task order: each strategy keeps completed rows until the replay cap is exhausted. Outcomes and Task Value stay fixed.

| Cap | Strategy | Attempted | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---:|---|---:|---:|---:|---:|
| $2.99 | bare_t2_baseline | 6/30 | $2.94 | 5.50 | 1.87 |
| $2.99 | bare_t3_baseline | 11/30 | $2.82 | 7.00 | 2.48 |
| $2.99 | routellm_learned_router_baseline | 9/30 | $2.74 | 7.50 | 2.73 |
| $2.99 | budget_only_baseline | 6/30 | $2.93 | 5.50 | 1.88 |
| $2.99 | budgetflow_task_level | 9/30 | $2.69 | 6.00 | 2.23 |
| $3.98 | bare_t2_baseline | 9/30 | $3.46 | 7.50 | 2.16 |
| $3.98 | bare_t3_baseline | 14/30 | $3.69 | 9.50 | 2.58 |
| $3.98 | routellm_learned_router_baseline | 11/30 | $3.44 | 9.50 | 2.76 |
| $3.98 | budget_only_baseline | 9/30 | $3.85 | 7.50 | 1.95 |
| $3.98 | budgetflow_task_level | 12/30 | $3.97 | 9.50 | 2.39 |
| $4.98 | bare_t2_baseline | 11/30 | $4.68 | 8.50 | 1.82 |
| $4.98 | bare_t3_baseline | 16/30 | $4.23 | 10.50 | 2.48 |
| $4.98 | routellm_learned_router_baseline | 13/30 | $4.76 | 12.00 | 2.52 |
| $4.98 | budget_only_baseline | 11/30 | $4.52 | 9.50 | 2.10 |
| $4.98 | budgetflow_task_level | 14/30 | $4.56 | 10.50 | 2.30 |
| $5.97 | bare_t2_baseline | 11/30 | $4.68 | 8.50 | 1.82 |
| $5.97 | bare_t3_baseline | 16/30 | $4.23 | 10.50 | 2.48 |
| $5.97 | routellm_learned_router_baseline | 14/30 | $5.37 | 12.00 | 2.23 |
| $5.97 | budget_only_baseline | 12/30 | $5.89 | 11.00 | 1.87 |
| $5.97 | budgetflow_task_level | 16/30 | $5.32 | 11.50 | 2.16 |
| $7.47 | bare_t2_baseline | 14/30 | $7.39 | 11.00 | 1.49 |
| $7.47 | bare_t3_baseline | 20/30 | $6.80 | 15.50 | 2.28 |
| $7.47 | routellm_learned_router_baseline | 17/30 | $7.03 | 15.00 | 2.13 |
| $7.47 | budget_only_baseline | 14/30 | $6.57 | 12.00 | 1.83 |
| $7.47 | budgetflow_task_level | 18/30 | $7.00 | 11.50 | 1.64 |
| $9.95 | bare_t2_baseline | 17/30 | $9.62 | 13.00 | 1.35 |
| $9.95 | bare_t3_baseline | 26/30 | $9.59 | 18.50 | 1.93 |
| $9.95 | routellm_learned_router_baseline | 22/30 | $9.82 | 20.00 | 2.04 |
| $9.95 | budget_only_baseline | 17/30 | $9.50 | 13.00 | 1.37 |
| $9.95 | budgetflow_task_level | 20/30 | $8.60 | 14.00 | 1.63 |

## Scoring Evidence

| Strategy | Trusted Pass | Trusted True Fail | No-Patch True Fail | Abort | Suspect |
|---|---:|---:|---:|---:|---:|
| bare_t2_baseline | 13 | 4 | 9 | 0 | 0 |
| bare_t3_baseline | 17 | 10 | 3 | 0 | 0 |
| routellm_learned_router_baseline | 19 | 4 | 7 | 0 | 0 |
| budget_only_baseline | 13 | 4 | 9 | 0 | 0 |
| budgetflow_task_level | 14 | 6 | 9 | 0 | 0 |

Suspect means the row should be inspected before paper use: a pass without trusted harness evidence, or a non-pass row carrying resolved-looking harness evidence.

## Task Order Audit

- Task count: 30.
- Task order source: `bare_t3_baseline`.
- High-value tasks (Task Value >= 1.5): 6; early=2, mid=3, late=1.
- On high-value tasks, BudgetFlow resolves 2 tasks / value 3.00; pure T3 resolves 3 tasks / value 4.50.
- Early third: BudgetFlow 7 resolved / value 7.00; pure T3 6 resolved / value 6.00.
- Middle third: BudgetFlow 6 resolved / value 7.00; pure T3 8 resolved / value 9.50.
- Late third: BudgetFlow 1 resolved / value 1.00; pure T3 3 resolved / value 3.00.

## Per-Task Matrix

| # | Task | Value | T2 | T3 | Route | Budget-only | BF |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `django__django-13447` | 1.00 | P 0.16 T2 | P 0.16 T3 | P 0.15 T2 | P 0.21 T3 | P 0.25 T2 |
| 2 | `mwaskom__seaborn-3190` | 1.50 | P 0.96 T2 | F 0.40 T3 | P 0.46 T2 | P 0.55 T3 | F 0.31 T3 |
| 3 | `pallets__flask-4992` | 1.00 | F 0.11 T2 | P 0.13 T3 | F 0.24 T3 | F 0.16 T2 | F 0.11 T3 |
| 4 | `sphinx-doc__sphinx-8595` | 1.00 | P 0.07 T2 | P 0.28 T3 | P 0.16 T2 | P 0.14 T2 | P 0.13 T2 |
| 5 | `pylint-dev__pylint-7993` | 1.00 | P 0.91 T2 | P 0.39 T3 | P 0.40 T2 | P 0.63 T2 | P 0.50 T2 |
| 6 | `sympy__sympy-17655` | 1.00 | P 0.73 T2 | F 0.42 T3 | P 0.50 T2 | P 1.24 T2 | P 1.00 T2 |
| 7 | `django__django-11179` | 1.00 | P 0.24 T2 | P 0.14 T3 | P 0.16 T2 | P 0.38 T2 | P 0.10 T2 |
| 8 | `mwaskom__seaborn-3010` | 1.00 | P 0.07 T2 | P 0.19 T3 | P 0.06 T2 | P 0.13 T2 | P 0.08 T2 |
| 9 | `pallets__flask-4045` | 1.50 | F 0.22 T2 | F 0.19 T3 | F 0.63 T2 | F 0.40 T2 | F 0.21 T3 |
| 10 | `sphinx-doc__sphinx-7738` | 1.00 | F 1.10 T2 | F 0.39 T3 | P 0.62 T2 | P 0.56 T2 | P 0.82 T2 |
| 11 | `django__django-15851` | 1.00 | P 0.12 T2 | P 0.12 T3 | P 0.08 T3 | P 0.11 T2 | P 0.11 T2 |
| 12 | `mwaskom__seaborn-2848` | 1.50 | P 2.11 T2 | P 0.33 T3 | P 1.12 T2 | P 1.37 T2 | P 0.34 T3 |
| 13 | `sympy__sympy-22714` | 1.00 | P 0.19 T2 | P 0.34 T3 | P 0.19 T2 | P 0.14 T2 | P 0.17 T2 |
| 14 | `pylint-dev__pylint-6506` | 1.00 | F 0.41 T2 | F 0.19 T3 | F 0.61 T2 | F 0.54 T2 | F 0.42 T2 |
| 15 | `sphinx-doc__sphinx-7686` | 1.00 | F 1.25 T2 | F 0.31 T3 | P 0.64 T3 | F 1.37 T2 | F 0.63 T3 |
| 16 | `django__django-11049` | 1.00 | P 0.11 T2 | P 0.23 T3 | P 0.28 T3 | P 0.16 T2 | P 0.12 T2 |
| 17 | `sympy__sympy-15346` | 1.00 | P 0.87 T2 | P 1.77 T3 | P 0.74 T3 | F 1.40 T2 | F 1.12 T2 |
| 18 | `mwaskom__seaborn-3407` | 1.50 | P 0.33 T2 | P 0.21 T3 | P 0.52 T2 | P 0.46 T2 | F 0.56 T3 |
| 19 | `django__django-15814` | 1.00 | F 0.00 - | P 0.19 T3 | P 1.10 T2 | F 0.00 - | P 0.66 T2 |
| 20 | `sympy__sympy-13647` | 1.50 | F 0.00 - | P 0.40 T3 | P 0.14 T2 | F 0.00 - | P 0.94 T3 |
| 21 | `sphinx-doc__sphinx-8801` | 1.00 | F 0.00 - | P 1.12 T3 | P 0.79 T3 | F 0.00 - | P 1.36 T2 |
| 22 | `sympy__sympy-12171` | 1.00 | F 0.00 - | F 0.34 T3 | F 0.24 T3 | F 0.00 - | F 0.00 - |
| 23 | `django__django-12908` | 1.00 | F 0.00 - | P 0.23 T3 | P 0.14 T2 | F 0.00 - | F 0.00 - |
| 24 | `sphinx-doc__sphinx-8282` | 1.00 | F 0.00 - | F 0.37 T3 | F 0.00 - | F 0.00 - | F 0.00 - |
| 25 | `sympy__sympy-24102` | 1.00 | F 0.00 - | F 0.44 T3 | F 0.00 - | F 0.00 - | F 0.00 - |
| 26 | `django__django-13964` | 1.00 | F 0.00 - | P 0.29 T3 | F 0.00 - | F 0.00 - | F 0.00 - |
| 27 | `sphinx-doc__sphinx-7975` | 1.00 | - | F 0.37 T3 | F 0.00 - | - | F 0.00 - |
| 28 | `sympy__sympy-18621` | 1.00 | - | F 0.00 - | F 0.00 - | - | F 0.00 - |
| 29 | `sympy__sympy-13177` | 1.50 | - | F 0.00 - | F 0.00 - | - | F 0.00 - |
| 30 | `sphinx-doc__sphinx-8273` | 1.00 | - | F 0.00 - | F 0.00 - | - | - |

Cell format: `P/F/A cost first-tier`.

## Routing And Spin Diagnostics

| Strategy | Rows | T3 Start | T3 Start Pass | T3 Start True Fail | T3 Start Abort | T3 Start Other | All-T2 Rows | All-T2 Turns | Extra All-T2 Turns vs Pure T3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | 26 | 0 | 0 | 0 | 0 | 0 | 18 | 611 | 470.0 |
| bare_t3_baseline | 30 | 27 | 17 | 10 | 0 | 0 | 0 | 0 | 0.0 |
| routellm_learned_router_baseline | 30 | 7 | 5 | 2 | 0 | 0 | 16 | 508 | 393.0 |
| budget_only_baseline | 26 | 2 | 2 | 0 | 0 | 0 | 16 | 569 | 444.0 |
| budgetflow_task_level | 29 | 7 | 2 | 5 | 0 | 0 | 14 | 477 | 356.0 |

- BudgetFlow T3-start rows: 7; resolved 2; true-fail 5; abort 0.
- BudgetFlow all-T2 rows on tasks with pure T3 rows: 14; turns 477 vs pure T3 121.

## BudgetFlow vs Pure T3 Diffs

- Both pass: 12 tasks.
- BudgetFlow-only pass: 2 tasks, value 2.00.
- Pure-T3-only pass: 5 tasks, value 5.50.
- Neither pass: 10 tasks.
- BudgetFlow-only tasks: `sympy__sympy-17655`(1.00), `sphinx-doc__sphinx-7738`(1.00)
- Pure-T3-only tasks: `pallets__flask-4992`(1.00), `sympy__sympy-15346`(1.00), `mwaskom__seaborn-3407`(1.50), `django__django-12908`(1.00), `django__django-13964`(1.00)


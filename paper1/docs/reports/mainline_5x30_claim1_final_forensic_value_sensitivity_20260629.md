# Claim 1 Forensic Value Sensitivity Audit

This is a no-paid audit of completed JSONL rows. It does not re-score patches or edit historical artifacts.

## Strategy Summary

| Strategy | Lane State | Rows | Scoreable | Abort | Resolved | Rate (planned) | Rate (scoreable) | Spend | Cost / Resolved | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | partial_incomplete | 16/30 | 14/30 | 2 | 10/30 | 33.3% | 71.4% | $8.22 | $0.82 | 11.00 | 1.34 |
| bare_t3_baseline | partial_incomplete | 22/30 | 22/30 | 0 | 14/30 | 46.7% | 63.6% | $6.33 | $0.45 | 17.00 | 2.68 |
| routellm_learned_router_baseline | partial_incomplete | 21/30 | 19/30 | 2 | 10/30 | 33.3% | 52.6% | $5.73 | $0.57 | 12.00 | 2.09 |
| budget_only_baseline | partial_incomplete | 20/30 | 18/30 | 2 | 9/30 | 30.0% | 50.0% | $5.24 | $0.58 | 10.50 | 2.00 |
| budgetflow_task_level | partial_incomplete | 22/30 | 22/30 | 0 | 13/30 | 43.3% | 59.1% | $6.19 | $0.48 | 16.00 | 2.58 |

## Value Sensitivity

Same resolved/not-resolved rows and same spend, rescored under alternate frozen Task Value profiles.

| Value Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |
|---|---|---:|---:|---:|---:|
| equal | bare_t2_baseline | 10/30 | $8.22 | 10.00 | 1.22 |
| equal | bare_t3_baseline | 14/30 | $6.33 | 14.00 | 2.21 |
| equal | routellm_learned_router_baseline | 10/30 | $5.73 | 10.00 | 1.74 |
| equal | budget_only_baseline | 9/30 | $5.24 | 9.00 | 1.72 |
| equal | budgetflow_task_level | 13/30 | $6.19 | 13.00 | 2.10 |
| criticality_value | bare_t2_baseline | 10/30 | $8.22 | 11.00 | 1.34 |
| criticality_value | bare_t3_baseline | 14/30 | $6.33 | 17.00 | 2.68 |
| criticality_value | routellm_learned_router_baseline | 10/30 | $5.73 | 12.00 | 2.09 |
| criticality_value | budget_only_baseline | 9/30 | $5.24 | 10.50 | 2.00 |
| criticality_value | budgetflow_task_level | 13/30 | $6.19 | 16.00 | 2.58 |
| compressed_criticality | bare_t2_baseline | 10/30 | $8.22 | 10.50 | 1.28 |
| compressed_criticality | bare_t3_baseline | 14/30 | $6.33 | 15.25 | 2.41 |
| compressed_criticality | routellm_learned_router_baseline | 10/30 | $5.73 | 10.75 | 1.88 |
| compressed_criticality | budget_only_baseline | 9/30 | $5.24 | 9.75 | 1.86 |
| compressed_criticality | budgetflow_task_level | 13/30 | $6.19 | 14.25 | 2.30 |
| expanded_criticality | bare_t2_baseline | 10/30 | $8.22 | 12.00 | 1.46 |
| expanded_criticality | bare_t3_baseline | 14/30 | $6.33 | 21.00 | 3.32 |
| expanded_criticality | routellm_learned_router_baseline | 10/30 | $5.73 | 15.00 | 2.62 |
| expanded_criticality | budget_only_baseline | 9/30 | $5.24 | 12.00 | 2.29 |
| expanded_criticality | budgetflow_task_level | 13/30 | $6.19 | 20.00 | 3.23 |

### BudgetFlow Margin Under Value Sensitivity

| Value Profile | Best Control By Value | BudgetFlow Value Delta | Best Control By Value/$ | BudgetFlow Value/$ Delta |
|---|---|---:|---|---:|
| equal | bare_t3_baseline | -1.00 | bare_t3_baseline | -0.11 |
| criticality_value | bare_t3_baseline | -1.00 | bare_t3_baseline | -0.10 |
| compressed_criticality | bare_t3_baseline | -1.00 | bare_t3_baseline | -0.11 |
| expanded_criticality | bare_t3_baseline | -1.00 | bare_t3_baseline | -0.08 |

### Value Permutation Diagnostic

This shuffles the same criticality-value multiset across the fixed task list. It is a diagnostic for value-placement dependence, not a replacement for the frozen main ValueSource.

| Samples | BudgetFlow Wins | Min Margin | P25 | Median | P75 | Max Margin |
|---:|---:|---:|---:|---:|---:|---:|
| 64 | 3/64 | -3.50 | -1.50 | -1.00 | -1.00 | +0.50 |

## Static Observed-Tier Oracle

- Skipped: complete pure T2 and pure T3 rows are required for all tasks.

## Scoring Evidence

| Strategy | Trusted Pass | Trusted True Fail | No-Patch True Fail | Abort | Suspect |
|---|---:|---:|---:|---:|---:|
| bare_t2_baseline | 10 | 4 | 0 | 2 | 0 |
| bare_t3_baseline | 14 | 8 | 0 | 0 | 0 |
| routellm_learned_router_baseline | 10 | 6 | 3 | 2 | 0 |
| budget_only_baseline | 9 | 7 | 2 | 2 | 0 |
| budgetflow_task_level | 13 | 6 | 3 | 0 | 0 |

Suspect means the row should be inspected before paper use: a pass without trusted harness evidence, or a non-pass row carrying resolved-looking harness evidence.

## Task Order Audit

- Task count: 30.
- Task order source: `paper1/docs/reports/mainline_5x30_claim1_prepaid_after_routingfix_budget_plan_20260629.json`.
- High-value tasks (Task Value >= 1.5): 10; early=3, mid=4, late=3.
- On high-value tasks, BudgetFlow resolves 4 tasks / value 7.00; pure T3 resolves 4 tasks / value 7.00.
- Early third: BudgetFlow 7 resolved / value 7.50; pure T3 6 resolved / value 6.50.
- Middle third: BudgetFlow 5 resolved / value 6.00; pure T3 7 resolved / value 8.00.
- Late third: BudgetFlow 1 resolved / value 2.50; pure T3 1 resolved / value 2.50.

## Per-Task Matrix

| # | Task | Value | T2 | T3 | Route | Budget-only | BF |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `django__django-13447` | 1.00 | P 0.19 T2 | P 0.22 T3 | P 0.27 T2 | P 0.18 T3 | P 0.07 T2 |
| 2 | `mwaskom__seaborn-3190` | 1.50 | P 0.97 T2 | P 0.37 T3 | F 0.30 T2 | P 0.26 T3 | P 0.31 T3 |
| 3 | `pallets__flask-4992` | 2.50 | F 0.11 T2 | F 0.19 T3 | F 0.18 T3 | F 0.09 T3 | F 0.16 T3 |
| 4 | `sphinx-doc__sphinx-8595` | 1.00 | P 0.17 T2 | P 0.25 T3 | P 0.11 T2 | P 0.16 T2 | P 0.26 T2 |
| 5 | `pylint-dev__pylint-7993` | 1.00 | A 0.05 T2 | P 0.21 T3 | F 0.31 T2 | F 0.31 T2 | P 0.34 T3 |
| 6 | `sympy__sympy-17655` | 1.00 | F 0.68 T2 | F 0.19 T3 | P 0.34 T2 | F 0.34 T2 | P 0.35 T3 |
| 7 | `django__django-11179` | 1.00 | P 0.25 T2 | P 0.11 T3 | P 0.08 T2 | P 0.05 T2 | P 0.09 T3 |
| 8 | `mwaskom__seaborn-3010` | 1.00 | P 0.06 T2 | P 0.16 T3 | P 0.09 T2 | P 0.11 T2 | P 0.17 T3 |
| 9 | `pallets__flask-4045` | 2.50 | F 0.28 T2 | F 0.38 T3 | F 0.29 T2 | F 0.44 T2 | F 0.30 T3 |
| 10 | `sphinx-doc__sphinx-7738` | 1.00 | P 1.50 T2 | F 0.63 T3 | F 0.33 T2 | F 0.35 T2 | F 0.22 T2 |
| 11 | `django__django-15851` | 1.00 | P 0.09 T2 | P 0.11 T3 | P 0.11 T3 | F 0.23 T2 | P 0.09 T2 |
| 12 | `mwaskom__seaborn-2848` | 1.50 | P 1.47 T2 | P 0.22 T3 | F 0.37 T2 | F 0.38 T2 | P 0.26 T3 |
| 13 | `sympy__sympy-22714` | 1.00 | P 0.45 T2 | P 0.18 T3 | P 0.23 T2 | P 0.11 T2 | P 0.27 T2 |
| 14 | `pylint-dev__pylint-6506` | 1.00 | A 0.05 T2 | F 0.14 T3 | F 0.36 T2 | F 0.36 T2 | F 0.24 T2 |
| 15 | `sphinx-doc__sphinx-7686` | 2.50 | F 1.69 T2 | F 0.26 T3 | F 0.62 T3 | F 0.74 T2 | F 0.48 T3 |
| 16 | `django__django-11049` | 1.00 | P 0.21 T2 | P 0.21 T3 | P 0.18 T3 | P 0.11 T2 | P 0.17 T2 |
| 17 | `sympy__sympy-15346` | 1.00 | - | P 0.88 T3 | F 0.35 T3 | A 0.07 T2 | F 0.39 T2 |
| 18 | `mwaskom__seaborn-3407` | 1.50 | - | F 0.16 T3 | P 0.40 T2 | P 0.41 T2 | F 0.37 T3 |
| 19 | `django__django-15814` | 1.00 | - | P 0.11 T3 | A 0.13 T2 | A 0.36 T2 | F 0.16 T2 |
| 20 | `sympy__sympy-13647` | 1.50 | - | P 0.25 T3 | A 0.07 T2 | P 0.19 T2 | P 0.46 T3 |
| 21 | `sphinx-doc__sphinx-8801` | 2.50 | - | P 0.94 T3 | P 0.61 T3 | - | P 0.62 T3 |
| 22 | `sympy__sympy-12171` | 1.00 | - | F 0.17 T3 | - | - | F 0.42 T2 |
| 23 | `django__django-12908` | 1.00 | - | - | - | - | - |
| 24 | `sphinx-doc__sphinx-8282` | 2.50 | - | - | - | - | - |
| 25 | `sympy__sympy-24102` | 1.00 | - | - | - | - | - |
| 26 | `django__django-13964` | 1.00 | - | - | - | - | - |
| 27 | `sphinx-doc__sphinx-7975` | 1.00 | - | - | - | - | - |
| 28 | `sympy__sympy-18621` | 1.00 | - | - | - | - | - |
| 29 | `sympy__sympy-13177` | 1.50 | - | - | - | - | - |
| 30 | `sphinx-doc__sphinx-8273` | 1.00 | - | - | - | - | - |

Cell format: `P/F/A cost first-tier`.

## BudgetFlow vs Pure T3 Diffs

- Both pass: 12 tasks.
- BudgetFlow-only pass: 1 tasks, value 1.00.
- Pure-T3-only pass: 2 tasks, value 2.00.
- Neither pass: 7 tasks.
- BudgetFlow-only tasks: `sympy__sympy-17655`(1.00)
- Pure-T3-only tasks: `sympy__sympy-15346`(1.00), `django__django-15814`(1.00)


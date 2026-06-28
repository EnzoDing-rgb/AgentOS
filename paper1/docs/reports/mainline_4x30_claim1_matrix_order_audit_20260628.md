# 4x30 Claim 1 Matrix And Task Order Audit

This is a no-paid audit of completed JSONL rows. It does not re-score patches or edit historical artifacts.

## Strategy Summary

| Strategy | Resolved | Rate | Spend | Cost / Resolved | Total Resolved Value | Total Resolved Value / Dollar |
|---|---:|---:|---:|---:|---:|---:|
| bare_t2_baseline | 12/30 | 40.0% | $10.44 | $0.87 | 13.50 | 1.29 |
| bare_t3_baseline | 15/30 | 50.0% | $9.46 | $0.63 | 18.00 | 1.90 |
| routellm_learned_router_baseline | 13/30 | 43.3% | $9.37 | $0.72 | 15.00 | 1.60 |
| budgetflow_task_level | 14/30 | 46.7% | $7.98 | $0.57 | 18.50 | 2.32 |

## Task Order Audit

- Task count: 30.
- Task order source: `docs/reports/mainline_4x30_lhm_cycle_4policy_planned_task_budget_regen_v2value_20260627.json`.
- High-value tasks (Task Value >= 1.5): 10; early=3, mid=4, late=3.
- On high-value tasks, BudgetFlow resolves 5 tasks / value 9.50; pure T3 resolves 4 tasks / value 7.00.
- Early third: BudgetFlow 8 resolved / value 10.00; pure T3 6 resolved / value 6.50.
- Middle third: BudgetFlow 3 resolved / value 4.00; pure T3 5 resolved / value 6.00.
- Late third: BudgetFlow 3 resolved / value 4.50; pure T3 4 resolved / value 5.50.

## Per-Task Matrix

| # | Task | Value | T2 | T3 | Route | BF |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `django__django-13447` | 1.00 | P 0.20 T2 | P 0.23 T3 | P 0.09 T2 | P 0.14 T2 |
| 2 | `mwaskom__seaborn-3190` | 1.50 | P 0.85 T2 | P 0.25 T3 | F 0.33 T2 | P 0.30 T3 |
| 3 | `pallets__flask-4992` | 2.50 | F 0.20 T2 | F 0.16 T3 | F 0.18 T3 | P 0.19 T3 |
| 4 | `sphinx-doc__sphinx-8595` | 1.00 | P 0.19 T2 | P 0.38 T3 | P 0.24 T2 | P 0.15 T2 |
| 5 | `pylint-dev__pylint-7993` | 1.00 | P 0.71 T2 | P 0.28 T3 | A 0.04 T2 | P 0.18 T3 |
| 6 | `sympy__sympy-17655` | 1.00 | F 1.43 T2 | F 0.28 T3 | P 0.36 T2 | P 0.37 T3 |
| 7 | `django__django-11179` | 1.00 | P 0.20 T2 | P 0.22 T3 | P 0.17 T2 | P 0.07 T3 |
| 8 | `mwaskom__seaborn-3010` | 1.00 | P 0.06 T2 | P 0.16 T3 | P 0.11 T2 | P 0.11 T3 |
| 9 | `pallets__flask-4045` | 2.50 | F 0.29 T2 | F 0.26 T3 | F 0.19 T2 | F 0.31 T3 |
| 10 | `sphinx-doc__sphinx-7738` | 1.00 | F 1.91 T2 | F 0.69 T3 | F 0.37 T2 | F 0.39 T3 |
| 11 | `django__django-15851` | 1.00 | P 0.09 T2 | P 0.08 T3 | P 0.10 T3 | F 0.11 T2 |
| 12 | `mwaskom__seaborn-2848` | 1.50 | P 0.97 T2 | P 0.30 T3 | F 0.42 T2 | P 0.18 T3 |
| 13 | `sympy__sympy-22714` | 1.00 | P 0.65 T2 | F 0.23 T3 | P 0.16 T2 | F 0.18 T2 |
| 14 | `pylint-dev__pylint-6506` | 1.00 | A 0.18 T2 | F 0.16 T3 | F 0.41 T2 | F 0.16 T2 |
| 15 | `sphinx-doc__sphinx-7686` | 2.50 | F 0.66 T2 | F 0.21 T3 | F 0.52 T3 | F 0.58 T3 |
| 16 | `django__django-11049` | 1.00 | P 0.14 T2 | P 0.17 T3 | P 0.33 T3 | P 0.12 T2 |
| 17 | `sympy__sympy-15346` | 1.00 | P 1.29 T2 | F 0.68 T3 | F 0.44 T3 | F 0.45 T2 |
| 18 | `mwaskom__seaborn-3407` | 1.50 | P 0.42 T2 | F 0.35 T3 | F 0.45 T2 | F 0.30 T3 |
| 19 | `django__django-15814` | 1.00 | F 0.00 - | P 0.28 T3 | A 0.29 T2 | A 0.30 T2 |
| 20 | `sympy__sympy-13647` | 1.50 | F 0.00 - | P 0.69 T3 | P 0.14 T2 | P 0.47 T3 |
| 21 | `sphinx-doc__sphinx-8801` | 2.50 | F 0.00 - | P 0.62 T3 | P 0.68 T3 | P 0.32 T3 |
| 22 | `sympy__sympy-12171` | 1.00 | F 0.00 - | F 0.14 T3 | F 0.12 T3 | F 0.50 T2 |
| 23 | `django__django-12908` | 1.00 | F 0.00 - | P 0.18 T3 | P 0.17 T2 | P 0.17 T2 |
| 24 | `sphinx-doc__sphinx-8282` | 2.50 | F 0.00 - | F 0.53 T3 | F 0.66 T3 | F 0.21 T3 |
| 25 | `sympy__sympy-24102` | 1.00 | F 0.00 - | F 0.36 T3 | F 0.37 T2 | F 0.56 T2 |
| 26 | `django__django-13964` | 1.00 | F 0.00 - | P 0.56 T3 | F 0.55 T2 | A 0.11 T2 |
| 27 | `sphinx-doc__sphinx-7975` | 1.00 | - | F 0.38 T3 | P 0.51 T3 | A 0.04 T2 |
| 28 | `sympy__sympy-18621` | 1.00 | - | P 0.28 T3 | P 0.27 T2 | P 0.54 T2 |
| 29 | `sympy__sympy-13177` | 1.50 | - | F 0.08 T3 | F 0.45 T2 | F 0.08 T3 |
| 30 | `sphinx-doc__sphinx-8273` | 1.00 | - | F 0.25 T3 | F 0.26 T3 | F 0.39 T2 |

Cell format: `P/F/A cost first-tier`.

## BudgetFlow vs Pure T3 Diffs

- Both pass: 12 tasks.
- BudgetFlow-only pass: 2 tasks, value 3.50.
- Pure-T3-only pass: 3 tasks, value 3.00.
- Neither pass: 13 tasks.
- BudgetFlow-only tasks: `pallets__flask-4992`(2.50), `sympy__sympy-17655`(1.00)
- Pure-T3-only tasks: `django__django-15851`(1.00), `django__django-15814`(1.00), `django__django-13964`(1.00)


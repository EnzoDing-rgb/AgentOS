# Historical Budgeting Prior

Generated from 2 source files, 40 clean rows.

## Per-Task Summary

| instance_id | records | resolved | median_cost | median_turns | dominant_tier | difficulty |
|---|---:|---:|---:|---:|---:|---:|
| sympy__sympy-13480 | 8 | 7/8 | 114.7 | 14 | T3 | TBD |
| sympy__sympy-13647 | 8 | 7/8 | 329.7 | 25 | T2 | TBD |
| sympy__sympy-14774 | 7 | 7/7 | 42.2 | 10 | T2 | TBD |
| sympy__sympy-16988 | 8 | 3/8 | 2091.0 | 141 | T1 | TBD |
| sympy__sympy-17139 | 1 | 1/1 | 725.3 | 39 | T3 | TBD |
| sympy__sympy-20212 | 8 | 8/8 | 308.9 | 46 | T1 | TBD |

## Difficulty Coefficients

Anchor: sympy__sympy-20212 = 1.0x (median_cost=308.9)

| task | difficulty | median_cost |
|---|---:|---:|
| sympy__sympy-13480 | 0.37x | 114.7 |
| sympy__sympy-13647 | 1.07x | 329.7 |
| sympy__sympy-14774 | 0.14x | 42.2 |
| sympy__sympy-16988 | 6.77x | 2091.0 |
| sympy__sympy-17139 | 2.35x | 725.3 |
| sympy__sympy-20212 | 1.00x | 308.9 |

## Confidence Distribution
- clean: 33
- usable_task_prior: 7

## Failure Class Distribution
- extract_fail: 5
- pass: 33
- repair_fail: 2

## Soft-Cap Recommendations

Per-task soft cap from historical median successful cost:

- **sympy__sympy-13480**: soft_cap=87.7 (median success), all_median=114.7, resolved=7/8, typical_tier=T3
- **sympy__sympy-13647**: soft_cap=231.5 (median success), all_median=329.7, resolved=7/8, typical_tier=T2
- **sympy__sympy-14774**: soft_cap=42.2 (median success), all_median=42.2, resolved=7/7, typical_tier=T2
- **sympy__sympy-16988**: soft_cap=3000.0 (median success), all_median=2091.0, resolved=3/8, typical_tier=T1
- **sympy__sympy-17139**: soft_cap=725.3 (median success), all_median=725.3, resolved=1/1, typical_tier=T3
- **sympy__sympy-20212**: soft_cap=308.9 (median success), all_median=308.9, resolved=8/8, typical_tier=T1

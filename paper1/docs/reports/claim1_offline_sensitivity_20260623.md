# Claim 1 Offline Sensitivity

Source: `paper1/data/runs/mainline_3x30_lhm_cycle_routefix_kv50_20260623.jsonl`. Historical JSONL is immutable; this analysis applies the documented patch-cleaner forensic pass corrections in derived metrics only.

## KV Sensitivity, Current Value

| KV input discount | Strategy | Yield | Cost | Yield/$ | Passes | Turns |
|---:|---|---:|---:|---:|---:|---:|
| 0% | pure T2 | 19.5 | $17.9595 | 1.0858 | 18 | 969 |
| 0% | pure T3 | 17.5 | $8.7395 | 2.0024 | 16 | 226 |
| 0% | BudgetFlow | 22.0 | $12.7868 | 1.7205 | 20 | 615 |
| 50% | pure T2 | 19.5 | $9.7729 | 1.9953 | 18 | 969 |
| 50% | pure T3 | 17.5 | $5.1336 | 3.4089 | 16 | 226 |
| 50% | BudgetFlow | 22.0 | $7.1727 | 3.0672 | 20 | 615 |
| 80% | pure T2 | 19.5 | $4.8610 | 4.0116 | 18 | 969 |
| 80% | pure T3 | 17.5 | $2.9701 | 5.8921 | 16 | 226 |
| 80% | BudgetFlow | 22.0 | $3.8043 | 5.7830 | 20 | 615 |
| 90% | pure T2 | 19.5 | $3.2236 | 6.0491 | 18 | 969 |
| 90% | pure T3 | 17.5 | $2.2489 | 7.7816 | 16 | 226 |
| 90% | BudgetFlow | 22.0 | $2.6814 | 8.2045 | 20 | 615 |
| 98% | pure T2 | 19.5 | $1.9138 | 10.1893 | 18 | 969 |
| 98% | pure T3 | 17.5 | $1.6720 | 10.4667 | 16 | 226 |
| 98% | BudgetFlow | 22.0 | $1.7832 | 12.3374 | 20 | 615 |
| 99% | pure T2 | 19.5 | $1.7500 | 11.1426 | 18 | 969 |
| 99% | pure T3 | 17.5 | $1.5998 | 10.9385 | 16 | 226 |
| 99% | BudgetFlow | 22.0 | $1.6709 | 13.1664 | 20 | 615 |

## Value Sensitivity at KV50

| Value profile | pure T2 Yield | pure T3 Yield | BF Yield |
|---|---:|---:|---:|
| `equal` | 18.0 | 16.0 | 20.0 |
| `current` | 19.5 | 17.5 | 22.0 |
| `current_high_to_2.0` | 21.0 | 19.0 | 24.0 |
| `current_high_to_2.5` | 22.5 | 20.5 | 26.0 |
| `top20_effort_critical` | 22.5 | 20.5 | 25.0 |
| `top33_effort_critical` | 24.5 | 21.5 | 28.5 |
| `effort_tertiles_1_1.5_2.5` | 27.5 | 24.0 | 31.5 |
| `both_fail_critical` | 19.5 | 17.5 | 23.5 |
| `top10_effort_critical` | 24.5 | 21.5 | 28.5 |

## Binding Cap Replay at KV50, Current Value

| Cap | Strategy | Attempted | Yield | Cost | Yield/$ |
|---:|---|---:|---:|---:|---:|
| $3.00 | pure T2 | 15 | 9.5 | $2.9401 | 3.2312 |
| $3.00 | pure T3 | 17 | 10.0 | $2.9445 | 3.3961 |
| $3.00 | BudgetFlow | 17 | 13.5 | $2.9813 | 4.5283 |
| $4.00 | pure T2 | 18 | 12.5 | $3.9541 | 3.1612 |
| $4.00 | pure T3 | 23 | 14.5 | $3.9682 | 3.6540 |
| $4.00 | BudgetFlow | 19 | 16.0 | $3.9972 | 4.0028 |
| $5.00 | pure T2 | 18 | 12.5 | $4.9650 | 2.5176 |
| $5.00 | pure T3 | 28 | 17.5 | $4.9101 | 3.5641 |
| $5.00 | BudgetFlow | 22 | 18.0 | $4.9581 | 3.6304 |
| $6.00 | pure T2 | 21 | 13.5 | $5.9444 | 2.2710 |
| $6.00 | pure T3 | 30 | 17.5 | $5.1336 | 3.4089 |
| $6.00 | BudgetFlow | 27 | 20.0 | $5.9992 | 3.3338 |
| $7.00 | pure T2 | 23 | 15.5 | $6.9965 | 2.2154 |
| $7.00 | pure T3 | 30 | 17.5 | $5.1336 | 3.4089 |
| $7.00 | BudgetFlow | 29 | 22.0 | $6.9740 | 3.1546 |
| $8.00 | pure T2 | 25 | 17.5 | $7.9361 | 2.2051 |
| $8.00 | pure T3 | 30 | 17.5 | $5.1336 | 3.4089 |
| $8.00 | BudgetFlow | 30 | 22.0 | $7.1727 | 3.0672 |
| $9.00 | pure T2 | 26 | 17.5 | $8.9609 | 1.9529 |
| $9.00 | pure T3 | 30 | 17.5 | $5.1336 | 3.4089 |
| $9.00 | BudgetFlow | 30 | 22.0 | $7.1727 | 3.0672 |
| $11.02 | pure T2 | 30 | 19.5 | $9.7729 | 1.9953 |
| $11.02 | pure T3 | 30 | 17.5 | $5.1336 | 3.4089 |
| $11.02 | BudgetFlow | 30 | 22.0 | $7.1727 | 3.0672 |

## Routing Metrics at KV50, Current Value

| Target | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| `t3_only` | 1 | 12 | 0 | 0.0769 | 1.0000 | 0.1429 |
| `t3_cheapest_solver` | 4 | 9 | 7 | 0.3077 | 0.3636 | 0.3333 |
| `high_effort_ge_40` | 3 | 10 | 4 | 0.2308 | 0.4286 | 0.3000 |
| `any_solver_route_relevance` | 7 | 0 | 12 | 1.0000 | 0.3684 | 0.5385 |

Full per-task frontier is in the JSON companion file.

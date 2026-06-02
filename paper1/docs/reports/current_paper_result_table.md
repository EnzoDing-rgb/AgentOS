| group | strategy | tasks | pass | cost | avg_cost | turns | failure_classes | next_action |
|---|---:|---:|---:|---:|---:|---:|---|---|
| raw ceiling GPT-5.3 goldpass2 | `all_gpt53` | 3 | 3/3 | 597.8 | 199.3 | 25 | pass=3 | keep / scale cautiously |
| raw ceiling GPT-5.3 tail2 | `all_gpt53` | 2 | 1/2 | 502.6 | 251.3 | 20 | pass=1, repair_fail=1 | inspect repair failures |
| raw ceiling GPT-5.5 hard case | `all_gpt55` | 1 | 0/1 | 982.2 | 982.2 | 5 | extract_fail=1 | fix protocol / patch extraction |
| BudgetFlow auto v2 smoke | `budgetflow_auto_v2_tight` | 2 | 1/2 | 1546.4 | 773.2 | 108 | pass=1, repair_fail=1 | inspect repair failures |
| BudgetFlow auto v2 smoke | `budgetflow_full_tight` | 2 | 0/2 | 1219.6 | 609.8 | 54 | repair_fail=2 | inspect repair failures |
| BudgetFlow auto v2 smoke | `stage_blind_tight` | 2 | 0/2 | 602.3 | 301.2 | 58 | repair_fail=2 | inspect repair failures |
| BudgetFlow autobudget p030 | `budget_only_tight` | 5 | 4/5 | 2824.1 | 564.8 | 273 | pass=4, repair_fail=1 | inspect repair failures |
| BudgetFlow autobudget p030 | `budgetflow_full_tight` | 5 | 2/5 | 2622.2 | 524.4 | 197 | loc_fail=1, pass=2, repair_fail=2 | inspect repair failures |
| BudgetFlow autobudget p030 | `stage_blind_tight` | 5 | 3/5 | 1531.8 | 306.4 | 147 | pass=3, repair_fail=2 | inspect repair failures |
| BudgetFlow bounded rescue v2 | `budget_only_tight` | 5 | 4/5 | 1708.5 | 341.7 | 175 | pass=4, repair_fail=1 | inspect repair failures |
| BudgetFlow bounded rescue v2 | `stage_blind_tight` | 1 | 1/1 | 128.8 | 128.8 | 16 | pass=1 | keep / scale cautiously |
| BudgetFlow rescue stoploss v2 | `budgetflow_full_tight` | 3 | 1/3 | 1476.5 | 492.2 | 101 | pass=1, repair_fail=2 | inspect repair failures |
| BudgetFlow rescue stoploss v2 | `stage_blind_tight` | 2 | 2/2 | 758.2 | 379.1 | 72 | pass=2 | keep / scale cautiously |

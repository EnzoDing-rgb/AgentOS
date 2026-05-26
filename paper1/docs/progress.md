# BudgetFlow Progress

## 明天回来先看这个

### 现在到哪了

- **E2E patch + local harness 已通**（2 sympy tasks，budgetflow_full）
- **gold patch 验证**：2/2 `harness_resolved=True`（harness 本身可信）
- **DeepSeek 生成 patch**：2/2 提取成功，**0/2 resolved**（patch corrupt，不能 apply）
- Docker SWE harness 不可用 → 用 `local_harness.py`（git checkout + pytest）

### E2E 2-task 结果（2026-05-26）

runner: `run_e2e_smoke.py budgetflow_full`  
tasks: `sympy__sympy-24152`, `sympy__sympy-24213`

| instance | workflow_steps_ok | patch_extracted | patch_applied | harness_resolved | picks |
|---|---|---|---|---|---|
| sympy-24152 | True | True | False | False | flash/pro/flash |
| sympy-24213 | True | True | False | False | flash/pro/flash |

- gold sanity：**2/2 resolved**（同 harness）
- model：**0/2 resolved** — patch 格式/内容不对，`git apply` 失败
- elapsed ≈ 68s

**指标边界：**

- `workflow_steps_ok` = API + rubric（弱，两 task 全 OK）
- `harness_resolved` = test_patch + model_patch apply + FAIL_TO_PASS pass + PASS_TO_PASS 子集 pass

### 10-task routing compare（仍有效）

runner: `run_deepseek_compare.py 10`

| strategy | workflow_steps_ok | total cost (gov units) | flash steps | pro steps |
|---|---|---|---|---|
| all_flash | 10/10 | 22.93 | 30 | 0 |
| all_pro | 10/10 | 109.63 | 0 | 30 |
| budgetflow_full | 10/10 | 52.23 | 20 | 10 |

- elapsed ≈ 575s
- budgetflow picks 稳定：**flash/pro/flash**（10 task 全同）
- cost 梯度：flash < budgetflow (~48%) < pro

**指标边界：**

- `workflow_steps_ok` = API 成功 + stage keyword rubric
- **不是** `harness_resolved` — 无 patch、无 SWE harness
- cost = mock-scale governor units，非精确 API USD

### 仍有效的 mock 结果（20 Lite tasks）

- `pressure=0.45`: budget_only 1/20，budgetflow_full 9/20
- mock backend，测 selector 机制，非真 fix

### 下一步（P0）

1. **提升 patch 质量** — repo context、更长 repair prompt、失败 retry；仍用 BudgetFlow 选档
2. **三策略 E2E compare** — all_flash / all_pro / budgetflow on 2–10 tasks
3. Docker 可用时切官方 SWE harness

### 现在不要做什么

- 不在 eval 10 上 tune pressure / progress_table
- 不做 continual learning
- 不做 trajectory / SweLoc / SweRank（除非为 held-out 校准）
- 不把 `workflow_steps_ok` 写成 resolved

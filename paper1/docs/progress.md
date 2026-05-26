# BudgetFlow Progress

## 明天回来先看这个

### 现在到哪了

- Tier-1 已经不再是 mock-only workflow。
- 现在已经进入 **真实 task + mock backend** 阶段。
- SWE-bench Lite 真实任务已经接进 BudgetFlow。

### 这轮刚做完什么

- 加了真实 Lite task adapter：`paper1/src/budgetflow/lite_tasks.py`
- 加了 Lite smoke runner：`paper1/src/budgetflow/run_lite_smoke.py`
- 本地数据目录已接好：`paper1/data/swebench_lite_export/`
- loader 已支持：
  1. 本地 `test.jsonl`
  2. 本地 `test.parquet`
  3. 在线 HF 回退
- tests 现在是 `4 passed`

### 当前最重要结果

20 个 SWE-bench Lite 真实任务，mock backend：

- `pressure = 0.22`
  - `workflow_level_router`: `1 / 50.2880`
  - `budget_only_step_router`: `9 / 79.2960`
  - `budgetflow_full`: `9 / 79.2960`

- `pressure = 0.45`
  - `workflow_level_router`: `1 / 50.2880`
  - `budget_only_step_router`: `1 / 50.2880`
  - `budgetflow_full`: `9 / 70.5040`

含义：

- `workflow_level_router` 很弱
- `budget_only_step_router` 在低 pressure 还能撑住
- `budgetflow_full` 在更高 pressure 下更稳

### 当前最诚实结论

- 真实 task 数据路径已经打通
- BudgetFlow 已经能在真实 Lite task 分布上跑 compare
- 但 backend 还是 mock
- 所以现在这是方向性证据，不是最终 paper 结果

### 下一步只做什么

1. 接最小真实 backend
   - 两档就够：`deepseek-v4-flash` / `deepseek-v4-pro`

2. 跑极小真实 execution pass
   - 先不追求大规模
   - 先验证真调用、真成本、真选档是否通

3. 如果真 backend 稳，再接 harness `resolved`

### 现在不要做什么

- 不做持续学习
- 不先接 full Verified
- 不先扩复杂 trajectory 管线
- 不先做大规模 paper-grade calibration

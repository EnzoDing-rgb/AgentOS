# BudgetFlow Tier-1 Result

## 一句话结论

现在已经进入 **真实 task + mock backend** 阶段。

> 在 20 个 SWE-bench Lite 真实任务上，BudgetFlow 已经不再只是手写 mock workflow 对比；当前结果表明，`budgetflow_full` 在较高 `budget_pressure` 下比弱 baseline 更稳，但目前 backend 仍是 mock，因此这还不是最终 paper 结果。

---

## 这轮做了什么

### 1. 真实 task 已接入

不再只跑手写 workflow spec。
现在已经把 **SWE-bench Lite 真实任务** 接到了 BudgetFlow：

- 本地导出目录：`paper1/data/swebench_lite_export/`
- 任务 adapter：`paper1/src/budgetflow/lite_tasks.py`
- smoke runner：`paper1/src/budgetflow/run_lite_smoke.py`

当前 loader 顺序：

1. 本地 `test.jsonl`
2. 本地 `test.parquet`
3. 在线 HuggingFace `princeton-nlp/SWE-bench_Lite`

### 2. backend 仍是 mock

这点要说清楚：

- task 已经是真实的 SWE-bench Lite task
- 但 backend 还是 BudgetFlow 当前的 mock backend
- 所以现在这一步叫：
  - **real-task smoke compare**
- 还不是：
  - **full real execution**

---

## 当前最重要结果

### 20-task SWE-bench Lite smoke compare

- 数据：20 个 SWE-bench Lite 真实任务
- backend：4 档 mock backend
- 比较策略：
  - `workflow_level_router`
  - `budget_only_step_router`
  - `budgetflow_full`

| budget_pressure | workflow_level_router | budget_only_step_router | budgetflow_full |
|---|---|---|---|
| 0.22 | 1 / 50.2880 | 9 / 79.2960 | 9 / 79.2960 |
| 0.45 | 1 / 50.2880 | 1 / 50.2880 | 9 / 70.5040 |

表中格式：

- `Resolved / Total cost`

---

## 这说明什么

### 1. 真实 task 数据路径已经打通

这是这轮最大进展。

现在已经不是：

- 手写 8 个 toy workflows

而是：

- 真实 SWE-bench Lite task
- 自动转成 BudgetFlow workflow 输入
- 再跑 compare

### 2. `workflow_level_router` 依旧很弱

在这 20 个任务上：

- `workflow_level_router` 在两个 pressure 下都只有 `1 solved`

这说明：

- workflow 开始时一次性选档
- 对这种任务仍然不够用

### 3. `budget_only_step_router` 和 `budgetflow_full` 开始分化

在 `pressure = 0.22`：

- `budget_only_step_router` = `9 / 79.2960`
- `budgetflow_full` = `9 / 79.2960`

这里两者持平。

在 `pressure = 0.45`：

- `budget_only_step_router` = `1 / 50.2880`
- `budgetflow_full` = `9 / 70.5040`

这里 `budgetflow_full` 明显更稳。

这说明当前 BudgetFlow 至少已经展示出一个值得继续推进的现象：

> 当 pressure 提高时，纯 budget-only 路由已经塌掉，但 stage-aware 的 `budgetflow_full` 还没有同步塌掉。

---

## 但现在还不能夸太满

### 1. backend 还是 mock

这是最大限制。

所以当前结果能说明：

- 真实 task 分布下，BudgetFlow 机制有信号

但还不能说明：

- 真实模型执行下最终 `resolved` 一定同样成立

### 2. 当前 task adapter 还是极简映射

现在只是把 SWE-bench Lite task 元信息映射成：

- `Localization`
- `Repair`
- `Validation`

以及一套粗略 token 估计。

它的价值是：

- 让真实任务先跑起来

不是：

- 直接提供 paper-grade execution realism

### 3. 当前 calibration 仍然不是 trajectory-derived

还没有接：

- public `.traj` replay calibration
- SweLoc / SweRank localization gold signal
- full held-out calibration split

所以现在仍然是：

- 真实 task
- 但 calibration 还是轻量版

---

## 当前最诚实结论

如果现在停下，最诚实的说法是：

> BudgetFlow 已经从 mock-only workflow 对比，前进到 SWE-bench Lite 真实任务驱动的 smoke compare。在 20 个真实任务上，`budgetflow_full` 相比 workflow-level baseline 明显更强，并且在更高 `budget_pressure` 下比 budget-only step routing 更稳；但由于当前 backend 仍是 mock、task adapter 仍是极简映射，这一结果应被视为“真实任务分布下的方向性证据”，而不是最终 paper 结论。

---

## 下一步

现在最自然下一步已经很明确：

### 1. 接最小真实 backend

优先只接两档：

- `deepseek-v4-flash`
- `deepseek-v4-pro`

目的不是一下子做完整系统，而是先把：

- BudgetFlow 选档
- 真实模型调用
- 真实 token 成本

这三件事真正串起来。

### 2. 跑更小但更真的 execution pass

先不用全量 20-task final eval。
先做：

- 极小子集
- 真 backend
- 真调用
- 看 call path、账本、成本、路由是否都对

### 3. 再决定是否接 harness `resolved`

如果真 backend call path 稳定，再接：

- patch 生成
- harness evaluation
- 最终 `resolved`

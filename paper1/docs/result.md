# BudgetFlow Tier-1 Mock Result

## 一句话结论

在新的 **四档 backend** 和更连续的 mock progress 设定下，当前结果说明：

> BudgetFlow 仍然能在低 pressure 区间做到 **和更强 baseline 相同的 solved count，但成本更低**；但一旦 pressure 升高，当前 BudgetFlow 会比强化后的 budget-only baseline 更早掉点。

所以结论变得更诚实了：

- 现在已经不是“随便一个弱 baseline 都能被打赢”
- 但也还不能说当前 BudgetFlow 已经全面优于强化后的 step-level baseline

---

## 这次改了什么

这轮不是随便调数字，而是先把实验做得更硬一点。

### 1. backend 从 2 档改成 4 档

固定四档：

1. `tier1_cheap`
2. `tier2_balanced`
3. `tier3_strong`
4. `tier4_elite`

每档都有不同的：

- input/output cost
- capability
- mean output tokens
- latency

这样路由不再只是“cheap vs strong”二选一。

### 2. mock progress 改成连续型

之前太二元：

- 能过就是过
- 不能过就是不能过

现在改成：

- success 概率由 `stage`、`backend tier`、`workflow difficulty`、`input_tokens` 共同决定
- 仍然保持 deterministic，可复现实验结果

这样结果更像一个粗糙但合理的 controllable world，而不是一眼假的硬阈值世界。

### 3. baseline 变强了

#### `workflow_level_router`

现在不再是随便写死。
它会在 workflow 开始时，基于整条 workflow 的平均重要性和当前 `budget_pressure`，**一次性选一个固定档位**。

#### `budget_only_step_router`

现在也不再是简单 cheap/strong 二选一。
它会按 `budget_pressure` 分段选择 4 档 backend，但仍然**完全不看 stage**。

所以这轮比较比之前公平得多。

---

## 实验设置

- 8 个 workflows
- 每个 workflow 3 步：
  - `Localization`
  - `Repair`
  - `Validation`
- 比较 3 个策略：
  - `workflow_level_router`
  - `budget_only_step_router`
  - `budgetflow_full`
- 做系统 pressure sweep，而不是只看单点

---

## 主结果表

| budget_pressure | workflow_level_router | budget_only_step_router | budgetflow_full |
|---|---|---|---|
| 0.10 | 6 / 21.7644 | 6 / 21.7644 | 6 / 18.3448 |
| 0.14 | 6 / 21.7644 | 6 / 21.7644 | 6 / 17.9964 |
| 0.18 | 6 / 21.7644 | 6 / 21.7644 | 6 / 17.9964 |
| 0.22 | 2 / 13.4792 | 6 / 21.7644 | 5 / 17.8472 |
| 0.30 | 2 / 13.4792 | 6 / 21.7644 | 1 / 14.1908 |
| 0.45 | 2 / 13.4792 | 2 / 13.4792 | 1 / 9.3032 |
| 0.60 | 0 / 4.1420 | 2 / 13.4792 | 0 / 7.3464 |
| 0.90 | 0 / 4.1420 | 0 / 7.9740 | 0 / 4.1420 |
| 1.50 | 0 / 4.1420 | 0 / 4.1420 | 0 / 4.1420 |

表中格式：

- `Resolved / Total cost`

---

## 这轮最重要的发现

### 发现 1：BudgetFlow 的“省钱不掉 solved”还在

在低 pressure 区间：

- `budget_pressure = 0.10`
- `budget_pressure = 0.14`
- `budget_pressure = 0.18`

三者 solved count 都是 6，
但：

- `workflow_level_router` = 21.7644
- `budget_only_step_router` = 21.7644
- `budgetflow_full` = 18.3448 / 17.9964

也就是说：

> 当前 BudgetFlow 仍然能保持 solved count 不变，同时显著降低成本。

相对 `budget_only_step_router` 的成本下降约：

- `0.10`：**15.7%**
- `0.14` / `0.18`：**17.3%**

这是当前最强、最干净的正结果。

### 发现 2：强化 baseline 之后，BudgetFlow 的脆弱点暴露出来了

在 `budget_pressure = 0.22`：

- `budget_only_step_router` = 6 / 21.7644
- `budgetflow_full` = 5 / 17.8472

这里 BudgetFlow 省钱，但已经开始掉 solved。

在 `budget_pressure = 0.30`：

- `budget_only_step_router` = 6 / 21.7644
- `budgetflow_full` = 1 / 14.1908

这里说明当前 BudgetFlow 对 pressure 已经过敏，掉点太快。

### 发现 3：workflow-level baseline 依然偏弱，但没有以前那么假

- 在很低 pressure 下，它能到 6 / 21.7644
- 但一旦进入中区间，它掉得很快

说明：

- workflow 开始时一次性选档，确实能在“非常宽松预算”下凑出不错结果
- 但它缺乏 step-aware 调节能力，所以在 tighter regime 里不稳

这个 baseline 现在仍弱于 budget-only step routing，但已经比旧版可信得多。

---

## 当前最关键的 weakness

### 1. BudgetFlow 现在对 `budget_pressure` 太敏感

这是当前最大问题。

现象很明显：

- `0.10 ~ 0.18` 还不错
- 到 `0.22` 开始掉 solved
- 到 `0.30` 基本崩掉

这说明当前 selector / progress table / stage weight 的组合还不够稳。

### 2. 当前 progress table 还是 cold-start heuristic

虽然 mock backend 更真实了，
但 `budgetflow_full` 自己用的 progress table 仍然还是手工的 zero-calibration default。

这会导致：

- low-pressure 下能打出好结果
- 但 pressure 一变，误判会被放大

### 3. 当前 BudgetFlow 对 Repair / Validation 的升级边界还不够准

从结果看，BudgetFlow 在中等 pressure 下变得过于保守。

这不一定说明“stage-aware 思路错了”，更像是：

- 当前 stage-aware gain estimate 还太粗
- 所以一旦 pressure 上来，selector 就过早停止升级

---

## 哪些事情现在不重要

先不要急着做这些：

- 不要接真实 backend
- 不要上 RL
- 不要为了好看去挑单点 pressure 汇报
- 不要继续扩 backend 到 5 档以上
- 不要先做更大规模工程接入

当前主要矛盾不是工程接入，而是：

> 让 stage-aware 路由在更真实的 mock 世界里，面对更强 baseline 时仍然稳得住。

---

## 下一步建议

顺序不变，但现在更具体了：

### 1. 先继续加强 `budgetflow_full` 自己的 calibration

重点不是乱调，而是让它的 stage-aware 估计更靠谱：

- 重新整理 `Progress[stage, tier]`
- 特别检查 `Repair` / `Validation` 的 tier gain
- 避免一上 pressure 就过早保守

### 2. 再做更细的 held-out pressure 区间分析

不是为了找最漂亮点，
而是为了看：

- 哪个区间稳定
- 哪个区间开始脆弱
- 脆弱是因为哪一类 step 被过早降档

### 3. 增加 step-level trace 分析

下一轮不要只看总表。
要直接看：

- 哪些 workflow 在 `0.22` 和 `0.30` 掉了
- 掉在 `Localization`、`Repair` 还是 `Validation`
- BudgetFlow 比 budget-only 少升了哪一级

---

## 当前最诚实的结论

如果现在停下，最诚实的说法是：

> 在更真实的四档 mock 设定和更强 baseline 下，BudgetFlow 仍然能在低 pressure 区间实现“相同 solved、更低成本”；但当前版本对 budget_pressure 过于敏感，在中等 pressure 区间会比强化后的 budget-only step baseline 更早掉 solved，因此目前最需要做的不是扩系统，而是提升 stage-aware calibration 的稳健性。

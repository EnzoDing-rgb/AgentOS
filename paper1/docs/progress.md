# BudgetFlow Progress

## 明天回来先看这个

### 现在到哪了

- Tier-1 最小系统已经能跑通：runtime / ledger / governor / selector / scheduler / mock backend / minimal loop / compare runner 都有了。
- 现在不是“能不能跑”的问题。
- 现在的问题是：**在更真实的 mock 世界里，BudgetFlow 是否还能稳定优于更强 baseline。**

### 这轮刚做完什么

- mock backend 从 **2 档** 改成 **4 档**。
- mock progress 从二元规则改成了 **更连续的 deterministic 概率模型**。
- baseline 加强了：
  - `workflow_level_router`
  - `budget_only_step_router`
- 重跑了系统 `budget_pressure` sweep。
- `paper1/docs/result.md` 已更新。

### 当前最重要结果

低 pressure 区间（`0.10 ~ 0.18`）：

- `workflow_level_router`: `6 / 21.7644`
- `budget_only_step_router`: `6 / 21.7644`
- `budgetflow_full`: `6 / 17.9964 ~ 18.3448`

含义：

- BudgetFlow 还能做到 **same solved, lower cost**。
- 相对 `budget_only_step_router`，当前省钱约 **15.7% ~ 17.3%**。

### 当前最关键问题

不是 baseline 太弱了。
现在真正的问题是：

> `budgetflow_full` 对 `budget_pressure` 太敏感。

现象：

- `0.10 ~ 0.18` 结果不错
- `0.22` 开始掉 solved
- `0.30` 掉得很明显

这说明：

- 当前 `stage-aware` 思路还在
- 但当前 calibration 还不稳
- 尤其是 `Repair / Validation` 的升级边界可能太保守

### 当前最诚实结论

- 现在已经证明：BudgetFlow 在更真实四档 mock 里，**有能力**做到 same solved, lower cost。
- 但还没证明：它能在更宽 pressure 区间里稳定压过强化后的 step-level baseline。

### 下一步只做什么

1. 看 step-level trace
   - 重点看 `0.22` 和 `0.30`
   - 找出到底是哪一类 step 被过早降档

2. 调 `budgetflow_full` 的 calibration
   - 先查 `Progress[stage, tier]`
   - 重点修 `Repair / Validation`
   - 不要乱调别的地方

3. 重跑 sweep
   - 看中间区间能不能稳住
   - 继续报告整体现象，不报单点胜利

### 现在不要做什么

- 不接真实 backend
- 不上 RL
- 不扩到 5 个以上 backend
- 不为了结果好看只挑一个 pressure 点

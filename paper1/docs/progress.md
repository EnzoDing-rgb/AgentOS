# BudgetFlow Progress

## 明天回来先看这个

### 现在到哪了

- Tier-1 最小系统已跑通。
- 刚完成一轮：**step trace → Repair/Validation calibration → 重跑 sweep**。
- 低/中 pressure（0.10~0.22）BudgetFlow **已稳定优于** budget-only baseline（solved 更高 + cost 更低）。
- 0.30 仍掉点，根因已定位：**Localization 被过早降档**（本轮按指令未动）。

### 这轮刚做完什么

1. **Step trace**（pressure=0.22 / 0.30）
   - 校准前 @0.30：Localization→cheap、Validation→strong（非 elite）
   - Repair 始终 elite，不是主因
   - 校准后 @0.30：Validation 已升到 elite；Localization 仍→cheap，5/6 workflow 因此 FAIL

2. **Calibration**（只动 Repair/Validation）
   - `Progress[repair/validation, tier]` 对齐 mock backend 在代表性 token 长度下的 success prob
   - Localization 未改

3. **重跑 sweep**（6 workflows, budget=40）
   - 见 `paper1/docs/result.md`

### 当前最重要结果

| pressure | budget_only | budgetflow_full |
|---|---|---|
| 0.10~0.18 | 4 / 15.83 | **5 / 13.10~13.45** |
| 0.22 | 4 / 15.83 | **5 / 13.10** |
| 0.30 | 4 / 15.83 | 1 / 12.35 |

含义：
- 0.22 区间已稳住，且 **solved 5 > 4**
- 0.30 仍崩，但 R/V 校准有效（Validation 不再卡在 strong）

### 当前最关键问题

> **Localization 的 Progress table 与 mock 世界不匹配**，pressure≥0.30 时被降到 cheap，5/6 workflow 第一步就 FAIL。

Repair/Validation 校准已完成；下一步若继续，应修 Localization tier gain（本轮刻意跳过）。

### 下一步只做什么

1. 修 Localization calibration（对齐 mock，同 Repair/Validation 做法）
2. 重跑 sweep，看 0.30 区间能否稳住
3. 继续报整体曲线，不挑单点

### 现在不要做什么

- 不接真实 backend
- 不上 RL
- 不扩第 5 档
- 不为了结果好看只挑一个 pressure 点

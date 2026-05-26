# BudgetFlow Tier-1 Mock Result

## 一句话结论

Repair/Validation calibration 后：

> BudgetFlow 在 **0.10~0.22** 区间稳定做到 **更高 solved + 更低 cost**；**0.30** 仍掉点，根因是 **Localization 过早降档**（R/V 已修复）。

---

## 本轮做了什么

### 1. Step trace 分析（校准前）

**pressure=0.22**
- BudgetFlow：Localization→balanced，Repair/Validation→elite
- wf-2 Repair 天然 FAIL（两策略共同）
- BudgetFlow 5 solved vs budget-only 4 solved

**pressure=0.30（校准前）**
- BudgetFlow：Localization→**cheap**，Validation→**strong**（score 0.29 < 0.30，卡在 elite 门槛下），Repair→elite
- 5/6 workflow 因 Localization cheap 第一步 FAIL
- Validation strong→elite 升级分数刚好低于 threshold → **过早降档**

结论：**Repair 不是主因；Validation tier gain 低估；Localization 是 0.30 最大杀手。**

### 2. Calibration 改动

只改 `selector.py` 中 Repair/Validation 的 `Progress[stage, tier]`：

| stage | tier1 | tier2 | tier3 | tier4 |
|---|---|---|---|---|
| repair (新) | 0.051 | 0.150 | 0.426 | 0.741 |
| validation (新) | 0.103 | 0.259 | 0.529 | 0.801 |
| localization (未动) | 0.150 | 0.185 | 0.205 | 0.218 |

数值来自 mock backend 在代表性 token 长度（repair~135, validation~109）下的 success probability。

### 3. Step trace（校准后）

**pressure=0.30**
- Validation 已升到 **elite**（R/V 校准生效）
- Localization 仍→**cheap** → wf-1~5 FAIL，仅 wf-6 OK

---

## 实验设置

- 6 个 workflows（wf-1 ~ wf-6）
- 每个 workflow 3 步：Localization / Repair / Validation
- 4 档 backend（tier1_cheap ~ tier4_elite）
- total_budget = 40.0
- 比较 3 策略：workflow_level_router / budget_only_step_router / budgetflow_full

---

## 主结果表（校准后）

| budget_pressure | workflow_level_router | budget_only_step_router | budgetflow_full |
|---|---|---|---|
| 0.10 | 4 / 15.8340 | 4 / 15.8340 | **5 / 13.4488** |
| 0.14 | 4 / 15.8340 | 4 / 15.8340 | **5 / 13.1004** |
| 0.18 | 4 / 15.8340 | 4 / 15.8340 | **5 / 13.1004** |
| 0.22 | 1 / 9.7832 | 4 / 15.8340 | **5 / 13.1004** |
| 0.30 | 1 / 9.7832 | 4 / 15.8340 | 1 / 12.3476 |
| 0.45 | 1 / 9.7832 | 1 / 9.7832 | 1 / 12.3476 |
| 0.60 | 0 / 2.9900 | 1 / 9.7832 | 1 / 12.3476 |
| 0.90 | 0 / 2.9900 | 0 / 5.7708 | 1 / 12.3476 |
| 1.50 | 0 / 2.9900 | 0 / 2.9900 | 1 / 12.3476 |

格式：`Resolved / Total cost`

---

## 整体现象（不报单点）

### 低 pressure（0.10~0.18）

- BudgetFlow **5 solved**，baseline **4 solved**
- cost **~13.1** vs **~15.8**（省 ~17%）
- stage-aware 路由在低 pressure 下 **既省钱又多解**

### 中 pressure（0.22）

- BudgetFlow **5 solved / 13.10**，budget-only **4 solved / 15.83**
- **0.22 区间已稳住**，且 solved 反超 baseline
- workflow_level_router 在此区间已崩（1 solved）

### 中 pressure（0.30）

- budget-only 仍 **4 solved**
- BudgetFlow 仍 **1 solved**
- R/V 校准后 Validation 已升到 elite，但 Localization cheap 仍导致 5/6 workflow 第一步 FAIL
- **剩余瓶颈明确在 Localization calibration**

### 高 pressure（0.45+）

- 三策略 solved 均低
- BudgetFlow 因 R/V 升级更积极，高 pressure 下偶有余存 solved，但 cost 偏高
- 此区间不是当前优化目标

---

## 当前最诚实结论

> Repair/Validation mock-aligned calibration 有效：0.22 区间 BudgetFlow 已稳定优于 budget-only（solved 更高 + cost 更低）。0.30 掉点根因从「R/V 过早保守」转为「Localization 过早降 cheap」——下一步应修 Localization tier gain，而非继续动 R/V。

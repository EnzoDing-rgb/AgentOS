# BudgetFlow Tier-1 Result

## 一句话结论

1. **Mock 20-task**：`budgetflow_full` 高 pressure 比 budget-only 稳（selector 方向信号，mock backend）。
2. **DeepSeek 10-task compare 已跑完**：routing/cost baseline 成立 — BudgetFlow **flash/pro/flash**，cost ≈ all_pro 的 48%。
3. **E2E 2-task**：链路通；旧 direct-diff **0/2 resolved**；新 workspace edit IR **0/2 resolved** 但 failure 已进 harness 层。

> routing baseline 成立；harness contract 成立；model 语义修复仍不够 — **不能 claim 修 bug**。

--- 

## 结果分层（两个维度）

| 维度 | 指标 | 现在能说什么 |
|---|---|---|
| 工作流层 | `workflow_steps_ok` | API 成功 + stage keyword rubric（弱） |
| 修复层 | `harness_resolved` | git apply + pytest（local harness；gold 2/2 校验过） |

**不能**把 `workflow_steps_ok` 当成 bug 修好了。

---

## A. Mock backend — 20 Lite tasks（仍有效）

- runner：`run_lite_smoke.py`
- backend：4 档 mock

| budget_pressure | workflow_level | budget_only | budgetflow_full |
|---|---|---|---|
| 0.22 | 1 / 50.29 | 9 / 79.30 | 9 / 79.30 |
| 0.45 | 1 / 50.29 | 1 / 50.29 | **9 / 70.50** |

格式：`workflow_steps_ok / total_cost`（mock governor units）

---

## B. DeepSeek 真 API — 10-task 三策略 compare（2026-05-26）

### 设置

- runner：`python src/budgetflow/run_deepseek_compare.py 10`
- tasks：SWE-bench Lite 前 10 个（astropy×6 + django×4）
- strategies：`all_flash` / `all_pro` / `budgetflow_full`
- frozen：`FROZEN_BUDGET_PRESSURE=0.35`，progress table 手设未 tune
- cost：mock-scale governor units（跨策略公平），非精确 API USD
- elapsed：**575.3s**

### Summary

| strategy | workflow_steps_ok | total cost | flash steps | pro steps |
|---|---|---|---|---|
| all_flash | **10/10** | 22.93 | 30 | 0 |
| all_pro | **10/10** | 109.63 | 0 | 30 |
| budgetflow_full | **10/10** | 52.23 | 20 | 10 |

### Per-task picks（budgetflow_full）

全部 10 task：**flash / pro / flash**（Repair 步升 Pro，L/V 用 Flash）

### 读法

**能说的：**

- 真 DeepSeek API + 真 Lite issue 上，三策略可复现跑完
- BudgetFlow 有稳定 Flash/Pro mix（对比旧 smoke 100% Pro）
- cost 梯度：flash (22.9) < budgetflow (52.2, **47.6% of pro**) < pro (109.6)

**不能说的：**

- 10/10 workflow_steps_ok **不代表** 10 bug 修好 — rubric 弱（keyword + len≥20），三策略全满
- 不能 claim BudgetFlow 修 bug 更好/更差 — 还没 harness
- 不能当 paper 主结果 — 这是 routing baseline

### 旧 smoke（作废）

20-task 全 Pro、`workflow_steps_ok=20/20` — 仅连通性，eval 价值为零。

---

## C. E2E patch + harness — 2 sympy tasks

### C1. 旧路线：direct diff（2026-05-26，已 supersede）

- runners: `run_e2e_smoke.py`, `run_e2e_compare.py`
- repair 输出 ` ```diff ` → 2/2 patch 抽出，**0/2 resolved**（hunk corrupt / apply fail）
- file context 有改善但未够

### C2. 新路线：通用 edit IR → workspace diff（2026-05-26）

- pipeline: JSON `edits` → `repair_workspace.realize_repair_edits` → `git diff` → pytest
- ops: `replace`, `anchor_replace`, `insert_before/after`, `line_replace`
- failure telemetry: `parse_error`, `target_not_found`, `ambiguous_anchor`, `empty_diff`, `harness_fail`
- multi-round repair: up to 5 attempts，`failure_class` 驱动 retry prompt

| task | patch_extracted | harness_resolved | failure bucket |
|---|---|---|---|
| sympy__sympy-24213 | 1/1 | 0/1 | **harness_fail** |
| sympy__sympy-24152 | 1/1 | 0/1 | harness_fail |

**读法：**

- task2 早期卡在 `target_not_found`（exact-match 太脆）；IR 升级后 patch 能导出，失败在 pytest — **healthier signal**
- task1 同样 patch apply OK，语义修不对 — 不是 IR/formatting 问题
- harness 价值 = 统一 contract + 可 bucket 的失败，不是 “一次命中”

### 三策略 E2E compare（旧 direct-diff，v2 +file context）

| strategy | harness_resolved | patch_extracted | cost (gov units) |
|---|---|---|---|
| all_flash | 0/2 | 2/2 | 4.79 |
| all_pro | 0/2 | 2/2 | 18.12 |
| budgetflow_full | 0/2 | 2/2 | 8.18 |

- picks: budgetflow 仍 **flash/pro/flash**
- elapsed ≈ 333s

### 读法

- E2E 链路 + 三策略 compare 通
- **全策略 0/2 resolved** — patch 抽出 OK，hunk 行号/格式 corrupt → `git apply` 失败
- file context 有改善方向但未够；下一刀 = apply-fail retry

---

## 当前最诚实结论

| 问题 | 答案 |
|---|---|
| BudgetFlow 路由 work？ | 是 — 10/10 task flash/pro/flash |
| 比 all_flash 省多少 cost？ | budgetflow 52 vs flash 23 — **更贵**（买 Repair 步 Pro） |
| 比 all_pro 省多少 cost？ | 52 vs 110 — **省 ~52%**（同 rubric 全 OK 前提下） |
| bug 修好了吗？ | **0/2**（edit IR 路线）；failure 已在 harness 语义层，非 patch formatting |

---

## 下一步

### P0 — harness-fail retry

- pytest 失败摘要 → repair retry（已有 5 rounds；需更短、更 actionable 的 error 摘要）
- resolved>0 再扩 task 数

### 现在不要做

- 在 eval 10 上 tune pressure / progress_table
- 把 workflow_steps_ok 当 resolved 写进 paper
- continual learning / trajectory / SweLoc / SweRank（除非 held-out 校准）

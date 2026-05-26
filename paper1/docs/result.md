# BudgetFlow Tier-1 Result

## 一句话结论

现在有两层结果，要分开看：

1. **Mock backend + 20 Lite tasks**：`budgetflow_full` 在高 pressure 下比弱 baseline 更稳（方向性证据）。
2. **DeepSeek 真 API**：call path 已通，但 **20-task 三策略 compare 还没跑完**；旧 smoke 跑（20/20 全 Pro）**不能当 paper 证据**。

> 当前最诚实说法：真实 task 分布 + mock 有信号；真 backend 有连通性，但还缺 **held-out 校准 + 三策略 20-task compare + harness resolved** 才能谈 paper 结论。

---

## 结果分层（两个维度）

| 维度 | 指标 | 现在能说什么 |
|---|---|---|
| 工作流层 | `workflow_steps_ok` | API 成功 + stage keyword rubric（弱） |
| 修复层 | `harness_resolved` | **N/A** — 无 patch 生成 / 无 SWE harness |

**不能**把 `workflow_steps_ok` 当成 bug 修好了。

---

## A. Mock backend — 20 Lite tasks（仍有效）

- 数据：20 个 SWE-bench Lite 真实任务
- backend：4 档 mock
- runner：`run_lite_smoke.py`

| budget_pressure | workflow_level | budget_only | budgetflow_full |
|---|---|---|---|
| 0.22 | 1 / 50.29 | 9 / 79.30 | 9 / 79.30 |
| 0.45 | 1 / 50.29 | 1 / 50.29 | **9 / 70.50** |

格式：`resolved / total_cost`（mock governor units）

**读法：** pressure 升高 → budget-only 塌，`budgetflow_full` 仍 9/20。仅 mock，非真模型。

---

## B. DeepSeek 真 API — 当前状态

### B1. 已落地代码

| 文件 | 作用 |
|---|---|
| `deepseek_backend.py` | Flash/Pro 真调用；`.env` 读 key；stage keyword rubric |
| `lite_tasks.py` | 真实 issue → L/R/V prompt |
| `selector.py` | `build_deepseek_progress_table()` — 手设 2-tier priors，**未 tune eval 20** |
| `loop.py` | `backend_runner` + 可选 `progress_table` |
| `run_deepseek_compare.py` | 三策略：`all_flash` / `all_pro` / `budgetflow_full` |

冻结超参（未在 eval 20 上 tune）：

- `FROZEN_BUDGET_PRESSURE = 0.35`
- governor `total_budget = 20.0`（mock-scale cost，否则 reserve 被拒）
- cost 报告 = mock-scale governor units（跨策略公平），**非精确 API USD**

### B2. 旧 smoke run — **作废，仅连通性**

`run_deepseek_smoke.py`，20 tasks，`pressure=0.3`，旧 4-tier zero calibration + 真实 tiny token cost：

```
workflow_steps_ok = 20/20
backend_picks: flash=0, pro=60
total_cost ≈ $0.07 (真实 token 价)
elapsed ≈ 696s
```

**问题（故意暴露）：**

- 100% Pro → selector 对 2-tier DeepSeek 无意义
- `resolved` = rubric `len≥20` 时代 → 全 OK 不代表修 bug
- **不能**证明 BudgetFlow 有用

### B3. 新 compare — 1-task probe（2026-05-24）

`run_deepseek_compare.py 1`，`pressure=0.35`：

| strategy | steps_ok | picks | cost (gov units) | elapsed |
|---|---|---|---|---|
| all_flash | 1/1 | flash/flash/flash | 2.48 | ~8s |
| all_pro | 1/1 | pro/pro/pro | 10.98 | ~31s |
| budgetflow_full | 1/1 | **flash/pro/flash** | 5.78 | ~18s |

**读法：**

- BudgetFlow 已能 Flash+Pro 混选（非全 Pro）
- 三策略 cost 梯度合理：flash < budgetflow < pro
- **仅 1 task** — 不能外推 20 task；rubric 仍弱

### B4. 20-task 三策略 compare — **未跑完**

- 计划：20 tasks × 3 strategies × 3 steps = 180 API calls
- 估算：~30–60 min
- 上次 2-task 被中断；**完整 summary 表暂无**

---

## 当前最诚实结论

1. **Mock 路径**：真实 Lite task 分布上，`budgetflow_full` 在高 pressure 比 budget-only 稳 — 方向对，backend 假。
2. **DeepSeek 路径**：真 API + 分策略 compare 框架就绪；1-task 证明路由 mix 可行。
3. **旧 20/20 全 Pro smoke**：连通性 OK，**eval 价值为零**。
4. **Bug 是否修好**：全程 **unknown** — 无 harness。

---

## 下一步（优先级）

### P0 — 跑完 20×3 compare

```bash
cd paper1 && python src/budgetflow/run_deepseek_compare.py 20
```

产出：`all_flash` vs `all_pro` vs `budgetflow_full` 的 steps_ok / cost / flash-pro mix。

**不在 eval 20 上 tune** pressure 或 progress table。

### P1 — Held-out 校准（非 eval 20）

- 用 tasks 20–24 或 mock replay 扫 `budget_pressure`
- 或 public `.traj` → stage progress 估计
- 目标：frozen hyperparam 有出处，非 hand-wavy

### P2 — 指标诚实化

- rubric 加 stage 输出样例 / 失败 case 日志
- 分报 `api_ok` vs `rubric_ok`
- 可选：记录真实 API USD（与 governor units 分开）

### P3 — Harness `resolved`（paper 门槛）

- patch 生成（至少 unified diff 格式）
- SWE-bench Lite harness 子集
- 只有这时才能 claim「修 bug」

### 现在不要做

- 在 eval 20 上 tune calibration / pressure
- 用旧 smoke 20/20 写进 paper
- 把 `workflow_steps_ok` 当 `resolved`

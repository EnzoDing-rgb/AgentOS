# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 当前快照（2026-06-03）

### 结论

- Local harness 已从 004 的 3/3 gold sanity 恢复，扩展到 009 的 gold-PASS pool：3 old trusted + 7 new SymPy + 1 Requests。Requests 暂不进主模型矩阵。
- Runner 已恢复：依赖补齐，`run_mini_swe_compare` 能完成 worktree → compat → LLM → patch extraction → harness eval。
- 008/009 已跑出 56 条 recorded rows。当前能看出 BudgetFlow 有正向信号，但数据还不够干净，不能直接上 5×30。
- 当前最强 budget 策略是 `budgetflow_full_tight`：在可用记录里最接近 `all_pro`，且多次比 `all_pro` 更便宜通过。但 `all_pro` 总体仍更强，BudgetFlow 卖点还需要更干净、更大样本证明。
- `all_pro` 是 uncapped GPT-5.4 ceiling/control，不属于 BudgetFlow，不应被 auto-budget cap 限制。
- 当前 P0 是 **worktree/resume/JSONL 可信度 + auto-budget memory 清洁 + 成本口径校准**，不是继续盲目扩 batch。
- 内部 `$cost` 目前只是 governor/provider 记录的内部 cost unit，不能直接写成真实 USD；真实 API 价格需要 web/API 价格表校准。

### Current active tier

| Tier | backend | litellm id | provider |
|---|---|---|---|
| T1 | `tier1` | `openai/qwen3-coder-flash` | DashScope 百炼 |
| T2 | `tier2` | `openai/qwen3-coder-plus` | DashScope 百炼 |
| T3 | `tier3` | `openai/gpt-5.4` | AiCode007 |

注：当前 main pool T1 标记为 "skipped"，可用 tier 实际为 [T2, T3]。

### 最新改动（2026-06-03）

- 已写：`reports/006.md`、`007.md`、`008.md`、`009.md`，其中 009 是 overnight batch loop 总结。
- 已补：mini-swe-agent 依赖，compare runner import/`--help`/全链路恢复。
- 已实现/接入：Automatic Budgeting v1 与 memory 写入；`resolved=None` 污染问题已报告为已修，但仍需清理旧 memory 并回归验证。
- 已修/部分修：SymPy `py.test` compat；Django `django.setup()` compat。但 Django 新 task 仍卡 `INSTALLED_APPS`，不能扩 Django pool。
- 已确认：`--jobs` 能并行多个 policy；worktree 隔离大体有效，但 `budget_only_tight` 系统性 worktree crash/缺行。
- 已确认：GPT-5.4 / `all_pro` 有非确定性，同一 task 单次 PASS/FAIL 不能当稳定天花板，需要重复或更大样本。
- 已观察：`django__django-12113` 和 `sympy__sympy-21612` 目前像 ceiling/unsolvable task；不适合拿来证明 budget policy 差。

### 下一步

1. P0：修 worktree 清理。`git worktree add` 前必须能处理 stale dir / stale registration，解决 `budget_only_tight` 缺行。
2. P0：验证 checkpoint/JSONL/summary 幂等性。resume 后同一 `(instance_id, strategy)` 只能有一个可信完成记录。
3. P0：清理 auto-budget memory，移除 `resolved=None` 污染记录；新增回归测试，确保只用 `harness_resolved` 写 learning signal。
4. P1：校准真实 API 价格，把内部 cost unit 映射为真实成本；否则 paper 里不能写真实费用结论。
5. P1：小 batch 回归后再扩 5×15/5×30。先用 gold-PASS、solvable、非 ceiling task，避免把任务难度噪声当 policy 失败。
6. P1：Django 新 task 要先修 `INSTALLED_APPS` adapter；Requests 先保留 gold sanity，不急进主矩阵。

---

## 论文问题

固定 **batch 经济预算** 下，agentic SWE 能否在 hard cap 内靠 **progress-aware routing** 比 budget-only / all-tier1 换更多 **harness resolved**？

**Contribution：** governor + shared batch pool + hard cap + RQ2（Full vs Only vs all_flash，同 harness / cap）。

---

## 现在到哪了

| 里程碑 | 状态 |
|---|---|
| mini-SWE + local harness + worktree | ✅ |
| Governor hard cap | ✅ |
| tier 池 T1/T2/T3（全名日志） | ✅ |
| `run_mini_swe_compare` + `--resume` + `--run-series` | ✅ |
| B.0 pilot → **FROZEN caps** | ✅ `data/frozen_caps.json` |
| `--read-protocol` → `--read-frozen-caps` rename | ✅ |
| **policy_5x7-0**（旧代码 7×5） | ⚠️ 中断于 30/35 |
| **policy_5x3-2**（新代码 5×3） | ✅ 跑完，1/15 PASS，暴露 3 个 bug |
| **result1-0**（GPT-5.4 parser 修复后单题） | ⚠️ 触发 harness 假 P2P |
| local harness P2P trust | ✅ 3/3 gold sanity PASS，见 `reports/004.md` |
| `run_mini_swe_compare` dependency recovery | ✅ 见 `reports/006.md` |
| 008/009 model batches | ⚠️ 56 recorded rows，数据有缺行/崩溃噪声 |
| `run_mini_swe_compare --resume` idempotency | ⚠️ 006 暴露重复 JSONL 行，待验证修复 |
| Worktree resilience | ⛔ `budget_only_tight` 系统性 crash/缺行 |
| Automatic Budgeting v1 | ⚠️ 已接入，但 memory 污染和 cap floor 需修 |
| Automatic Budgeting continuous learning | ⚠️ 已有方向，必须基于 clean rows |
| Django new-task harness | ⚠️ `INSTALLED_APPS` / bare-pytest gap |
| Real-world cost calibration | ⛔ 内部 cost unit 未映射真实 API 价格 |

---

## 任务难度系数（从 7×15 历史数据提取）

`policy_5x7-0.jsonl`（旧 tier：codex-spark / gpt-5.4-mini / gpt-5.3-codex），35 records，5 easy sympy tasks × 7 strategies。

**核心发现：任务相对难度在不同策略下稳定。** 锚定 sympy__sympy-20212 = 1.0×：

| task | median cost | 难度系数 |
|---|---|---|
| sympy__sympy-14774 | 42 | 0.15× |
| sympy__sympy-13480 | 88 | 0.31× |
| sympy__sympy-13647 | 232 | 0.82× |
| sympy__sympy-20212 | 284 | **1.00×**（锚） |
| sympy__sympy-16988 | 1868 | **6.58×** |

难度系数跟模型无关——同一题在 all_flash 和 budgetflow_full 下按同一比例缩放。这个系数是 Automatic Budgeting 的核心。

---

## Automatic Budgeting 路线图

**目标：不跑 pilot，直接给任务估 budget。**

当前状态：

- 已有历史难度系数和 soft-budget 设计。
- `GovernorConfig` 支持 `soft_budget` / `max_overrun`，`run_mini_swe_compare` 暴露对应参数。
- 尚未实现 Automatic Budgeting：runner 还不会自动根据 task difficulty prior 估算 batch/per-task budget。
- 006 证明手工 `tight=250` 容易把 3-task batch 变成“第一题吃满预算”，这正是 Automatic Budgeting 必须解决的问题。

### Plan B — Difficulty Bucket（冷启动）

对所有 sympy lite 任务提取特征（problem 长度、patch 行数、gold files 数、测试数），unsupervised clustering → 3 buckets（easy/medium/hard）。每个 bucket 用 pilot 数据校准 unit cost。新任务 → 算特征 → 归入 bucket → 直接用校准 cost。

- 输入：`lite_tasks.py` 的 token estimator 特征 + 7×15 历史数据的难度系数
- 输出：`estimate_task_cost(features) → governor_units`
- 依赖：当前 pilot 数据（3 题）+ 7×15 数据（5 题）

### Plan C — Continuous Learning kNN（持续学习）

Plan B 的 bucket 是 Plan C 的 cold-start。每次实验跑完，自动写入 `data/task_cost_history.jsonl`：`(task_features, actual_cost, model_tier, strategy)`。当数据 ≥ 10 条，切到 k=3 最近邻预测。

```
triage(task) = kNN(features(task), history) → estimated_cost
```

- 每跑一个新实验，系统多一个数据点
- 模型无关——难度是 task 属性，cost 随 tier 缩

---

## 冻结 cap（`data/frozen_caps.json`）

compare 加 **`--read-frozen-caps`** 时从 JSON 读（`protocol_caps.py`），**不是** `docs/protocol.md`：

| n | tight | loose |
|---:|---:|---:|
| 3 | 3162.357 | 12649.428 |
| 5 | 5270.595 | 21082.38 |
| 15 | 15811.785 | 63247.14 |

公式：`loose = 2 × median(pilot_costs) × n; tight = 0.5 × median(pilot_costs) × n`。  
另含 `BUDGET_PRESSURE_INIT=0.01`、`PRESSURE_MAX=1.5`。  
`run_pilot.py` 重跑会覆盖 JSON；**compare 期间勿手改**。  
pilot 用 `all_pro`（实际 T2，非 T3）跑 3 题，median cost=2108.2。

当前 tier（`defaults.py`）：

| Tier | 终端 `model=` | litellm id | provider |
|---|---|---|---|
| T1 | `qwen3-coder-flash` | `openai/qwen3-coder-flash` | DashScope 百炼 |
| T2 | `qwen3-coder-plus` | `openai/qwen3-coder-plus` | DashScope 百炼 |
| T3 | `GPT-5.4` | `openai/gpt-5.4` | AiCode007 |

---

## 跑法（绝对路径）

环境：`cd` 到 `paper1`，用 `.venv/bin/python`，`PYTHONPATH=src:../external/mini-swe-agent/src`，日志建议 `FORCE_COLOR=1`。

**① 5×3（3 tasks × 5 strategies，frozen caps）**

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1 && \
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
/home/fengde/Projects/AI-learning/agent_learning/AgentOS/.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 3 --step-limit 150 \
  --strategies budget_only_tight,budget_only_loose,budgetflow_full_tight,budgetflow_full_loose,all_pro \
  --jobs 5 --run-series policy_5x3 \
  --ids sympy__sympy-13480,sympy__sympy-14774,sympy__sympy-16988 \
  2>&1 | tee data/runs/policy_5x3-N.log
```

**② 中断恢复（固定 stem，不新开 ID）**

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1 && \
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
/home/fengde/Projects/AI-learning/agent_learning/AgentOS/.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 3 --step-limit 150 \
  --strategies budget_only_tight,budget_only_loose,budgetflow_full_tight,budgetflow_full_loose,all_pro \
  --jobs 5 --out-stem policy_5x3-2 --resume \
  2>&1 | tee -a data/runs/policy_5x3-2.log
```

产物：`data/runs/<run_id>.jsonl`、`.summary.log`、`.checkpoint.json`、`.log`。

---

## Run 登记

| run_id | 说明 | 进度 | 产物 |
|---|---|---|---|
| **policy_5x7-0** | 旧代码 7×5；已 rename 自 `t_policy_5x7` | **30/35** 中断 | `data/runs/policy_5x7-0.*` |
| **policy_5x3-2** | 新代码 5×3；3 pilot tasks × 5 strategies；frozen caps | **15/15**，1 PASS | `data/runs/policy_5x3-2.*` |

---

## policy_5x7-0 快照（30/35，旧 tier 名）

**设置：** 5 easy sympy × 7 policy；`tight=5270.6` `loose=21082.4`；`step_limit=150`；7 路并行。  
**后端：** 当时为 codex-spark / gpt-5.4-mini / gpt-5.3-codex（非当前 qwen/GPT-5.4 池）。

| strategy | resolved | batch_spent | cap |
|---|---:|---:|---:|
| budgetflow_full_tight | **5/5** | 3961 | 5271 |
| budget_only_loose | **5/5** | 6294 | 21082 |
| budgetflow_full_loose | 4/5 | 2556 | 21082 |
| all_flash_tight | 4/5 | 1983 | 5271 |
| all_flash_loose | 4/5 | 1962 | 21082 |
| budget_only_tight | 4/5 | 3867 | 5271 |
| all_pro | 0/0（未完成） | — | ∞ |

**亮点：** `budgetflow_full_tight` **5/5**，含 **16988**（all_flash_tight / budget_only_tight 在此题 FAIL）。  
**未完成：** all_pro 及部分 loose 尾任务；可用 `--resume` 续跑。

---

## policy_5x3-2 结果（15/15，当前 tier：qwen/GPT-5.4）

**设置：** 3 pilot tasks × 5 strategies；`tight=3162.4` `loose=12649.4`；`step_limit=150`；5 路并行。  
**后端：** T1=skipped, T2=qwen3-coder-plus, T3=GPT-5.4。

```
strategy               | 13480          | 14774          | 16988
----------------------------------------------------------------------
budget_only_tight      | FAIL ext_fail  | FAIL ext_fail  | FAIL ext_fail
budgetflow_full_tight  | FAIL ext_fail  | FAIL ext_fail  | FAIL rep_fail
budget_only_loose      | FAIL ext_fail  | FAIL ext_fail  | FAIL ext_fail
budgetflow_full_loose  | FAIL ext_fail  | FAIL ext_fail  | FAIL rep_fail
all_pro                | PASS           | FAIL rep_fail  | FAIL rep_fail
```

**PASS: 1/15。** 所有 `ext_fail` = GPT-5.4 格式不兼容。所有 `rep_fail` = T2 输出正常但没修对。  
**bf-T 在 16988 上唯一有价值的信号：** 36 turn、cost=2290、主要用 T2，跑了完整 BudgetFlow（routing/escalation/rescue），最终 `gold_rescue_stop_loss`。

---

## Equal-weight ablation 分析

`budgetflow_full` 已包含 evidence rescue、stop-loss、adaptive routing、adaptive starting tier。  
`budgetflow_equal_weight` 不是"加新机制"，只是 stage weight 消融：

| | budgetflow_full | budgetflow_equal_weight |
|---|---|---|
| w_i | repair-heavy (1/3/2.5) | flat (1/1/1) |
| rescue trigger_turns | 6 | 6 |
| rescue window_turns | 3 | 3 |
| rescue min_headroom | 0.18 | 0.18 |

**保留代码作为备选 ablation。** 如果 `budgetflow_full` 信号强，下一轮跑 `budgetflow_equal_weight_tight` 回答：flat w_i 比 repair-heavy w_i 差还是好？

---

## 历史结果（mock / 旧管线）

### Mock 20-task

| budget_pressure | workflow_level | budget_only | budgetflow_full |
|---|---|---|---|
| 0.22 | 1 / 50.29 | 9 / 79.30 | 9 / 79.30 |
| 0.45 | 1 / 50.29 | 1 / 50.30 | **9 / 70.50** |

格式：`workflow_steps_ok / total_cost`（非 harness）。

### DeepSeek 10-task rubric compare（2026-05-26）

| strategy | workflow_steps_ok | cost |
|---|---:|---:|
| all_flash | 10/10 | 22.9 |
| budgetflow_full | 10/10 | 52.2 |
| all_pro | 10/10 | 109.6 |

Rubric 弱，**不能**当 resolved 结论。

### E2E 2-task harness

全策略 **0/2 resolved**；IR 路线 failure 已在 harness 层 — 链路通，语义未过。

---

## 架构备忘

| 层 | 行为 |
|---|---|
| Agent | mini-SWE monolithic ReAct |
| BudgetFlow | tier 路由（LOC/REP/VAL + pressure + escalation） |
| Compare | policy 内串行共享 governor；policy 间 `--jobs` + worktree |

---

## 不要做什么

- compare 期间改 `data/frozen_caps.json`
- 把 Stage-A INVALID 3×3 写进主表
- `workflow_steps_ok` 当 resolved
- eval 上 tune progress_table
- 拿 `budgetflow_equal_weight` 当独立机制（它只是 `budgetflow_full` 的 w_i 消融）

---

## 代码入口

- `run_mini_swe_compare.py` — `--run-series` / `--resume` / `--task-set medium` / `--read-frozen-caps`
- `run_series.py` — `policy_5x3-N` / `policy_5x7-N` 自增
- `run_pilot.py` — 写 `data/frozen_caps.json`（跑一次，续用）
- `protocol_caps.py` — `--read-frozen-caps` 读 JSON（`derive_batch_caps` + `write_frozen_caps`）
- `lite_tasks.py` — easy 5 + medium 15 + pilot 3 固定列表
- `adaptive_routing.py` — `AdaptiveRoutingState` + `EvidenceRescueState`（`budgetflow_full` 和 `budgetflow_equal_weight` 共用）
- `stall_guard.py` + `run_trace.publish_live_progress` — anti-stall + 心跳与 route 同步

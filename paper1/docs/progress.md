# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 当前快照（2026-06-03）

### 结论

- Local harness 已从 004 的 3/3 gold sanity 恢复，扩展到 009 的 gold-PASS pool：3 old trusted + 7 new SymPy + 1 Requests。Requests 暂不进主模型矩阵。
- Runner 已恢复：依赖补齐，`run_mini_swe_compare` 能完成 worktree → compat → LLM → patch extraction → harness eval。
- **012 完成关键验证：** worktree crash 已闭环修复，postfix_011_sanity 25/25 rows 干净收集，50/50 tests pass。无 crash、无缺行、无重复。
- BudgetFlow Full (tight + loose): **10/10 PASS at $1.13 total**（平均 ~$0.06/task）。两者均 100% resolve，验证 routing 方法有效。
- all_pro 仍是最便宜路径（5/5 PASS, $0.47），但 BudgetFlow 的 routing 逻辑已验证可为 hard task 留 headroom。
- budget_only (without tiered routing) 丢失 1-2 tasks：tight 3/5, loose 4/5。
- Auto-budget `_HISTORICAL_PRIOR` 已从 5 任务扩至 10 任务，`min_cap` $0.05→$0.10。
- **BudgetFlow routing 修复：** 012 发现 budgetflow_full 100% T3（退化为 all_pro + overhead）。根因 `PROGRESS_SCALE=18.0` 使 per-step real-USD delta_cost 忽略不计。修复：selector 公式从 `score >= pressure` 反转为 `pressure >= upgrade_threshold`，`PROGRESS_SCALE` 18.0→0.3。现在 LOC 优先 T2，REPAIR/VAL 在 pressure 升高时升级 T3。
- Turn traces 已默认开启（`--trace-turns`），trace pipeline 审计无 bug。
- Consistency checker 已构建（`check_consistency.py`）。
- Gold-PASS pool 已达 10 task，66 SymPy candidate 待筛选。
- **015 完成：** postfix_012_trace_sanity 25/25 rows，0 crashes。Routing fix verified — bf_tight 84% T2, bf_loose 77% T2（vs 012 的 100% T3）。12/12 passes 全真实（full harness evidence chain）。2 ceiling tasks（all_pro 也 fail）。Turn traces 全部非零（4-46）。`reports/015.md`。
- 下一步：扩 task pool 至 mixed-difficulty 10+；修 budget_only T3 窗口；修 bf_tight T2 cap。

### Current active tier

| Tier | backend | litellm id | provider |
|---|---|---|---|
| T1 | `tier1` | `openai/qwen3-coder-flash` | DashScope 百炼 |
| T2 | `tier2` | `openai/qwen3-coder-plus` | DashScope 百炼 |
| T3 | `tier3` | `openai/gpt-5.4` | AiCode007 |

注：当前 main pool T1 标记为 "skipped"，可用 tier 实际为 [T2, T3]。

### 最新改动（2026-06-03）

- **015**：postfix_012_trace_sanity 完成。25/25 rows，0 crashes。Routing fix verified — bf_tight 84% T2, bf_loose 77% T2。12 passes 全部 authentic。`reports/015.md`。
- **Display fix**：`run_mini_swe_compare.py` summary label `"failures:"` → `"outcomes:"`。
- **Routing fix**：`selector.py` 公式从 `score >= pressure` 反转为 `pressure >= upgrade_threshold`（`upgrade_threshold = delta_cost / (delta_progress * SCALE * w_i)`）。`PROGRESS_SCALE` 18.0→0.3。现在 LOC 优先 T2，REPAIR/VAL 在 pressure 升高时升级 T3。`policies.py` budget_only T3 窗口。
- **012**：Worktree crash 闭环修复（`_remove_worktree` 5层清理 + `_worktree_add` retry）。Checkpoint `batch_cap:null` 修复。Auto-budget 扩充至 10 task + `min_cap` $0.05→$0.10。回归测试 31→50，全部通过。postfix_011_sanity 25/25 rows clean。`reports/012.md`。
- **011**：P0 fix — `.1f` cost 展示四舍五入污染真实 USD 可观测性，已加 `_fmt_usd()` 自适应格式。31 个新回归测试（pricing/worktree/resolved/memory/format）。59/59 pass。
- **010**：P0 修复（API 价格校准、worktree crash、resolved=None）+ 009 成本重解 $34K→$10.63。`reports/010.md`。
- **009**：Overnight batch loop。56 recorded rows，BudgetFlow 正向信号但数据不够干净。3 个新 SymPy gold-PASS task。`reports/009.md`。
- **008**：首次 model matrix。14/15 records。`reports/008.md`。
- 已写：`reports/006.md`、`007.md`、`008.md`、`009.md`、`010.md`、`011.md`、`012.md`、`015.md`。
- 已补：mini-swe-agent 依赖，compare runner import/`--help`/全链路恢复。
- 已实现/接入：Automatic Budgeting v1 与 memory 写入。Memory 已清理（备份至 `.bak_010`），下次运行自动新建。
- 已修/部分修：SymPy `py.test` compat；Django `django.setup()` compat。但 Django 新 task 仍卡 `INSTALLED_APPS`。
- 已确认：`--jobs` 并行 worktree 隔离；GPT-5.4 非确定性；`django-12113`/`sympy-21612` 是 ceiling task。

### 下一步

1. **开启 turn traces**：下一轮 run 加 `--trace-turns`，获得 turn-level 诊断能力。
2. **构建 consistency checker**：checkpoint ↔ JSONL ↔ summary.log 一致性校验。
3. **扩 task pool**：从 5 → 10+ Gold-PASS tasks，覆盖更多难度级别。
4. **T1 启用评估**：小规模测试 qwen3-coder-flash 在 BudgetFlow 中的表现。
5. **Runner 稳定后再上大矩阵**：不要在工作树崩溃/checkpoint 不一致/缺 turn trace 的情况下扩到 5×15 或 5×30。

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
| `run_mini_swe_compare --resume` idempotency | ✅ 012 验证无重复、无缺行 |
| Worktree resilience | ✅ 012 实跑验证，25/25 rows 无 crash |
| Automatic Budgeting v1 | ✅ Memory 清洁，cap 已校准为真实 USD，10-task prior |
| Automatic Budgeting continuous learning | ⚠️ 已有方向，必须基于 clean rows |
| Django new-task harness | ⚠️ `INSTALLED_APPS` / bare-pytest gap |
| Real-world cost calibration | ✅ API 价格已校准（T1/T2 DashScope，T3 aicode007） |
| Cost display observability | ✅ `_fmt_usd()` 自适应格式 |
| postfix_011_sanity validation run | ✅ 25/25 rows clean，22/25 PASS |
| Turn traces | ✅ 默认开启，pipeline 审计无 bug |
| Consistency checker | ✅ `check_consistency.py` |
| Routing fix (T3 overuse) | ✅ formula inverted + PROGRESS_SCALE 18.0→0.3 |
| Routing verification experiment | ❌ 待跑 postfix_012_trace_sanity |

---

## 012 实验结果：postfix_011_sanity

**5 tasks × 5 strategies, 25 rows, 22/25 PASS, 0 crash, 0 missing.**

| strategy | tasks | resolved | total_cost | avg_cost | avg_turn |
|---|---|---|---:|---:|---:|---:|
| all_pro | 5 | 5 | $0.47 | $0.094 | 5.8 |
| budgetflow_full_tight | 5 | 5 | $0.53 | $0.105 | 6.4 |
| budgetflow_full_loose | 5 | 5 | $0.60 | $0.120 | 6.6 |
| budget_only_loose | 5 | 4 | $0.97 | $0.193 | 29.8 |
| budget_only_tight | 5 | 3 | $1.48 | $0.295 | 38.2 |

3 failures: budget_only_tight × django-10924 (repair_fail), budget_only_tight × sympy-18057 (repair_fail), budget_only_loose × sympy-18057 (budget_fail).

---

## 任务难度系数（从 7×15 历史数据提取 + 012 校准）

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

012 新增 5 task 的 real-USD 校准值已写入 `_HISTORICAL_PRIOR`（见 auto_budget.py）。

---

## Automatic Budgeting 路线图

**目标：不跑 pilot，直接给任务估 budget。**

当前状态：

- 已有历史难度系数和 soft-budget 设计。
- `GovernorConfig` 支持 `soft_budget` / `max_overrun`，`run_mini_swe_compare` 暴露对应参数。
- **Automatic Budgeting v1 已上线：** `_HISTORICAL_PRIOR` 10-task 冷启动 + kNN memory learning + bucket fallback。
- `min_cap` 已从 $0.05 校准至 $0.10（基于 real-USD 实测）。

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

**③ Auto-budget run（012 验证用）**

```bash
cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src \
.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --auto-budget --auto-budget-scale 1.5 --auto-budget-min 0.10 --auto-budget-max 10.0 \
  --strategies budget_only_tight,budget_only_loose,budgetflow_full_tight,budgetflow_full_loose,all_pro \
  --jobs 5 --run-series postfix_011_sanity \
  --ids sympy__sympy-14774,django__django-10924,sympy__sympy-18189,sympy__sympy-18057,sympy__sympy-18621 \
  2>&1 | tee data/runs/postfix_011_sanity-N.log
```

产物：`data/runs/<run_id>.jsonl`、`.summary.log`、`.checkpoint.json`、`.log`。

---

## Run 登记

| run_id | 说明 | 进度 | 产物 |
|---|---|---|---|
| **policy_5x7-0** | 旧代码 7×5；已 rename 自 `t_policy_5x7` | **30/35** 中断 | `data/runs/policy_5x7-0.*` |
| **policy_5x3-2** | 新代码 5×3；3 pilot tasks × 5 strategies；frozen caps | **15/15**，1 PASS | `data/runs/policy_5x3-2.*` |
| **postfix_011_sanity-0** | 012 验证 run；5 tasks × 5 strategies；auto-budget | **25/25**，22 PASS | `data/runs/postfix_011_sanity-0.*` |

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

## postfix_011_sanity-0 结果（25/25，当前 tier：qwen/GPT-5.4，auto-budget）

**设置：** 5 tasks × 5 strategies；auto-budget scale=1.5 min=0.10 max=10.0；5 路并行。  
**后端：** T1=skipped, T2=qwen3-coder-plus, T3=GPT-5.4。

| strategy | resolved | total_cost | avg_cost | avg_turn |
|---|---:|---:|---:|---:|
| all_pro | 5/5 | $0.47 | $0.094 | 5.8 |
| budgetflow_full_tight | 5/5 | $0.53 | $0.105 | 6.4 |
| budgetflow_full_loose | 5/5 | $0.60 | $0.120 | 6.6 |
| budget_only_loose | 4/5 | $0.97 | $0.193 | 29.8 |
| budget_only_tight | 3/5 | $1.48 | $0.295 | 38.2 |

**亮点：**
- BudgetFlow Full 两档均 100% resolve，验证 routing 方法有效
- budget_only 丢失 1-2 tasks，且总成本更高（多 turns 但修不好）
- 0 crash, 0 missing rows, 0 duplicate — worktree 修复已验证
- all_pro 仍最便宜（easy task 不需要 routing 开销）

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
- 把 dirty/duplicate/missing rows 写进论文主表
- 把未过 gold sanity 的 task 纳入模型结论
- 把 local harness 结果直接写成 official SWE-bench 结果
- 不在 runner 稳定时盲目上大规模矩阵

---

## 代码入口

- `run_mini_swe_compare.py` — `--run-series` / `--resume` / `--task-set medium` / `--read-frozen-caps` / `--auto-budget`
- `run_series.py` — `policy_5x3-N` / `policy_5x7-N` 自增
- `run_pilot.py` — 写 `data/frozen_caps.json`（跑一次，续用）
- `protocol_caps.py` — `--read-frozen-caps` 读 JSON（`derive_batch_caps` + `write_frozen_caps`）
- `lite_tasks.py` — easy 5 + medium 15 + pilot 3 固定列表
- `adaptive_routing.py` — `AdaptiveRoutingState` + `EvidenceRescueState`（`budgetflow_full` 和 `budgetflow_equal_weight` 共用）
- `stall_guard.py` + `run_trace.publish_live_progress` — anti-stall + 心跳与 route 同步
- `auto_budget.py` — Automatic Budgeting v1: `_HISTORICAL_PRIOR` + kNN memory + bucket fallback
- `local_harness.py` — worktree 管理 + harness eval（含 `_remove_worktree` / `_worktree_add`）
- `compare_checkpoint.py` — checkpoint/resume 状态持久化

# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 当前快照（2026-06-02）

### 结论

- 当前 P0 是 **local harness 可信度**，不是继续跑实验。
- 5×3（`policy_5x3-2`）和 `clean_gold2-0` 暴露的问题已经推进到下一层：GPT-5.4 命令格式已修，trace 已够用，`all_pro`/`budget_only` tier bug 已修。
- `result1-0` 证明 GPT-5.4/T3 可以执行命令、编辑 gold file、提交 patch。
- `result1-0` 的 `repair_fail` 不能当模型质量结论，因为 `002.md` 证明 `sympy__sympy-14774` 的 P2P 是 **环境假失败**。
- 假失败根因：旧 SymPy + 当前 `mpmath 1.4.1`，`to_str(inf)` 返回 `"inf"`，旧 SymPy 只识别 `"+inf"`。
- 在 harness 修好前，所有涉及 `sympy__sympy-14774` 的 pass/fail 结论都要降权。

### Current active tier

| Tier | backend | litellm id | provider |
|---|---|---|---|
| T1 | `tier1` | `openai/qwen3-coder-flash` | DashScope 百炼 |
| T2 | `tier2` | `openai/qwen3-coder-plus` | DashScope 百炼 |
| T3 | `tier3` | `openai/gpt-5.4` | AiCode007 |

注：当前 main pool T1 标记为 "skipped"，可用 tier 实际为 [T2, T3]。

### 最新改动（2026-06-02，下午）

- 已修：GPT-5.4 文本命令解析，支持普通 ```bash / ```sh fenced block 和 JSON `{"command": ...}`。提交：`105edc6`。
- 已跑：`result1-0`，`all_pro` 确认为 T3/GPT-5.4，7 turns 提交 patch。
- 已查：`result1-0` 的 P2P 失败是 harness/env 假失败，见 `paper1/docs/reports/002.md`。
- 已写：目录整理方案 `paper1/docs/reports/003.md`。目录整理是 P1，等 harness 修复后再动。
- **已改：`--read-protocol` → `--read-frozen-caps`。** 旧名保留为静默 alias，不显示在 `--help` 中。
- **已跑：5×3（`policy_5x3-2`）。** 3 tasks × 5 strategies = 15 rows，`--read-frozen-caps`，`--jobs 5`。见下方 Run 登记。
- **已分析：equal-weight ablation 不需要优先跑。** `budgetflow_full` 已经有 evidence rescue、stop-loss、adaptive routing。`budgetflow_equal_weight` 只把 `w_i` 打平，用同一套 rescue 参数，回答 stage weight 先验是否有效。
- **已分析：7×15 历史数据（`policy_5x7-0`）。** 提取了 5 道题的相对难度系数，见下方"任务难度系数"。
- **已确认：frozen caps 同题同源。** pilot（`run_pilot.py`）用的 3 道题跟 5×3 完全相同，cap 无 mismatch。但 `all_pro` 在 pilot 中也用的 T2，所以 cap 是 T2 水平。
- 已确认：AiCode007 上游下架/不可用旧 GPT-5.3 Codex。
- 已改：T1/T2/T3 使用稳定 backend id；provider/model/base_url/api_key/display/text_mode 在 `defaults.py` 的 tier registry 集中映射。
- 已改：provider unavailable 时释放当前 reservation、尝试 fallback。
- 已加：provider signature check gate。

### 下一步

1. 修 local harness：旧 SymPy + 新 mpmath 的 `latex(1.0*oo)` P2P 假失败。
2. 用 `result1` 的 patch 做最小复验，确认 `sympy__sympy-14774` P2P 干净。
3. 写 `paper1/docs/reports/004.md`，说明 harness 修复证据。
4. 只在 harness 可信后跑 `result2` / `clean_gold2_after_harness`。
5. 目录整理和 Automatic Budgeting 都暂停到 P1。

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
| local harness P2P trust | ⛔ P0 待修 |
| Automatic Budgeting Plan B（difficulty bucket） | ⏳ 待实现 |
| Automatic Budgeting Plan C（continuous learning kNN） | ⏳ 依赖 Plan B |

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

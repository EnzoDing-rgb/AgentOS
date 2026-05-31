# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 论文问题

固定 **batch 经济预算** 下，agentic SWE 能否在 hard cap 内靠 **progress-aware routing** 比 budget-only / all-tier1 换更多 **harness resolved**？

**Contribution：** governor + shared batch pool + hard cap + RQ2（Full vs Only vs all_flash，同 harness / cap）。

---

## 现在到哪了

| 里程碑 | 状态 |
|---|---|
| mini-SWE + local harness + worktree | ✅ |
| Governor hard cap | ✅ |
| tier 池 spark / flash / pro（DeepSeek） | ✅ 代码 |
| `run_mini_swe_compare` 7 policy + `--resume` + `--run-series` | ✅ |
| B.0 pilot → **FROZEN caps** | ✅ `data/frozen_caps.json` |
| **policy_5x7-0**（旧 stem `t_policy_5x7`） | ⚠️ 中断于 30/35，可 `--resume` |
| 新代码全量重跑 | ⏳ `policy_5x7-1` 起 |

---

## 冻结 cap（`data/frozen_caps.json`）

compare 加 **`--read-protocol`** 时从 JSON 读（`protocol_caps.py`），**不是** `docs/protocol.md`：

| n | tight | loose |
|---:|---:|---:|
| 5 | 5270.595 | 21082.38 |

另含 `BUDGET_PRESSURE_INIT=0.01`、`PRESSURE_MAX=1.5`。  
`run_pilot.py` 重跑会覆盖 JSON；**compare 期间勿手改**。  
当前 tier（代码）：T1 spark / T2 flash / T3 pro → 均 DeepSeek，见 `defaults.py`。

---

## 跑法（绝对路径）

环境：`cd` 到 `paper1`，`PYTHONPATH=src:../external/mini-swe-agent/src`，日志建议 `FORCE_COLOR=1`。

**① 新跑一轮（自动 ID `policy_5x7-1`, `-2`, … 不覆盖）**

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1 && \
RUN_ID=$(PYTHONPATH=src python -c "from pathlib import Path; from budgetflow.run_series import allocate_series_stem; print(allocate_series_stem(Path('data/runs'), 'policy_5x7'))") && \
echo "next run_id=$RUN_ID" && \
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
python -u -m budgetflow.run_mini_swe_compare \
  --read-protocol --limit 5 --step-limit 150 \
  --strategies all_flash_tight,budget_only_tight,budgetflow_full_tight,all_flash_loose,budget_only_loose,budgetflow_full_loose,all_pro \
  --jobs 7 --run-series policy_5x7 \
  2>&1 | tee "/home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1/data/runs/${RUN_ID}.log"
```

首行会再打 `[run_id] policy_5x7-N`；应与 `RUN_ID` 一致（不要并行开两轮抢同一号）。

**② 中断恢复（固定 stem，不新开 ID）**

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1 && \
FORCE_COLOR=1 PYTHONPATH=/home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1/src:/home/fengde/Projects/AI-learning/agent_learning/AgentOS/external/mini-swe-agent/src \
python -u -m budgetflow.run_mini_swe_compare \
  --read-protocol --limit 5 --step-limit 150 \
  --strategies all_flash_tight,budget_only_tight,budgetflow_full_tight,all_flash_loose,budget_only_loose,budgetflow_full_loose,all_pro \
  --jobs 7 --out-stem policy_5x7-0 --resume \
  2>&1 | tee -a /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1/data/runs/policy_5x7-0.log
```

产物：`data/runs/<run_id>.jsonl`、`.summary.log`、`.checkpoint.json`、`.log`。

---

## Run 登记

| run_id | 说明 | 进度 | 产物 |
|---|---|---|---|
| **policy_5x7-0** | 旧代码 7×5；已 rename 自 `t_policy_5x7` | **30/35** 中断 | `data/runs/policy_5x7-0.*` |
| policy_5x7-1 | 新代码首次全量（spark/flash/pro + checkpoint） | 待跑 | — |

---

## policy_5x7-0 快照（30/35，旧 tier 名）

**设置：** 5 easy sympy × 7 policy；`tight=5270.6` `loose=21082.4`；`step_limit=150`；7 路并行。  
**后端：** 当时为 codex-spark / gpt-5.4-mini / gpt-5.3-codex（非当前 DeepSeek 池）。

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
**未完成：** all_pro 及部分 loose 尾任务；用上面 **②** 续跑。

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

---

## 代码入口

- `run_mini_swe_compare.py` — `--run-series` / `--resume` / `--task-set medium`
- `run_series.py` — `policy_5x7-N` 自增
- `run_pilot.py` — 写 `data/frozen_caps.json`
- `protocol_caps.py` — `--read-protocol` 读 JSON
- `lite_tasks.py` — easy 5 + medium 15 固定列表

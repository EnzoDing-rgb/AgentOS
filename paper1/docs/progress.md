# BudgetFlow Progress

## 明天回来先看这个

### 主线（2026-05-31）

**论文问题：** 固定 **batch 经济预算** 下，agentic SWE 能否 hard cap 内靠 **progress-aware routing** 比 budget-only / all-tier1 换更多 resolved？

**Contribution：**

1. **BudgetFlow runtime** — reserve/settle governor + stage-aware selector；不动 mini-SWE 循环。
2. **Shared batch budget** — 一 policy 一池、题内串行；模拟项目预算。
3. **Hard cap** — settle clamp，`batch_spent ≤ batch_cap`。
4. **RQ2** — 同 agent、harness、cap 档：Full vs Only vs all_flash。

**不测：** 自建 agent、eval 上 tune progress table、smoke cap 写进主表。

---

### 现在到哪了

| 里程碑 | 状态 |
|---|---|
| mini-SWE adapter + local harness + worktree | ✅ |
| Governor hard cap（settle clamp） | ✅ |
| 三档 AICode pool（spark / mini / codex） | ✅ |
| `run_mini_swe_compare`（6 capped + all_pro） | ✅ |
| **B.0 pilot（clean 题单）** | ✅ **FROZEN** tight_batch_n5=5271 |
| `protocol.md` | ✅ tight_n5=5271 / loose_n5=21082 |
| `step_limit` 80→**150** | ✅ 代码默认已改 |
| Stage-A 3×3（旧 pressure+手写 cap） | ⚠️ **INVALID** — 勿当主结果 |
| **Stage-A 5×3 @ protocol** | ⏳ **P0 下一步** |
| RQ2 n=20 | ⏳ |

---

### 架构（并行边界）

| 层 | 行为 |
|---|---|
| Agent | mini-SWE monolithic ReAct |
| BudgetFlow | 只路由 **model tier**（LOC/REP/VAL 启发式 + budget pressure） |
| Pilot | uncapped `all_pro` 测每题花费 → 写入 **loose_batch_n* / tight_batch_n*** → 冻结 protocol |
| Compare | **policy 内串行**（共享 governor）；**policy 间并行**（`--jobs N`） |

Governor units ≠ 真实 API ¥；真钱看 provider dashboard。

**Backend pool（frozen）：**

| tier | model |
|---|---|
| T1 | `openai/gpt-5.3-codex-spark` |
| T2 | `openai/gpt-5.4-mini` |
| T3 | `openai/gpt-5.3-codex` |

`BUDGET_PRESSURE_INIT=0.01`，`PRESSURE_MAX=1.5`。

---

### B.0 pilot（2026-05-31，FROZEN）

**Tasks:** 13480, 14774, 16988（去掉 13647 localization outlier）  
**Runner:** `run_pilot --jobs 3 --step-limit 80`（当时默认；**正式 compare 用 150**）  
**Artifacts:** `pilot_b0_summary.json`, `docs/protocol.md`

| task | resolved | cost (units) | turns | exit |
|---|---:|---:|---:|---|
| 14774 | ✅ | 995 | 41 | Submitted |
| 13480 | ✅ | 2108 | 64 | Submitted |
| 16988 | ❌ | 2992 | **80** | **LimitsExceeded**, NO PATCH |

**Frozen batch caps（compare 只读这两列）：**

| n | loose_batch | tight_batch |
|---|---:|---:|
| 3 | 12649 | 3162 |
| 5 | **21082** | **5271** |

**读法：**

- Pilot 输出的是 **整包 workflow budget**，不是 per-task cap。
- Harness OK（13480/14774 PASS）。
- **80 step 太紧** — 16988 explore/LOC 耗尽，无 patch。
- 16988 失败仍花 2992 → **tight_batch_n5 偏松**；可跳过 re-pilot 先跑 compare。
- 若要更紧 cap：step_limit=150 重跑 pilot，或手工下调 protocol 里 `tight_batch_n5`。

---

### Stage-A 3×3（2026-05-31，**INVALID — 历史 smoke**）

**勿写进 paper。** 两档/三档过渡期、手写 cap、旧 pressure。

设置：13480/13647/14774 × 3 策略；**手动** tight=150、loose=500（非 protocol）；`BUDGET_PRESSURE_INIT=0.08`。

| strategy | resolved | batch / cap | t1% | t2% | t3% |
|---|---:|---:|---:|---:|---:|
| all_flash_tight | 1/3 | 150/150 | 67% | 0% | 0% |
| budgetflow_full_tight | 2/3 | 150/150 | **100%** | 0% | 0% |
| budget_only_loose | 3/3 | 330/500 | 50% | 29% | 21% |

结论仅限 smoke：**full 2/3 > all_flash 1/3**（同 cap=150）；full **无升档**（pressure 仍偏高）；only_loose cap 更松，不可与 full_tight 比。

---

### 3×5 compare（2026-05-27，DeepSeek 两档，smoke cap）

**Runner:** `--preset 3x5 --loose 500 --tight 200`  
**Tasks:** 13480, 13647, 14774 | **非 protocol cap**

| strategy | resolved | batch_spent | cap |
|---|---:|---:|---:|
| budgetflow_full_loose/tight | **3/3** | 139 / 180 | 500 / 200 |
| budget_only_loose/tight | 1/3 | 500 / 199 | 500 / 200 |
| all_pro | 3/3 | 774 | ∞ |

历史信号：同 cap **Full 3/3 vs Only 1/3**；all_pro ~5.5× 贵。模型池已换三档，数值不可直接拼接。

---

### 5×5 compare @ 旧 protocol（2026-05-27，superseded）

| strategy | resolved | batch_spent | cap |
|---|---:|---:|---:|
| budgetflow_full_tight | **3/5** | 468 | 468 |
| budget_only_tight | 2/5 | 468 | 468 |
| all_pro | 5/5 | 6707 | ∞ |

tight 档 Full > Only；旧 batch cap 口径已被 clean pilot 取代。

---

### 下一步（P0）

**Stage-A 5×3 @ FROZEN protocol** — 验三档 routing + resolve 优势：

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1 && \
FORCE_COLOR=1 PYTHONPATH=/home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1/src:/home/fengde/Projects/AI-learning/agent_learning/AgentOS/external/mini-swe-agent/src \
python -u -m budgetflow.run_mini_swe_compare \
  --limit 5 --jobs 3 \
  --strategies all_flash_tight,budget_only_tight,budgetflow_full_tight \
  --read-protocol --trace-verbose --heartbeat 30 --step-limit 150 \
  2>&1 | tee /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1/data/runs/stage_a_5x3.log
```

**Caps（n=5）：** tight=**5271**，loose=21082（来自 `protocol.md`）

**成功标准：**

- `budgetflow_full` resolved ≥ `budget_only` ≥ `all_flash`（至少 tight 档）
- full 出现 **t2% 或 t3% > 0**（REP/VAL 升档）
- 无 OVER_CAP

通过后 → Stage-B 10 题 tight 三策略 → Stage-C 全 6 策略。

---

### 现在不要做什么

- 把 Stage-A INVALID 3×3 写进主表
- 用旧 protocol（tight_batch 187 档 / 1951 档）
- 用 smoke 500/200 写 paper
- eval 上 tune progress_table / pressure
- `workflow_steps_ok` 当 resolved
- step_limit=80 跑正式 compare

---

### 代码备忘（2026-05-31）

- `defaults.py` — 三档 AICode；pressure init 0.01
- `run_pilot.py` — 写 `loose_batch_n*` / `tight_batch_n*`；无 median 对外字段
- `run_mini_swe_compare.py` — default `--step-limit 150`；`_flash_ratio` 含 spark
- `deepseek_backend.py` — 清 ALL_PROXY 修 litellm SOCKS
- `lite_tasks.py` — pilot 默认 13480/14774/16988
- 单测 19/19 pass

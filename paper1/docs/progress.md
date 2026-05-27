# BudgetFlow Progress

## 明天回来先看这个

### 主线（2026-05-27）

**论文问题：** 在固定 **batch 经济预算** 下，agentic SWE 能否既守住 hard cap，又靠 **progress-aware routing** 比 budget-only 换到更多 resolved？

**Contribution 叙事（顶会 vision，不是调参小实验）：**

1. **BudgetFlow runtime** — LLM 边界的 reserve/settle governor + stage-aware selector；不动 mini-SWE agent 循环。
2. **Shared batch budget** — 一个 policy 一个池、题内串行；模拟真实「项目预算」而非 per-task 独立 cap。
3. **Hard cap** — settle clamp，`batch_spent ≤ batch_cap`；并发 reserve 防超支。
4. **RQ2 实证** — 同 agent、同 harness、同 cap 档，Full vs Budget-Only vs all_pro。

**不测什么：** 自建 agent、改 prompt、在 eval 上 tune progress table、把 smoke cap 当主表。

---

### 现在到哪了

| 里程碑 | 状态 |
|---|---|
| mini-SWE adapter + local harness + worktree | ✅ |
| Governor hard cap（settle clamp） | ✅ 3×5 验证 |
| `run_mini_swe_compare`（3×5 / 5×5 preset） | ✅ |
| **3×5 harness compare** | ✅ **首个 resolved>0 主信号** |
| **B.0 pilot** | ✅ **FROZEN** M=187.15（13480/13647/14774） |
| **dynamic budget_pressure** | ✅ `live_budget_pressure` + `PRESSURE_MAX=1.5` |
| **trace submit fix** | ✅ 仅 `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` |
| `protocol.md` 冻结 cap | ✅ loose_n5=1871 / tight_n5=468 |
| **5×5 compare @ protocol** | ✅ Full 3/5 vs Only 2–3/5 |
| RQ2 n=20 主表 | ⏳ |

---

### 3×5 mini-SWE compare（2026-05-27，hard cap，easy-3）

**Runner:** `run_mini_swe_compare --preset 3x5 --loose 500 --tight 200 --jobs 5`  
**Tasks:** `13480`, `13647`, `14774`（compare_easy 前 3，小 patch）  
**Caps:** smoke 占位（偏松，见下节校准）；**非论文冻结 cap**  
**Logs:** `data/runs/compare_3x5.{jsonl,summary.log}`  
**Traces:** `data/runs/trace_<task>_<strategy>/{steps.jsonl,trajectory.json}`

| strategy | resolved | batch_spent | cap | flash% |
|---|---:|---:|---:|---:|
| **budgetflow_full_loose** | **3/3** | 139 | 500 | 100% |
| **budgetflow_full_tight** | **3/3** | 180 | 200 | 100% |
| all_pro | 3/3 | 774 | ∞ | 0% |
| budget_only_loose | 1/3 | 500 | 500 | 0% |
| budget_only_tight | 1/3 | 199 | 200 | 5% |

**读法（paper 级）：**

- 同 cap 档 **Full 3/3，Only 1/3** — routing 在 batch 竞争下换 resolved，不是省 turn 的小技巧。
- Full 全 flash 仍过 harness；all_pro 贵 **~5.5×**（774 vs 139）。
- Only 几乎全 pro（`BUDGET_PRESSURE_INIT=0.35` + 两档 backend）→ 13647 吃光池 → 14774 `budget_exhausted`。**预期 batch 叙事**。
- `batch_spent ≤ cap`，无 OVER_CAP — hard cap 生效。
- loose 绝对花费 < tight（139 vs 180）：**非 bug**；13647 在 tight 多 4 turns；并行 run 有方差。看 **resolved + cap 利用率**。

elapsed ≈ 408s

---

### Cap 校准（重要 — 全文见 `docs/protocol.md`）

**公式（batch 级，已锁定）：**

```
M = median(per-task all_pro cost)   # pilot，uncapped
loose_batch = 2 × M × n
tight_batch = 0.5 × M × n
```

**M 从哪来：**

| 来源 | tasks | M | 能否冻结 cap |
|---|---|---:|---|
| compare_3x5 all_pro（**应用**） | 13480/13647/14774 | mean **258**, median **113** | ✅ 推荐 |
| B.0 pilot（**废弃**） | 20212/12171/**21614** | median **1951** | ❌ 21614 wander 47571 污染 |

**21614 为何不能估 M：** 236 turns、kind 子系统探索、patch 多文件失败 — 测的是 uncapped zombie，不是典型题成本。  
**Pilot / smoke 题单应换成 compare_easy 档**（13480/13647/14774 类），不是 `SMOKE_INSTANCE_IDS` 里的 21614。

**n=3 推荐 cap（待 B.0 重跑写入 protocol）：**

| 基准 | loose | tight | 说明 |
|---|---:|---:|---|
| M=113（median，稳健） | **680** | **170** | 推荐冻结 |
| M=258（mean，含 13647 方差） | 1550 | 387 | 偏保守 |
| 应力档（约 M_eff≈50 的 BF 观测） | **~300** | **~150** | 比 smoke 500/200 更紧，适合 RQ2 |

**现 hand cap 500/200：** pipeline smoke 用，**偏松**（full_loose 只花 28% pool）— 主表须换 protocol 值。

---

### Pilot 怎么叙事（B.0）

**Purpose：** 测 uncapped all_pro 的 per-task cost 分布 → 导出 batch cap 公式。**不是**比策略。

**Procedure：**

1. 选 **representative easy** n 题（单 gold file、小 patch、harness 稳定）。
2. all_pro、无 cap、`step_limit` 与正式 eval 一致。
3. 记每题 cost、turns；**M = median**；报告 outlier（如 21614）但不进 M。
4. 算 `loose_batch` / `tight_batch` → 写入 `protocol.md` → **冻结**，后续 compare 只读 protocol。

**当前 B.0 状态：** 已跑完但题单错误 → `protocol.md` 标 **INVALID**，需 `--pilot-tasks compare_easy` 重跑。

---

### 历史（superseded，勿当主结果）

<details>
<summary>旧 edit-IR / E2E / mock routing（点击展开）</summary>

- 通用 edit IR E2E（24152/24213）：IR 目标达成，harness 语义 fail
- 10-task mock routing（`run_deepseek_compare`）：workflow_steps_ok，**非 harness**
- 20-task mock Lite：pressure=0.45 下 Full 9/20 vs Only 1/20

指标边界：`workflow_steps_ok` ≠ `harness_resolved`；mock units ≠ API USD。

</details>

---

### B.0 pilot（2026-05-27，FROZEN）

**Tasks:** 13480, 13647, 14774 | **M=187.15** | costs: 187, 485, 69  
**Batch caps (n=5):** loose **1871**, tight **468**  
**Artifacts:** `pilot_b0_summary.json`, `docs/protocol.md` (FROZEN)

---

### 5×5 compare @ FROZEN protocol（2026-05-27，dynamic pressure）

**Runner:** `--preset 5x5 --read-protocol --jobs 5`  
**Caps:** loose=1871.5, tight=467.9（M=187.15）  
**Logs:** `data/runs/compare_5x5.{jsonl,summary.log}`

| strategy | resolved | batch_spent | cap | flash% |
|---|---:|---:|---:|---:|
| **budgetflow_full_loose** | **3/5** | 1871 | 1871 | 100% |
| **budgetflow_full_tight** | **3/5** | 468 | 468 | 100% |
| budget_only_loose | 3/5 | 1871 | 1871 | 3% |
| budget_only_tight | 2/5 | 468 | 468 | 41% |
| all_pro | 5/5 | 6707 | ∞ | 0% |

**读法：** tight 档 Full **3/5 > Only 2/5**；loose 同分但 Only 几乎全 pro（dynamic pressure 后 tight 有 41% flash）。16988/20212 wander 拖垮 capped 策略；hard cap 无 OVER_CAP。

elapsed ≈ 1243s

---

### 下一步（P0）

1. **RQ2 iter-1** — n=20，Full vs Only，只读 protocol cap

### 已完成（2026-05-27 code）

- `live_budget_pressure(governor)`：`pressure = init + used_frac × (PRESSURE_MAX - init)`
- trace：`submit=YES` 仅完整 marker；`patch.txt` → `patch_prep`
- `PILOT_INSTANCE_IDS = compare_easy[:3]`；`run_pilot` 输出 batch caps
- `run_mini_swe_compare --read-protocol`；单测 18/18 pass

### 现在不要做什么

- 用 B.0 旧 protocol（M=1951）跑主表
- 用 21614 估 M
- 把 smoke 500/200 写进 paper
- 在 eval 上 tune progress_table / pressure
- 把 `workflow_steps_ok` 写成 resolved

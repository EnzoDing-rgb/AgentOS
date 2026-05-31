# BudgetFlow Refactor — 进度

> **Vision：** BudgetFlow 是 agentic SWE 的 **runtime economic layer** — 在固定 batch 预算下，用 reserve/settle hard cap + progress-aware routing，比 budget-only 换更多 **harness resolved**，且不修改 agent scaffold。  
> **Empirical hook：** mini-SWE-agent + local harness + shared batch pool（RQ2）；mock batch governance（RQ1）。

---

## 已锁定

| 项 | 决定 |
|---|---|
| Scaffold | mini-SWE-agent，commit pin `adfe2023…`，只 bash |
| BF 接入点 | LLM 边界 wrapper，不动 agent 循环 |
| Harness | `local_harness.py`（非 Docker leaderboard；论文 disclaimer） |
| Backend | DeepSeek Flash / Pro |
| 预算 | **每 policy 一个 shared batch pool**；policy 内 task **串行**；policy 间 `--jobs N` + worktree |
| Cap | pilot 测 uncapped all_pro per-task costs → 冻结 **`loose_batch_n*` / `tight_batch_n*`**；compare 只读 batch cap |
| Hard cap | settle clamp；`batch_spent ≤ cap` |
| 路由表 | `defaults.py` 写死，eval 不调 |

---

## Cap 校准（论文冻结数据 — 详见 `docs/protocol.md`）

**Runtime 单位：** 每个 policy 一个 **shared batch budget**（`tight_batch_n5=5271` 等），不是 per-task cap。

**Pilot 产出：** uncapped all_pro 每题 governor units → 写入 protocol 的 `loose_batch_n*` / `tight_batch_n*`。

**当前 FROZEN（2026-05-31）：** per-task costs 995/2108/2992 → `tight_batch_n5=5271`，`loose_batch_n5=21082`。

**Pilot 题单（待改代码）：** `13480`, `13647`, `14774`（compare_easy），**非** `SMOKE_INSTANCE_IDS`（含 21614）。

---

## Pilot 叙事（B.0）

| 问题 | 答案 |
|---|---|
| Pilot 测什么？ | Uncapped all_pro per-task costs → **batch caps** 写入 protocol |
| Pilot 不测什么？ | 策略对比、BF vs Only |
| 题怎么选？ | Representative **easy**（小 patch、单 gold、harness 稳） |
| 21614 角色？ | Stress / case study；**不进 pilot 题单** |
| 产出？ | `pilot_b0_summary.json` + **`protocol.md`（冻结）** |
| 旧 protocol？ | 2026-05-27 版标 INVALID，compare 主表不得用 |

---

## 进度

| 步 | 状态 | 说明 |
|---|---|---|
| **A** Adapter | ✅ | runner、harness、worktree；hard cap；**dynamic pressure** |
| trace submit fix | ✅ | `run_trace.py` + `test_run_trace.py` |
| pilot 题单代码 | ✅ | `PILOT_INSTANCE_IDS`；batch cap 输出 |
| **B.0 Pilot** | ✅ | tight_batch_n5=5271；protocol **FROZEN** |
| **5×5 compare** | ✅ | Full 3/5 tight > Only 2/5；protocol caps |
| **B.1–3** RQ2 | ⏳ | n=20、cap 读 protocol |
| **C** RQ1 mock batch | ⏳ | `run_batch_governance.py` |
| **D** 文档 | 🏃 | progress + refactor 已更；concept/result 待同步 |

---

## 3×5 结果摘要（paper seed）

```
full_loose   3/3  batch_spent=139/500
full_tight   3/3  batch_spent=180/200
only_loose   1/3  batch_spent=500/500  (13647 吃池)
only_tight   1/3  batch_spent=199/200
all_pro      3/3  batch_spent=774
```

Artifacts: `data/runs/compare_3x5.{jsonl,summary.log}`，`trace_*` 目录。

---

## 5×5 结果摘要（2026-05-27，FROZEN caps + dynamic pressure）

```
full_loose   3/5  batch_spent=1871/1871
full_tight   3/5  batch_spent=468/468
only_loose   3/5  batch_spent=1871/1871  flash=3%
only_tight   2/5  batch_spent=468/468   flash=41%
all_pro      5/5  batch_spent=6707
```

Artifacts: `data/runs/compare_5x5.{jsonl,summary.log}`

---

## 下一步（按顺序）

1. **B.1** — n=20 iter-1（Full vs Only，caps 读 protocol）
2. Step C mock batch（可并行）

## Dynamic budget_pressure（已落地）

```
used_frac = (spent + reserved) / total
pressure = BUDGET_PRESSURE_INIT + used_frac × (PRESSURE_MAX - init)   # PRESSURE_MAX=1.5
```

- 接线：`mini_swe_proxy.query()`、`loop._run_step()`
- uncapped（total ≥ 1e6）→ 保持 init
- **不做：** PROGRESS_TABLE 在线更新（iter-3）

---

## 跑实验

**3×5 smoke（占位 cap，验管道）：**
```bash
cd paper1 && FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
python -u -m budgetflow.run_mini_swe_compare --preset 3x5 --loose 500 --tight 200 --jobs 5
```

**5×5（stress + wander 题，读 FROZEN protocol）：**
```bash
python -u -m budgetflow.run_mini_swe_compare --preset 5x5 --read-protocol --jobs 5
```

**Pilot（重跑后）：**
```bash
python -m budgetflow.run_pilot   # 题单改 compare_easy 后
```

**主表指标：** resolved/n、batch_spent、batch_cap、violations、flash%。  
早题花光池 → 后题 `budget_exhausted` = **正常 batch 竞争**，写进 paper。

---

## 禁做

- 用 INVALID protocol（M=1951）或 21614 估 M
- per-task 独立 cap
- smoke hand cap 当论文最终结果
- eval 上调 routing / progress table
- 改 mini-SWE prompt

---

## Paper-ready checklist

- [ ] `protocol.md` 有效版（M + batch caps + task list hash）
- [ ] RQ2 主表（iter-1 n=20）
- [ ] RQ1 mock batch 表
- [ ] concept/design/result 同步；旧 E2E 标 superseded

# BudgetFlow Refactor — 进度

> 测什么：**同一 mini-SWE agent、同一 batch 预算，BF 路由是否比 Budget-Only 更省、batch 是否更稳。**  
> 不测什么：自建 agent、改 mini-SWE prompt、在 eval 上调参。

---

## 已锁定

| 项 | 决定 |
|---|---|
| Scaffold | mini-SWE-agent，commit pin `adfe2023…`，只 bash |
| BF 接入点 | LLM 边界 wrapper，不动 agent 循环 |
| Harness | 现用 `local_harness.py`（非 Docker leaderboard 口径，论文须 disclaimer） |
| Backend | 仅 DeepSeek Flash / Pro |
| 预算 | **每 policy 一个共享 batch pool**；policy 内 task **串行**；policy 间 `--jobs N` 并行 + worktree |
| Cap 公式 | pilot 得 `M` → `loose_batch = 2×M×n`，`tight_batch = 0.5×M×n` |
| 路由表 | `defaults.py` 写死，不校准 |

---

## 进度

| 步 | 状态 | 说明 |
|---|---|---|
| **A** Adapter | ✅ | adapter、baseline/compare runner、harness、worktree 隔离；runtime 单测过 |
| 归档旧 scaffold | ✅ | `archive/staged_react_v1` 已推；main 已删旧 ReAct/tool_sandbox |
| **B.smoke** 5×5 | 🏃 | `run_mini_swe_compare --limit 5 --jobs 5`；手填 cap 试管道，**非论文主表** |
| **B.0** Pilot | ⏳ | `run_pilot.py` 有，**未跑**；`protocol.md` **未生成** |
| **B.1–3** 正式 RQ2 | ⏳ | n=20、cap 来自 pilot、iter 递进（Full/Only → +workflow → +anchors） |
| **C** RQ1 mock batch | ⏳ | `run_batch_governance.py` 未建 |
| **D** 文档 | ⏳ | concept/design/result 未同步 |

---

## 下一步（按顺序）

1. **等 5×5 smoke 跑完** → 看 summary 里各 strategy 的 `resolved/n`、`batch_spent`（Full vs Only 有无信号）
2. **跑 B.0 pilot**（3 task × all_pro 无 cap）→ 出 `M`，写 `protocol.md` 冻 batch 公式
3. **改 `run_pilot.py`**：输出 `loose_batch`/`tight_batch`（别再用 `*_per_task` 字段名）
4. **B.1**：20 task，仅 Full vs Only，cap 读 protocol，`--jobs` 并行 policy
5. **并行或之后**：Step C mock batch（不依赖 mini-SWE）

---

## 跑实验怎么记

**一个 batch** = 一个 strategy × 一个 budget 档 × 一个 governor × n 题串行。

主表看：**resolved/n、batch_spent、batch_cap、violations**。  
早题花光预算 → 后面题 `budget_exhausted`，**正常**，要写在论文里。

**Smoke 命令（占位 cap）：**
```bash
cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src \
python -u -m budgetflow.run_mini_swe_compare --limit 5 --loose 500 --tight 200 --jobs 5
```

**Pilot：**
```bash
python -m budgetflow.run_pilot
```

---

## 禁做

- per-task 独立 governor cap（与 batch 设计冲突）
- 改 mini-SWE prompt / fork scaffold
- eval 上调 routing 或 progress table
- smoke 手填 cap 当论文最终结果
- iter-3 完成前扩到 n=50

---

## Paper-ready 还差

- [ ] `protocol.md`（M + batch cap 公式 + task list hash）
- [ ] RQ2 主表（`rq2_iter*.jsonl` + summary）
- [ ] RQ1 主表（`result_batch.md`）
- [ ] 三份设计/结果文档同步 + 旧 E2E 标 superseded

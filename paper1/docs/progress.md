# BudgetFlow Progress

## 明天回来先看这个

### 现在到哪了

- **通用 edit IR 已落地**：JSON `edits` → workspace apply → `git diff` → harness
- ops: `replace`, `anchor_replace`, `insert_before/after`, `line_replace`
- 结构化 failure: `parse_error`, `target_not_found`, `ambiguous_anchor`, `empty_diff`, `harness_fail`
- **gold patch**：2/2 `harness_resolved=True`（harness 可信）
- Docker SWE harness 不可用 → `local_harness.py`

### 通用 edit IR E2E（2026-05-26，budgetflow_full，5 repair rounds）

| task | patch_extracted | harness_resolved | last_failure |
|---|---|---|---|
| sympy__sympy-24213 | 1/1 | 0/1 | **harness_fail**（语义，非 exact-match） |
| sympy__sympy-24152 | 1/1 | 0/1 | harness_fail（patch apply OK，pytest fail） |

- task2 失败从 `target_not_found` → `harness_fail` — IR 目标达成
- repair prompt 已从 stale ````diff```` 改回 JSON multi-op（含 `line_replace`）
- 单元测试 `test_repair_workspace.py` 5/5 pass

### E2E 2-task × 三策略 compare（旧路线，direct diff + file context）

runner: `run_e2e_compare.py`  
tasks: `sympy__sympy-24152`, `sympy__sympy-24213`

| strategy | harness_resolved | patch_extracted | total cost |
|---|---|---|---|
| all_flash | 0/2 | 2/2 | 4.79 |
| all_pro | 0/2 | 2/2 | 18.12 |
| budgetflow_full | 0/2 | 2/2 | 8.18 |

- repair prompt 已加 **repo 文件 snippet**（localization 路径 → checkout 读文件）
- localization 不再 leak gold_files
- **仍 0/2 resolved** — patch 能抽出，但 hunk 行号/格式 corrupt → `git apply` 失败
- budgetflow picks 仍 **flash/pro/flash**；cost 梯度 flash < budgetflow < pro
- elapsed ≈ 333s

### E2E 首跑（无 file context，budgetflow only）

- patch_extracted 2/2，harness_resolved 0/2（同上根因）

### 10-task routing compare（仍有效）

runner: `run_deepseek_compare.py 10`

| strategy | workflow_steps_ok | total cost (gov units) | flash steps | pro steps |
|---|---|---|---|---|
| all_flash | 10/10 | 22.93 | 30 | 0 |
| all_pro | 10/10 | 109.63 | 0 | 30 |
| budgetflow_full | 10/10 | 52.23 | 20 | 10 |

- elapsed ≈ 575s
- budgetflow picks 稳定：**flash/pro/flash**（10 task 全同）
- cost 梯度：flash < budgetflow (~48%) < pro

**指标边界：**

- `workflow_steps_ok` = API 成功 + stage keyword rubric
- **不是** `harness_resolved` — 无 patch、无 SWE harness
- cost = mock-scale governor units，非精确 API USD

### 仍有效的 mock 结果（20 Lite tasks）

- `pressure=0.45`: budget_only 1/20，budgetflow_full 9/20
- mock backend，测 selector 机制，非真 fix

### 下一步（P0）

1. **语义 repair 质量** — failure 已在 harness 层；加 harness 失败摘要进 retry prompt
2. resolved>0 后再扩 2-task / 10-task E2E
3. Docker 可用时切官方 SWE harness

### 现在不要做什么

- 不在 eval 10 上 tune pressure / progress_table
- 不做 continual learning
- 不做 trajectory / SweLoc / SweRank（除非为 held-out 校准）
- 不把 `workflow_steps_ok` 写成 resolved

# BudgetFlow Automatic Budget Objective

本文档记录 BudgetFlow 论文当前的终局设计：系统不要求人类提前知道每个任务应该批多少预算，而是自动估算预算、动态分配预算，并在预算约束下尽可能多解决有价值的任务。

## 1. Core Claim

BudgetFlow 的卖点不是“某个模型更强”，也不是“某个 agent scaffold 更强”。

BudgetFlow 的卖点是：

> 给定一批 agent tasks 和一个预算池，系统能自动判断哪些任务值得继续花钱、哪些任务应该升级模型、哪些任务应该止损，并在总预算下解决更多可验证任务。

这比手工指定 per-task budget 更有价值，因为人类通常不知道：

- 一个任务到底简单还是困难；
- 什么时候便宜模型已经足够；
- 什么时候需要升级到强模型；
- 什么时候继续烧钱只是浪费；
- 一批任务里应该优先救哪些任务。

## 2. Optimization Target

主目标应写成 constrained optimization，而不是单一指标。

默认形式：

```text
maximize    sum_i value(task_i) * P(resolve_i)
subject to  sum_i cost_i <= batch_budget
```

Paper 1 的默认设置可以先令：

```text
value(task_i) = 1
```

此时主指标就是：

> 在自动预算和固定 batch budget 下，解决尽可能多的任务。

这避免过早陷入“难题价值到底怎么算”的争论。任务价值可以作为扩展实验或讨论项保留。

## 3. Reporting Metrics

不要只报一个 pass rate。BudgetFlow 应该报 Pareto-style 结果。

核心指标：

- `resolved_count`: 解决题目数量。
- `pass@budget`: 固定预算下的通过率。
- `AUC over budget`: 从低预算到高预算，整体预算效率。
- `cost_per_resolved`: 每解决一道题平均花费。
- `wasted_cost_on_failed_tasks`: 失败任务上浪费的钱。
- `oracle_gap`: 和 raw strong model ceiling 的差距。
- `gold_sanity_pass`: 任务本身是否能被 gold patch 在当前 harness 下通过。

论文主表应该回答：

```text
同样预算下，BudgetFlow 是否比固定策略解决更多题？
同样解决数量下，BudgetFlow 是否更省钱？
失败时，BudgetFlow 是否更早止损？
强模型可解时，BudgetFlow 是否能及时升级？
```

## 4. Budget Policy

BudgetFlow 不应该是死板 hard cap only。

推荐策略：

```text
soft_budget + bounded_overrun_guard
```

解释：

- `soft_budget`: 系统默认按这个预算规划。
- `bounded_overrun_guard`: 只有在证据很强时允许小幅超支。
- `absolute_hard_cap`: 最外层仍然保留，防止失控烧钱。

允许超支的证据包括：

- agent 已经定位到 gold-like file；
- patch 能成功 apply；
- fail_before 已确认存在；
- fail_after 接近通过，或者失败数量减少；
- 当前任务已经进入 repair/validation 后期；
- 继续一次强模型调用的边际成本小于重新开始任务的浪费。

不允许超支的信号包括：

- 长时间没有打开相关文件；
- 多轮 patch apply 失败；
- fail_after 没有任何改善；
- 重复读同一批无关文件；
- 工具错误或 harness 异常没有被解决；
- 当前任务已经明显超过同类任务成本分布。

## 5. Automatic Budget Estimation

自动预算分两层：

### 5.1 Batch Budget

人类给出总预算级别，例如：

```text
small probe: 5 tasks, low cost
medium run: 20-50 tasks
paper run: larger fixed budget
```

系统负责把 batch budget 分配到任务和 workflow turns。

### 5.2 Per-task Dynamic Budget

每个任务启动时给一个初始预算，不一次性批满。

建议按以下信号动态调整：

- repo/task 历史难度；
- gold sanity 是否通过；
- 当前模型是否找到相关文件；
- patch apply 是否成功；
- fail_after 是否改善；
- 当前任务相对同 batch 其他任务的进展；
- 当前 batch 剩余预算压力。

一句话：

> 预算不是一次性发完，而是按证据逐步解锁。

## 6. Resume Requirement

所有实验 runner 必须有 resume 能力。

原因很简单：

> 实验一定会断。断了不能重烧钱。

必须满足：

- 每个 `(task_id, policy, model_pool, seed/config)` 有稳定 run key。
- 每个 run 完成后写入 jsonl/ledger。
- 已完成且 verdict 可信的 run 默认跳过。
- 中途 crash 后可以从 next unfinished run 继续。
- harness bug 修复后，可以只重跑 affected runs。
- API 失败、网络失败、工具失败要标记为 infra failure，不要混成 model failure。
- resume 时必须打印 skipped / pending / rerun 的数量。

推荐状态：

```text
PENDING
RUNNING
PASS
FAIL_MODEL
FAIL_INFRA
FAIL_HARNESS
SKIPPED_RESUME
INVALIDATED
```

如果 evaluation harness 变化，旧结果不能盲信。需要记录：

- harness version 或 git commit；
- task ids；
- model pool config；
- policy config；
- pass/fail evaluator version；
- gold sanity result。

## 7. Model Tier Policy

GPT-5.5 太贵，不适合作为常规最强档。

推荐常规 tier：

```text
T1: remove from main run, keep only for ablation/smoke
T2: cheap Qwen / cheap coder
T3: stronger Qwen or GPT-5.3 Codex candidate
T4: GPT-5.3 Codex as regular strongest tier
T5: GPT-5.5 only for ceiling probe
```

原则：

- GPT-5.5 只回答“这题强模型到底能不能解”。
- GPT-5.5 不进入 budgeted routing pool。
- 常规 BudgetFlow 实验用 GPT-5.3 Codex 做强档更合理。
- 如果 GPT-5.3 Codex 明显强于当前 Qwen T4，应该替换当前 T4。
- T1 不要参与主实验，避免低质量调用污染轨迹；但可以保留做消融。

Current implementation:

- `build_compare_backends()` skips T1 by default.
- Explicit `all_flash` / `all_t1` ablation runs can still include T1.
- This makes the main automatic-budget pool start at T2, which matches the paper claim: BudgetFlow should allocate useful budget, not prove repeatedly that the cheapest weak model is weak.

Soft budget implementation:

- `GovernorConfig` now supports `soft_budget` and `max_overrun`.
- `run_mini_swe_compare` exposes `--soft-budget` and `--max-overrun`.
- Per-task experiments can keep a soft cap while allowing a bounded overrun when a turn is already in flight or evidence justifies one more step.
- `scripts/run-auto-v2-goldpass5.sh` uses `--per-task-cap 3000 --max-overrun 300`.

Expensive T4 rule:

- If regular T4 is Qwen coder-plus, auto_v2 may open a short T4 rescue window after concrete repair evidence.
- If regular T4 is `gpt-5.3-codex`, auto_v2 must be more conservative: wait for more repair evidence, use a shorter rescue window, and require more remaining budget headroom.
- This is the key automatic-budget behavior: expensive models are not banned, but they are only unlocked after evidence says the task is worth rescuing.

## 8. Evaluation Guardrails

Evaluation hardness 是第一优先级。

任何 task 进入主实验前必须先过：

```text
gold patch sanity
```

也就是：

- 原始代码 fail_before 必须失败；
- 应用 gold patch 后 fail_after 必须通过；
- PASS_TO_PASS 不应被截断到不合理子集；
- 网络、DNS、外部服务依赖不能污染判定；
- infra failure 不能被算成 model failure。

如果 gold patch 在本地 harness 下都过不了，这个 task 不能用于 BudgetFlow 结论。

## 9. Experiment Ladder

推荐推进顺序：

1. `raw agent + GPT-5.5` 跑少量 gold-sanity tasks，确认 ceiling。
2. `raw agent + GPT-5.3 Codex` 跑同一批，确认可用强档。
3. `BudgetFlow + no GPT-5.5` 跑 5 policies x 5 tasks。
4. 如果 BudgetFlow 差，先查 routing/预算/resume/harness，不急着换 agent。
5. 只有当 raw strong model 能解、BudgetFlow 解不了，才说明 BudgetFlow routing 有问题。
6. 只有当 raw strong model 也解不了，才考虑 task 太难或 agent scaffold 太弱。

当前阶段不优先切换 agent framework。先固定 SWE-mini agent scaffold，把 BudgetFlow 的预算机制跑清楚。

## 10. Paper Message

最终论文不要说：

> 我们找到一个更便宜模型组合。

应该说：

> 我们提出一个 workflow-aware budget governor。它能在 agent workflow 运行中根据进展证据动态分配预算、升级模型和止损。在相同预算下，它比固定强模型、固定弱模型、stage-blind routing、budget-only routing 解决更多任务或浪费更少预算。

这才是 BudgetFlow 的核心贡献。

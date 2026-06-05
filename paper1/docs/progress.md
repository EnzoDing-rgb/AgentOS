# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 当前快照（2026-06-05）

### 043 后 Phase M 状态

- **Phase M 完成：** AutoResearch infra 验收 PASS（186 tests, no-paid goal-loop smoke exit 0）。Paper 文档一致性审计 PASS（4 docs, claim ladder 无矛盾）。详细报告：`docs/reports/043.md`。
- **Paper claim ladder 已明确：** First Claim 是 value-driven token efficiency，即 shared hard budget 下最大化 verified resolved value per dollar。Second Claim 是原始 BudgetFlow 机制，即 stage/progress-aware routing 是否还能比 dummy / budget-only / market routing policy 更省钱或更高效。
- **不再把 routing 公式当唯一支柱。** 当前代码确实实现了 `stage weight × expected progress gain / marginal cost` 的逐步路由，并叠加 progress/stagnation/gold-edit escalation/stop-loss；但它可能付出 KV / prefix-cache loss 和切换开销。该机制先保留为 second-claim hypothesis，后续用实验验证，不提前否定也不盲目护航。
- **North Star 文档已补 claim ladder。** 论文主目标是 value-aware shared budget governance；SWE-bench 只是可复现 proxy，不是系统边界。系统要防止对 SWE-bench 过拟合，保留可插拔 task value、budget context、history、runtime adapter、verifier。
- **Concept 文档已开始转向。** `paper1_concept.md` 标题和核心问题从 workflow-aware budgeting 改为 value-aware budget governance；实验问题和指标加入 `resolved value @ fixed budget` 与 `resolved value per dollar`，旧 `cost_per_resolved` 保留为 second-claim / backward-compatible 指标。
- **Value 第一版实现细节暂不落盘。** 当前文档只记录 abstract value-driven direction；具体 proxy、矩阵字段、重算脚本和实验命令留给下一轮 Worker 任务设计。

### 039 后权威状态

- **North Star 已完成重大转向：** BudgetFlow 不再只被定位为 smart routing / cost efficiency 系统，而是 value-aware shared budget governance。核心目标是让共享硬预算池中的 value flow 到最高价值、可验证完成的任务上。
- **Value Proposition 已更新：** 论文主指标应从 `resolved tasks per dollar` / per-task cost 转为 `resolved value per dollar`。也就是在同一 hard budget 下，系统是否解决了价值量最高的一批任务，而不是只比较每个任务花多少钱。
- **BudgetMemory 的定位也随之改变：** 它不只是 task cost memory；长期应学习 task value、difficulty、model success、cap sufficiency、failure axis 和 marginal escalation benefit，服务 value-cost allocation。
- **现有 030/031 实验仍有工程价值，但不再足够支撑新主张。** 031 证明了 true LOO BudgetMemory cascade 干净；030/031 也证明在 equal-value 假设下 BudgetFlow 暂未稳定 beat BudgetOnly。但在新 Value Proposition 下，下一轮必须重设 Key Indicator 和 task value model 后再做实验。
- **AutoResearch Phase K 完成：闭环。** 034-041 已完成完整闭环：coordinator → CLI → fake/real workers → goal-loop → deterministic review gate → owner_decision → safe commit/push → 报告。Owner 现在可以用一条 `goal-loop` 命令跑完整 cycle，exit code 区分 complete/owner-review/failure。
- **AutoResearch 当前判断：** Phase K 已把 AutoResearch 从"能跑 smoke"推进到"基本减少 owner 人肉搬运"。goal-loop 自动化了 issue 遍历 + review + mark-complete/retry/pause + 报告生成 + commit/push。证据 ledger 自洽（goal JSON ↔ summary ↔ metadata ↔ review）。下一步应做 real API goal-loop smoke 验证和 `_safe_commit_push` 实战测试。
- **运行环境结论：** 当前开发目录 `/root/.dev/AgentOS` 和 `/tmp/budgetflow-runtime` 避开了 `/Lishun` NFS 小文件 I/O。runtime-root 重构已把 worktrees、repo cache、locks、trace scratch 迁出 repo/NFS。`external/mini-swe-agent` symlink 仍是待清理技术债，不要提交。
- **最新实验卡点：** BudgetFlow paid benchmark 暂停推进。最近 clean BudgetFlow 实验仍是 031；之后的 034-039 是 AutoResearch / workflow infrastructure。037 卡点是 `claude -p` session overhead 超出小额 smoke budget；038 用 thin API worker 绕过。
- **下一条并行主线：** 重新设计 Key Indicator：为 SWE-bench task 赋予 value / difficulty / expected payoff，评估 `sum(value * resolved) / cost` 或同 hard budget 下 resolved value total。该实验设计与 AutoResearch 证据闭环是并行任务。

### 当前必须区分的两条线

| 线 | 当前目标 | 状态 |
|---|---|---|
| BudgetFlow paper | 从 cost-driven 转为 value-driven，重设 indicator 和实验 | 等待新指标设计；不再用 030/031 直接 claim 优势 |
| AutoResearch | 减少 owner 人肉搬运，形成 Codex ↔ Worker 可恢复闭环 | 原型可跑；下一步修 evidence ledger 和 review gate |

### 031 后权威状态（旧 cost/equal-value 口径）

- **031 完成：真正 5x2 LOO BudgetMemory 泛化验证。** `postfix_031_loo_5x2`：5 held-out tasks, 2 strategies, 10/10 rows clean。BudgetMemory source 全部 `repo_median`，0 exact_task leakage。checker CLEAN。
- **031 结果：** `budget_only_tight` 4/5 PASS ($0.49)；`budgetflow_full_tight` 4/5 PASS ($0.70)。双方均 budget_fail 在 sympy-18057。BudgetFlow 更贵且无 pass 优势（与 030 一致）。
- **BudgetMemory LOO cascade 已验证：** held-out tasks → `repo_median`，training tasks → `exact_task`。gate 通过。Gate/dry-run 可用 `--budget-memory-dry-run` + `--budget-memory-exclude-ids` 在不调 API 下验证。
- **Auto-budget 与 BudgetMemory 是两个独立系统：** auto-budget 的 `history_exact` 来自硬编码 `_HISTORICAL_PRIOR`，不是 leakage。两个 source 字段必须分开解读。
- **详细报告：** `paper1/docs/reports/031.md`。
- **阶段 B 路径审计完成：** `paper1/docs/reports/032.md`。发现 3 个 HIGH blocker：repo cache 在 paper1/data/repo_cache（NFS + Git 污染）、mini-swe-agent symlink 指向 /Lishun、CACHE_DIR 无 CLI 覆盖。Trace scratch 在 data/runs 也需迁到 /tmp。
- **阶段 C2 完成：runtime-root 非侵入重构。** 所有高 churn 路径迁至 `/tmp/budgetflow-runtime/`（worktrees, repos, locks, traces）。新增 `--runtime-root` / `--allow-nfs-runtime` CLI。8/8 blocker 修复。21 测试通过。P0 review fixes 已完成。详细报告：`paper1/docs/reports/033.md`。
- **阶段 D 完成：AutoResearch 最小闭环骨架。** 实现了非侵入式 coordinator state machine（`autoresearch_coordinator.py`），管理 workflow 目录、pause conditions、retry、dry-run/manual mode。37 新测试。不调用 Worker/API。详细报告：`paper1/docs/reports/034.md`。
- **`budget_prior_source` vs `budget_memory_budget_source` 交叉审计：** 030 全部 `global_fallback`（空训练集），031 全部 `repo_median`（LOO cascade 正确）。两个字段是独立系统，不能混读。

### 030 后权威状态

- **工作目录已迁移：** 当前主开发目录是 `/root/.dev/AgentOS`。`/Lishun/.../AgentOS` 仍可作为旧持久化来源，但不要再作为交互开发主目录，避免 Git/NFS 小文件 I/O 卡顿污染判断。
- **云端同步点：** `feature/issue-1` 已 push 到 GitHub，当前 HEAD 为 `18f14eb Add autoresearch guard and 030 fallback report`。
- **030 口径修正：** `postfix_030_loo_10x2` 不是 LOO generalization，而是 cold-start fallback test。因为排除了全部 10 个已知 task，BudgetMemory 训练集变成 0 records，所有任务走 `global_fallback`，cap=$1.50。
- **030 真实结果按 `harness_resolved` 统计：** `budget_only_tight` 7/10 PASS, $1.59；`budgetflow_tight` 7/10 PASS, $2.03。双方 pass 打平，BudgetFlow 更贵。之前把 `rescue_timeout_gold_edited` 直接算 FAIL 是错误口径；5 个该 exit_reason 中 4 个 harness_resolved=True。
- **论文 claim 状态：** BudgetMemory fallback safety 成立；BudgetMemory 泛化未由 030 证明；BudgetFlow > BudgetOnly 未稳定成立。当前不能用 030 讲泛化或优势，只能讲 fallback 不崩与 pass/fail 口径修正。
- **下一步主线：** 不扩到 15/20 task。先做真正 LOO 5x2：held-out 5 tasks，但训练数据中保留其它 task，确认 `repo_median` cascade 在真实 run 中可复现，再讨论 repeats/scale。
- **分工规则：** worker agent 只执行实验、交付 JSONL/checker/report/log/test 证据；下一步策略判断由主 agent 做，不接受 worker 的“推荐下一步”作为决策依据。

### 仍然有效的硬门槛

- PASS/FAIL 主口径永远是 `harness_resolved`，不是 `exit_reason`。
- 报告不是事实源；JSONL、checker、heartbeat、summary log 是事实源。报告只能是这些证据的 ledger。
- `data/runs` 体积大且高 churn，不默认提交 Git；需要审计某次实验时，先明确要同步哪些小型 JSONL/summary/report。
- 所有新实验必须先过 gate：无 orphan/stuck heartbeat、无 suspicious pass、无 no_trace、BudgetMemory source 分布符合实验语义。

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
- **016 完成：** 3 bugs fixed (bo T3 window, bf cap relax, rescue_timeout rename)。bf_tight **5/5 PASS (100%)**，首次 beat all_pro。all_pro stability audit 11/11 PASS 确认 18189/18057 为模型非确定性，非天花板。BudgetFlow 路由修复全面验证。54/54 tests pass。`reports/016.md`。
- 下一步：gold-PASS pool 从 7 → 10+；跑 3×5 smoke test；准备 10×5。

### Current active tier

| Tier | backend | litellm id | provider |
|---|---|---|---|
| T1 | `tier1` | `openai/qwen3-coder-flash` | DashScope 百炼 |
| T2 | `tier2` | `openai/qwen3-coder-plus` | DashScope 百炼 |
| T3 | `tier3` | `openai/gpt-5.4` | AiCode007 |

注：当前 main pool T1 标记为 "skipped"，可用 tier 实际为 [T2, T3]。

### 最新改动（2026-06-05）

- **Phase M (043)**：AutoResearch infra 验收 + paper doc 一致性审计。No-paid goal-loop smoke (2/2 PASS, exit 0)。186 tests pass。4 docs 审计无矛盾。takeaway.md 竞争定位段标注 pre-pivot 上下文。详细报告：`paper1/docs/reports/043.md`。
- **Phase L (042)**：Real API goal-loop smoke。Dispatch wrapper (`<!-- WORKER:fake/worker:api -->`) + real API worker → goal-loop → deterministic review → all PASS。Push-path validated（secret scan / diff --check / test suite / commit / push）。总 API cost ~$0.002，远在 $0.05 cap 内。详细报告：`paper1/docs/reports/042.md`。
- **Phase J-fix (040)**：Evidence gate hardening。Goal completion invariants、fake worker auto-detect、factual heuristic 上下文感知、marker_appended 强制 WARN。040 报告更新为 COMPLETE ALL PASS。
- **Phase J (040)**：Evidence ledger + review gate。7-check deterministic review、fake/real worker auto-detect、worker_metadata.json + factual header 审计 trail。`paper1/docs/reports/040.md`。
- **039**：Real API goal smoke。两次 DeepSeek API 调用，成本 ~$0.002。Goal summary 自洽性修复。`paper1/docs/reports/039.md`。

- **016**：3 bug fixes + routing verification。bf_tight 5/5 (100%)。all_pro stability audit 11/11 PASS。`reports/016.md`。
- **015**：postfix_012_trace_sanity 完成。25/25 rows，0 crashes。Routing fix verified — bf_tight 84% T2, bf_loose 77% T2。12 passes 全部 authentic。`reports/015.md`。
- **Display fix**：`run_mini_swe_compare.py` summary label `"failures:"` → `"outcomes:"`。
- **Routing fix**：`selector.py` 公式从 `score >= pressure` 反转为 `pressure >= upgrade_threshold`（`upgrade_threshold = delta_cost / (delta_progress * SCALE * w_i)`）。`PROGRESS_SCALE` 18.0→0.3。现在 LOC 优先 T2，REPAIR/VAL 在 pressure 升高时升级 T3。`policies.py` budget_only T3 窗口。
- **012**：Worktree crash 闭环修复（`_remove_worktree` 5层清理 + `_worktree_add` retry）。Checkpoint `batch_cap:null` 修复。Auto-budget 扩充至 10 task + `min_cap` $0.05→$0.10。回归测试 31→50，全部通过。postfix_011_sanity 25/25 rows clean。`reports/012.md`。
- **011**：P0 fix — `.1f` cost 展示四舍五入污染真实 USD 可观测性，已加 `_fmt_usd()` 自适应格式。31 个新回归测试（pricing/worktree/resolved/memory/format）。59/59 pass。
- **010**：P0 修复（API 价格校准、worktree crash、resolved=None）+ 009 成本重解 $34K→$10.63。`reports/010.md`。
- **009**：Overnight batch loop。56 recorded rows，BudgetFlow 正向信号但数据不够干净。3 个新 SymPy gold-PASS task。`reports/009.md`。
- **008**：首次 model matrix。14/15 records。`reports/008.md`。
- 已写：`reports/006.md`、`007.md`、`008.md`、`009.md`、`010.md`、`011.md`、`012.md`、`015.md`、`016.md`、`039.md`、`040.md`、`041.md`、`042.md`、`043.md`。
- 已补：mini-swe-agent 依赖，compare runner import/`--help`/全链路恢复。
- 已实现/接入：Automatic Budgeting v1 与 memory 写入。Memory 已清理（备份至 `.bak_010`），下次运行自动新建。
- 已修/部分修：SymPy `py.test` compat；Django `django.setup()` compat。但 Django 新 task 仍卡 `INSTALLED_APPS`。
- 已确认：`--jobs` 并行 worktree 隔离；GPT-5.4 非确定性；`django-12113`/`sympy-21612` 是 ceiling task。

### 下一步

当前下一步分两条并行线：

1. **BudgetFlow paper 线：重设 Key Indicator。** 为 SWE-bench task 构造 value / difficulty proxy，先明确 `value_i` 如何从 historical trajectories、gold patch complexity、known solve difficulty、repo/task family、model success/cost 等信号得到。然后重跑小规模 value-aware 评估，主表改为 `resolved_value_per_dollar` 和 fixed-budget resolved value。
2. **AutoResearch 线：已闭环，后续做 real API goal-loop smoke 和实战 commit/push 测试。** Phase K 完成 goal-loop、owner_decision、safe commit/push、报告生成。下一步用真实 API (≤$0.02) 验证 goal-loop + review gate 全链路，以及 `--commit-after-pass --push-after-commit` 在真实 git remote 上的行为。
3. **实验 hygiene 保持不变：** 所有新 BudgetFlow paid run 仍必须先过 gate：无 orphan/stuck heartbeat、无 suspicious pass、无 no_trace、BudgetMemory source 分布符合实验语义。
4. **不要直接扩规模。** 在新 indicator 未定义前，继续 5×10/10×N 只会烧钱并强化旧问题。先做 value model + 2-3 个 baseline 的小型验证。
5. **Runner/环境稳定性继续保持：** runtime-root 已修复高 churn 路径；新 paid run 使用 `/tmp/budgetflow-runtime`，不要回到 `/Lishun` worktree/repo cache。

---

## 论文问题

固定 **shared hard budget** 下，BudgetFlow 能否比 cost-only routing / static quotas / simple baselines 创造更多 **verified resolved value per dollar**？

新主问题不是“每个任务谁更便宜”，而是：

```text
Given a shared budget pool and a batch/stream of tasks with unequal value,
which policy resolves the highest total verified value within the same budget?
```

**核心指标：**

```text
resolved_value_per_dollar = sum(value_i * harness_resolved_i) / sum(cost_i)
```

也可以在 fixed budget 下报告：

```text
total_resolved_value_under_budget = sum(value_i * harness_resolved_i)
```

**Contribution：** value-aware shared budget governance + hard budget pool + task-level value/difficulty/cost learning + verified outcome accounting。Stage-aware routing（Localization/Repair/Validation）是一个实现机制，不是唯一贡献。

**历史实验口径说明：** 012/030/031 默认 `value_i=1`，因此只能说明 equal-value setting 下的 routing/cascade/fallback 行为。它们仍然是工程与机制证据，但不能直接支撑最新 Value Proposition。

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
| Routing verification experiment | ✅ postfix_015_fixes: bf_tight 5/5 (100%) |
| Value-driven North Star | ✅ 2026-06-05 更新：shared budget pool + resolved value per dollar |
| True LOO BudgetMemory cascade | ✅ 031 验证 `repo_median`，0 exact-task leakage |
| Runtime root / NFS mitigation | ✅ 033：高 churn 路径迁至 `/tmp/budgetflow-runtime` |
| AutoResearch coordinator | ✅ 034：非侵入 state machine + pause/retry/manual mode |
| AutoResearch CLI + worker bridge | ✅ 035/036：CLI + fake-worker full no-paid smoke |
| AutoResearch real worker adapter | ⚠️ 037 `claude -p` overhead blocked；038 thin API worker PASS |
| AutoResearch goal loop | ✅ 039 real API goal smoke PASS；Phase K 完成 goal-loop 闭环 |
| AutoResearch evidence ledger + review gate | ✅ Phase J：evidence 自洽；deterministic review gate 硬化 |
| AutoResearch goal-loop + owner_decision + commit/push | ✅ Phase K：`goal-loop` 一键闭环；owner_decision.md；safe commit/push |
| AutoResearch real API goal-loop smoke + dispatch | ✅ Phase L：dispatch wrapper；real API goal-loop；push-path validated |
| AutoResearch infra audit + paper doc consistency | ✅ Phase M：186 tests pass；no-paid smoke exit 0；4 docs audit clean |

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

环境：`cd` 到 `/root/.dev/AgentOS/paper1`，用可用的 `python3` 或项目 `.venv/bin/python`，`PYTHONPATH=src:../external/mini-swe-agent/src`，日志建议 `FORCE_COLOR=1`。

**① 5×3（3 tasks × 5 strategies，frozen caps）**

```bash
cd /root/.dev/AgentOS/paper1 && \
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
python3 -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 3 --step-limit 150 \
  --strategies budget_only_tight,budget_only_loose,budgetflow_full_tight,budgetflow_full_loose,all_pro \
  --jobs 5 --run-series policy_5x3 \
  --ids sympy__sympy-13480,sympy__sympy-14774,sympy__sympy-16988 \
  2>&1 | tee data/runs/policy_5x3-N.log
```

**② 中断恢复（固定 stem，不新开 ID）**

```bash
cd /root/.dev/AgentOS/paper1 && \
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
python3 -u -m budgetflow.run_mini_swe_compare \
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
| **postfix_012_trace_sanity-1** | 015 验证 run；5×5；trace enabled；routing fix | **25/25**，12 PASS | `data/runs/postfix_012_trace_sanity-1.*` |
| **postfix_015_fixes-1** | 016 验证 run；5×5；bo T3 + bf cap fix | **25/25**，19 PASS | `data/runs/postfix_015_fixes-1.*` |
| **stability_audit** | all_pro 7 tasks × 3 rounds；T3-only uncapped | **11/21**（中断）| `data/runs/stability_audit_*.jsonl` |
| **postfix_031_loo_5x2** | 真正 5×2 LOO；BudgetMemory exclude；auto-budget；trace on | **10/10**，8 PASS | `data/runs/postfix_031_loo_5x2.*` |

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

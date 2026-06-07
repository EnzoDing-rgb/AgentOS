# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 当前快照（2026-06-07）

### 072 / AutoResearch implementation pruning

- **072 COMPLETE SLICE — no-paid architecture cleanup.** No historical experiment JSONL was edited and no paid experiment was run.
- **AutoResearch document preserved:** `docs/autoresearch_workflow.md` remains the canonical memory of the owner/Codex/Worker productivity design.
- **Paused implementation removed:** deleted the inactive AutoResearch Python modules, worker scripts, and tracked `.autoresearch/` smoke/workflow artifacts from the active tree. They were self-contained and not imported by the compare runner, observability checker, value/RVPD path, learning context, routing policy, or no-paid gates.
- **Architecture judgment:** future AutoResearch should be rebuilt from the workflow document when it again accelerates BudgetFlow. Keeping old coordinator code and old smoke artifacts in the active tree now slows navigation and invites stale-test maintenance.
- **Evidence status:** this is not new T1/T2 experiment evidence. It reduces non-paper surface area so future infer/debug work can focus on runtime, evaluation, observability, routing, and learning.

### 071 / Local harness adapter boundary

- **071 COMPLETE SLICE — no-paid evaluation-harness refactor.** No historical JSONL was edited and no paid experiment was run.
- **Harness boundary split:** repo-specific local-harness behavior moved from `local_harness.py` into `local_harness_adapters.py`. The new adapter module owns SymPy/Django/Requests adapters, Python-version compatibility patching, pytest node-id mapping, and pytest invocation.
- **Core harness locality:** `local_harness.py` now focuses on runtime repo/worktree preparation, patch application, and `evaluate_local_harness()`. This makes local-harness false-positive/false-negative debugging easier without deleting necessary repo compatibility behavior.
- **Compatibility judgment:** repo compatibility patches remain part of the local evaluation adapter, not obsolete paper-runtime compatibility. They prevent local-harness infra failures from being mistaken for model or routing failures.
- **Verification:** `171 passed`, `py_compile` passed for `paper1/src/budgetflow`, `git diff --check` passed, and no-provider `--auto-budget-dry-run` still loaded both cap memory and routing policy memory.
- **Evidence status:** this is not new T1/T2 experiment evidence. It improves trust in the inner-loop evaluation harness used before paid experiments.

### 070 / AutoResearch doc contraction and value-context locality

- **070 COMPLETE SLICE — no-paid architecture/document cleanup.** No historical JSONL was edited and no paid experiment was run.
- **AutoResearch document rewritten:** `docs/autoresearch_workflow.md` moved from 373 lines of mixed current/old implementation narrative to a 129-line current design note. It preserves the useful productivity thinking (owner/Codex/Worker loop, artifact-first review, pause gates, recoverability) while deleting stale phase history, implementation inventories, directory scaffolding, and old 3x10 readiness details.
- **Runtime locality improvement:** `run_mini_swe_compare.py` no longer keeps module-level `_VALUE_CONTEXT` state. `ValueEfficiencyContext` is now constructed inside `main()` and passed/closed over explicitly for record enrichment and strategy execution. This reduces cross-run/test leakage risk and keeps value/RVPD state local to one compare invocation.
- **Architecture judgment:** checker/observability is already split into `run_observability/{audit,checks,schema,report,cli}` with `check_run_observability.py` as a thin compatibility entrypoint. Legacy fallback remains only at analysis/checker edges.
- **Verification:** `171 passed`, `py_compile` passed for `paper1/src/budgetflow`, `git diff --check` passed, and no-provider `--auto-budget-dry-run` still loaded both cap memory and routing policy memory.
- **Evidence status:** this is not new T1/T2 experiment evidence. It makes the core loop easier to reason about before the next paid experiment.

### 069 / Test-suite contraction and evidence-contract cleanup

- **069 COMPLETE SLICE — no-paid test/infra cleanup.** No historical JSONL was edited and no paid experiment was run.
- **Test-suite contraction:** `paper1/tests` moved from 50 files / ~11.1k LOC to 19 files / ~2.6k LOC. Deleted AutoResearch implementation tests, phase-era regression bundles, old compatibility tests, result-table display tests, and duplicated micro-helper tests that did not protect T1/T2 evidence quality.
- **Contract tests kept:** compare-path row schema, value/RVPD enrichment, learning-context source separation, PolicyMemory routing priors, value-aware routing/salvage, anti-spin/timeout/provider guards, local harness sanity, policy parallelism, and failure classification.
- **Large test files rewritten:** `test_policy_memory.py`, `test_adaptive_routing.py`, `test_compare_record_schema.py`, and `test_trace_fields.py` now test current paper/runtime contracts instead of historical implementation details.
- **AutoResearch positioning:** `autoresearch_workflow.md` is preserved and updated as a research-productivity thinking artifact. AutoResearch code/tests are not part of the current BudgetFlow T1/T2 proof path unless they affect compare runtime, JSONL observability, value accounting, or learning gates.
- **Observability architecture judgment:** `check_run_observability.py` is already a thin compatibility entrypoint over `run_observability/{audit,checks,schema,report,cli}`. Legacy fallback remains isolated at checker/analysis edges and does not shape current runtime code.
- **Verification:** `171 passed` in 10.71s, `py_compile` passed for `paper1/src/budgetflow`, `git diff --check` passed, and no-provider `--auto-budget-dry-run` loaded cap memory plus routing policy memory successfully.
- **Evidence status:** this is not new T1/T2 experiment evidence. It improves future iteration speed by making tests guard experiment credibility instead of historical compatibility.

### 068 / Compare runner architecture refactor

- **068 COMPLETE SLICE — no-paid architecture cleanup.** No historical JSONL was edited and no paid experiment was run.
- **Runner decomposition:** `run_mini_swe_compare.py` is now a thin compare CLI/orchestrator, not the home for all compare semantics. Focused modules now own config, setup, CLI parsing, artifact persistence, summary rendering, task execution, and learning-memory setup.
- **New modules:** `experiments/compare_execution.py` owns task execution, record construction, per-policy batch execution, heartbeat progress, and per-row observability assembly. `experiments/compare_memory.py` owns Value-Driven Budget Allocation memory, BudgetMemory estimates, policy-memory gate-only, and no-provider dry-run output.
- **Entrypoint shrink:** `run_mini_swe_compare.py` moved from the old 2400+ line shape to **609 lines**. The runner no longer exposes `_run_one` / `_run_strategy_batch` as pseudo-library APIs; tests use `compare_execution.run_task_record`.
- **Deleted stale compatibility:** current code no longer rewrites old strategy aliases or preserves old `_VALUE_*` globals. New experiments must use canonical strategy names and `ValueEfficiencyContext`. Historical reports remain forensic and are not edited.
- **Verification:** focused no-paid gate passed: `72 passed` across value efficiency, record schema, setup, value-aware routing, policy parallelism, learning context, and auto-budget tests. `py_compile` passed for the refactored modules. No-paid `--auto-budget-dry-run` still loads cap memory and routing memory without provider calls.
- **Architecture judgment:** this was a necessary cleanup before more paid scale-up. The next useful cleanup is checker/observability: standard fields should be the interface, while legacy JSONL fallback should stay isolated and not shape new runtime code.
- **Evidence status:** this refactor improves future infer/debug iteration speed. It is not new T1/T2 evidence.

### 067 / T1-first learning and observability refactor

- **067 COMPLETE — no-paid core refactor.** No historical JSONL was edited and no paid experiment was run.
- **Architecture change:** `learning_context.py` now separates cap/value-cost memory (`auto_budget_memory.jsonl`) from routing memory (run JSONL with routing traces). Auto-budget dry-run shows both sources separately.
- **Value semantics change:** `value_efficiency.py` owns T1/T2 value fields and treats T2 as the equal-value special case of T1, not a competing North Star.
- **Routing observability change:** `experiment_observability.py` adds persisted row fields for routing objective, policy family, policy-memory source, learned action, imitation fields, and schema version. The compact checker now reads these standard fields first, with legacy fallback for old JSONL.
- **Bug fixed during review:** BFV under `value_profile=equal` is now labeled `bfv_equal_value_ablation`, not `bfv_t1_value_aware`; equal-value runs cannot be mislabeled as Tier 1 value-allocation evidence.
- **No-paid gate:** focused suite `183 passed, 8 skipped`; py_compile and `git diff --check` pass. `--auto-budget-dry-run` loads cap memory from `data/runs/auto_budget_memory.jsonl` and routing memory from `data/runs/066_postfix_3x3.jsonl` without provider preflight.
- **Evidence status:** `066_postfix_3x3.jsonl` remains forensic/pre-refactor evidence only (`policy_memory_used=False`, incomplete invoice trace). It can seed routing memory, but it should not be used as a post-refactor claim result.
- **Residual risk:** `run_mini_swe_compare.py` still keeps `_VALUE_*` compatibility globals around `ValueEfficiencyContext`. This is acceptable for this phase but should be removed after old tests/callers migrate.

### 065 / Value-aware salvage gate and post-run infra fixes

- **065_value_salvage_3x3 COMPLETE — fresh BFV salvage gate.** Same 3 tasks × 3 policies, `--jobs 3`, `--auto-budget`, cost about **$1.09**, 9/9 rows complete. JSONL checker: 0 suspicious pass, 0 no trace.
- **Tier 1 mechanism signal:** On highest-value `sympy__sympy-16988` (value 0.329), BFV triggered value salvage (`task_value_multiplier=1.478`), patched `sympy/sets/sets.py`, and passed. BO and BFC both stopped with no patch. This supports value-aware stop/continue as a mechanism.
- **Aggregate result is mixed/negative:** BO 2/3, $0.2180, RVPD 1.523; BFC 2/3, $0.3354, RVPD 0.990; BFV 2/3, $0.5332, RVPD 0.728. BFV resolves more value than BO/BFC but spends too much and fails Django 10924.
- **Tier 2 not supported:** BFC does not beat BO on pass, cost, or RVPD. It passes Django but takes 25 turns versus BO's 8.
- **Post-run infra fixes:** heartbeat writer race fixed (`10041ef`), concrete `out_stem` now becomes `run_series` for new artifacts (`10041ef`), and live summary strategy spend aggregation fixed (`65fb6a5`). Historical 065 JSONL is not edited; summary/heartbeat are forensic.
- **No-paid gate after fixes:** `066_dryrun_identity_gate --auto-budget-dry-run` created no run artifacts and read high-confidence exact memory caps: 14774 $0.1000, 16988 $0.3547, Django 10924 $1.0000.
- **Next direction:** run a fresh paid 3x3/3x5 only after schema/summary/heartbeat stay clean on the post-fix path. Main policy question: BFV needs better mid-high-value Django behavior, either through lower salvage threshold or better post-gold-edit repair quality.

### 064 / Anti-spin validation and classifier correction

- **064_antispin_3x3 COMPLETE — fresh post anti-spin run.** Same 3 tasks × 3 policies, `--jobs 3`, `--auto-budget`, cost about **$0.74**, 9/9 rows complete.
- **Runtime fix:** repair phase no longer counts as progress unless the command is an actual repair/validation action. `STAGNATION_NO_PROGRESS_STEPS` moved 40 → 12. This directly targets 062b's read-only repair-loop false progress.
- **Evaluator fix:** no-patch `stagnation_no_progress` is no longer automatically `budget_fail/conservation_lockout`. Conservation lockout now requires trace evidence that T3 was blocked by max-tier/conservation and never accessed. 064 recomputes to `loc_fail=3`, `repair_fail=1`.
- **Result:** BO 3/3, $0.1775; BFC 1/3, $0.3896; BFV 1/3, $0.1742. This is negative for both Tier 1 and Tier 2.
- **Interpretation:** early anti-spin saves money but is too blunt. BFV stops before patching high-value tasks, so the missing mechanism is value-aware salvage: high-value no-patch stalls should get a bounded T3/salvage window rather than immediate stop.
- **Next direction:** do not scale. Implement value-aware stop/continue salvage, then rerun the same 3x3 gate.

### 063 / 062b rerun fragility audit

- **062b_gold_stoploss_3x3 is negative/fragility evidence, not a hidden success.** Same 3 tasks × 3 policies after the stop-loss tweak produced BO 3/3, BFC 3/3, BFV 1/3. Cost was about **$1.41**.
- **Tier 1 judgment:** 062's positive BFV signal is not stable enough for scale-up. 062b shows BFV can lose both high-value tasks (`sympy__sympy-16988`, `django__django-10924`) even when value multipliers are active.
- **Tier 2 judgment:** BFC can solve all three tasks, but it is still inefficient: 84 turns and about $0.67 versus BO's 31 turns and about $0.22. This does not support a clean routing-efficiency claim.
- **Patch-level audit:** BFV failures are real repair-quality failures, not obvious evaluator false negatives. On Django 10924, BFV computes `path` but still passes `self.path`, and pollutes unrelated field classes; BO/BFC produce compact passing patches. On SymPy 16988, BFV makes a broader multi-branch patch while BO/BFC make narrower passing duplicate-removal changes.
- **Continual-learning implication:** learned caps changed between 062 and 062b, which is expected now that Value-Driven Budget Allocation writes memory by default. Reports must record cap source/confidence/neighbors; repeated runs are not identical unless memory is frozen.
- **Observability fix after audit:** fresh rows now write top-level `resolved == harness_resolved`; checker warns on `RESOLVED_ALIAS_MISMATCH`. Historical JSONL is not edited and should be treated as forensic-only when aliases or stale verdict fields are missing.
- **Next direction:** do not launch 3×5/3×8 yet. First debug BFV decision quality and worktree/gold-edit evaluation timing on the 062/062b traces, then run another small policy-parallel rerun.

### 062 后 Auto-Budget Gate 与 3x3 fresh validation

- **062 COMPLETE — Value-Driven Budget Allocation learning gate + fresh 3-policy validation.** 新增 `--auto-budget-dry-run`，可零 API 审计 learned caps；修复 `not_enough_evidence` 低证据失败污染 learned median 的 P0 bug。
- **Fresh run:** `062_autobudget_3x3`，3 tasks × 3 policies，`--jobs 3` policy-parallel，`--auto-budget` learned caps，包含 1 个 Django task。9/9 rows complete，API cost **$1.1337**。
- **结果:** BFV 3/3，resolved value 0.6610，cost $0.4622，RVPD 1.430；BO 2/3，value 0.3320，cost $0.2253，RVPD 1.474；BFC 2/3，value 0.3881，cost $0.4463，RVPD 0.870。
- **Tier 1 判断:** 正信号但非 headline。BFV 是唯一解决全部任务的策略，并解决 BO 失败的高价值 `sympy__sympy-16988`；但 RVPD 略低于 BO，说明现在证据更支持“resolved value under budget”，不是简单 per-task cost win。
- **Tier 2 判断:** 062 不支持 BFC routing efficiency。BFC 比 BO 更贵、turns 更多，虽然能 rescue `16988`，但成本效率不干净。
- **新 P0 runtime bug:** gold-file edit 后 fallback/evaluation 太晚。多条 row 在 first repair 后继续消耗 5-18 turns，最终靠 `StagnationExit` worktree diff 评测。worktree fallback 有价值，但 `rescue_timeout_gold_edited evidence_turns=10` 太慢。
- **Summary bug fixed after run:** raw JSONL 的 dynamic per-task caps 正确；summary 误把 auto-budget sentinel 显示成 shared `batch_cap=100.00`。代码已区分 `dynamic_task_caps`，历史 summary 不回写。
- **下一步:** 不扩大到 3×5/3×8；先修 gold-edit fallback/evaluation timing，再 rerun 同一个 062 3×3。

### 061 后术语与 continual-learning 闭环状态

- **术语统一：** 新 canonical term 是 **Value-Driven Budget Allocation**。旧称 Automatic Budgeting 和 CLI `--auto-budget` 只保留为 backward-compatible implementation name。
- **重要修复：** continual learning 代码没有消失，但此前默认 run 不会写 learning memory；只有 `--auto-budget` 开启时才写。这意味着 058/059/060 这类 paid run 产生了 outcome，却默认没有进入 `auto_budget_memory.jsonl`。
- **现在行为：** normal run 默认创建 Value-Driven Budget Allocation memory writer，并把每个完成 row 写入 `auto_budget_memory.jsonl`，除非显式传 `--no-auto-budget-learn`。
- **策略边界不变：** 默认只收集学习数据，不默认用学习结果改变 cap；应用 learned cap 仍需显式 `--auto-budget` 或 `--budget-memory`。这样避免悄悄改变实验协议。
- **新增 observability：** JSONL row 写 `budget_learning_update_written`、`budget_learning_memory_path`、`budget_learning_applied_to_cap`，并带 `task_features`，使后续 exact-task / repo-kNN learning 可审计。
- **fresh runtime smoke：** `061_learning_smoke_v2`（1 task × 1 strategy, step_limit=1, cost ~$0.0013）验证新 row 真实写入 learning memory；memory record 带 `run_series` 和 `run_id=attempt_id`，可追溯。
- **下一步重点：** 用 `--auto-budget` 做小规模 Value-Driven Budget Allocation gate，检查 learned caps 是否合理；不要把 058/059/060 旧 row 回写成 learning evidence。

### 060 后 runtime/evaluator 修复状态

- **060_runtime_fix_3x3 COMPLETE — fresh post-fix validation.** 3 tasks × 3 strategies, `--jobs 3`, per-task cap $0.50, `unsolved_difficulty` value profile, all provider preflight PASS.
- **Runtime/evaluator fixes confirmed:** new rows have `turns == llm_turns`, explicit `budget_mode=per_task_cap`, `per_task_cap=0.5`, `value_source=value_matrix`, and BFV-only `va_active=True`. Checker reports 9 records, 8 pass / 1 fail, 0 suspicious pass, 0 no_trace, 0 warnings.
- **Summary bug fixed after 060:** final table correctly reports `planned_cap=1.50`; 060 footer still shows stale `per_task_cap=100.00` because `_ingest_batch_footer()` used shared `batch_cap` for display. Code now displays `batch_caps[cfg.name]` in per-task mode; historical summary not edited.
- **Timeout fix hardened:** LLM timeout is now configurable via `BUDGETFLOW_LLM_TIMEOUT_S` with default 90s, and timeout exceptions abort tenacity retry so provider fallback can happen instead of 50-minute stalls.
- **Fresh signal:** BFV 3/3, $0.4859, RVPD 1.123; BFC 3/3, $0.9100, RVPD 0.5995; BO 2/3, $0.6109, RVPD 0.3546. BFV is both the cheapest successful strategy and the only strategy that solves all tasks without hitting the cap.
- **Tier 1 signal:** highest-value task `sympy__sympy-16988` (value=0.329) is solved by BFV and BFC, failed by BO. BFV solves it at $0.2029 / 26 turns; BFC needs $0.5000 / 44 turns and hits cap. This supports task-wise value awareness as a practical improvement over both BO and value-blind conservation.
- **Tier 2 signal:** on common successful tasks, BFV also reduces waste versus BO/BFC; on `sympy__sympy-20212`, BFV spends $0.2509 vs BFC $0.3665 and BO $0.4831.
- **Remaining bugs / risks:** BO's 16988 row is `extract_fail` / protocol failure, so BO comparison is not a pure model-capability loss. BFC still shows repeated exploration and late rescue on 16988. These are runtime/anti-spin targets before scaling to 3×5/3×10 or adding more repos.
- **Task-pool decision pending:** current evidence is still mostly SymPy plus a small Django history. Next expansion should be staged: first add one new repo/category as an infra audit, not a paper-scale experiment; then scale once harness/protocol/observability stay clean.
- **Commit**: TBD

### 058 后 Phase AB 状态

- **Phase AB COMPLETE — Anti-spin hardening and validation**
- **3 bugs fixed**: (1) BFV missing from escalation/reserve allowlists, (2) HTTP timeout retry-loop → 50-min stalls, (3) BFC conservation lockout misclassification as protocol_fail
- **25 regression tests added**, all passing. 0 regressions in existing suite.
- **Validation experiment (058_5x1_v1)**: 15/15 rows, 3 strategies × 5 tasks, per-task cap $0.50, jobs=3
- **Reviewer correction:** 058 is an engineering/evaluator signal, not Tier 1 evidence. All 3 strategies resolve the same 4/5 tasks, so resolved value is identical (0.3798). BFV has the best RVPD/cost among the 4 resolved tasks, but this is cost efficiency, not value allocation.
- **16988 not evaluable in 058:** highest-value task (value=0.329) fails across the board. BFC/BFV hit provider/billing guard on dashscope T2; BO fails with repair/protocol behavior. This row cannot decide whether BFV rescues high-value tasks.
- **Phase AB runtime signals partially confirmed**: va_active/task_value_multiplier correct in all 15 rows, BFV escalation working, zero timeout retry loops. Post-review replay now flags 058 as old-schema artifact: missing `turns` alias and explicit `budget_mode` on all 15 rows, plus 2 stale verdict fields.
- **Post-review evaluator fixes:** compact audit now recomputes verdict fields from current classifier instead of trusting stale JSONL cache; per-task-cap budget exhaustion no longer triggers SHARED_CAP_STARVATION; new rows write `turns == llm_turns`, `budget_mode`, and `per_task_cap`.
- **Official harness caveat:** all current BudgetFlow pass/fail numbers are local-harness results. Official SWE-bench Docker audit is still required before paper headline claims.
- **Total cost Phase AB**: $2.34. Running total ~$17.50.
- **Commit**: TBD

### 056 后 Phase Z 状态

- **Phase Z COMPLETE — Debugging & validation loop for BFV**
- **当前定位不是 paper-level 结论。** Phase Z 的目标是修 inference、value observability、checker/evaluator、BudgetFlow runtime 的系统性 bug；小实验只作为 gate，跑稳后再扩大，不把单轮 worker summary 升级成论文结论。
- **决策纪律：worker recommendation 只作为输入材料。** 下一步方向由主 Agent / reviewer 基于 JSONL、checkpoint、summary log、checker 和 trace 独立判断；报告中的建议不能自动成为路线。
- **BFV 5/5 resolves all 5 tasks** in medium validation (056_5x1_v1). Only strategy to achieve full resolution.
- **BFC conservation lockout on high-value tasks REPRODUCED 3x**: sympy-16988 (value=0.329) fails at 7 turns across 055_3x3_v2, 055_3x5_v2, 056_5x1_v1. Conservation factor progressively locks out T3 as shared budget depletes.
- **BO hung on sympy-20212**: GPT-5.4 call stalled (121s/step, 1000+ seconds), never returned. Killed process. Missing 2 rows (20212, 16988).
- **Phase Z checker**: 5 new automated warnings + 16 regression tests in `test_phase_z_checker.py`
- **Value multiplier gradient confirmed**: 0.50 → 0.71 → 1.48 drives T3 share (14% → 24% → 47%)
- **Total cost Phase Z**: $1.61 (056_5x1_v1, 13/15 rows). Running total ~$10.75.
- **Remaining Phase Z cap**: $13.39 of $15.00
- **Commit**: TBD

### 055 后 Phase Y 状态

- **Phase Y COMPLETE — BudgetFlowValueAware (BFV) implemented and validated**
- **BFV WINS on both Tier 1 and Tier 2**: 6/6 combined resolution, RVPD=0.977 vs BFC=0.741 vs BO=0.473
- **BFV is the only strategy to resolve the highest-value task** (sympy-16988, value=0.329): BFC spent $0.028 then stagnated, BO exhausted budget, BFV spent $0.279 and succeeded with multiplier=1.48
- **Value-aware multiplier works**: 0.50 for below-median tasks → conservative, 1.48 for high-value outlier → aggressive. T3 allocation: 8% low-value → 32% high-value.
- **BFC's value-blind conservation backfires on the most valuable task**: conservation factor prevented T3 escalation, task stagnated after 7 turns and $0.028. BFV's value_multiplier counterbalances this.
- **Implementation**: ValueAwareSelector (72 lines), cleanly separated from ConservativeSelector. `_build_turn_trace()` bug found and fixed (missing value-aware kwargs).
- **Proxy noise**: BFV winner stability 96-100% at ±50% noise on RVPD, 100% on total value.
- **Combined evidence: 3x3 (primary) + 3x5 (supplementary) = 18 paid rows**. 3x3 had full task coverage (all 3 tasks, value spread 5x). 3x5 budget-exhausted before reaching high-value tasks.
- **Total cost Phase Y**: $3.00 (v1 crash $0.90 + v2 3x3 $1.14 + v2 3x5 $0.96)
- **Running total all phases**: ~$9.14 (exceeds original $8 cap for phases through X; Phase Y authorized as new phase)
- **Commit**: TBD
- **16 unit tests** in `test_value_aware.py` — all passing
- **Bug fixed mid-phase**: `_build_turn_trace()` TypeError — missing `task_value`, `task_value_multiplier`, `value_aware_active` parameters

### 053 后 Phase W 状态

- **Phase W COMPLETE — 27 paid rows, $3.76 total**
- **BFC WINS shared budget on outcome**: 3/3 PASS vs BO 2/3, BO2 2/3, BF 2/3. First strategy to achieve 3/3 under shared cap in this small pool.
- **Bug found & fixed**: BFC T3 double-penalty (hard cap + conservation). Fix: lower T3 gate 0.15→0.05 for BFC, reduce conservation slope 3.0→1.5.
- **Per-task results**: BO 3/3 ($0.34, 12% T3), BF 3/3 ($0.34, 32% T3), BFC 2/3 ($0.30, 19% T3), BO2 2/3 ($0.25, 0% T3). BF wastes T3, BFC balanced but per-task $0.15 too tight for hard task.
- **Checker**: ALL CLEAN (0 suspicious_pass, 0 no_trace across 27 rows)
- **P0 review finding after Phase W**: all 053 runtime rows have `value_source=missing_profile_fallback` and `task_value=1.0`. Therefore 053 is **NOT Tier 1 value-allocation evidence**. It is a Tier 2 routing-positive signal only.
- **Current interpretation**: BFC's shared-budget 3/3 supports the conservative-routing direction, but value observer fail-fast must be fixed before any claim about value-driven allocation.
- **Commit**: `760233c` (Phase W report), `aa12e80` (BFC fix), `4d0e63c` (052 report), `ad9bfc0` (Phase V code).

### 052 后 Phase V 状态

- **Phase V root-cause forensic complete.** Confirmed two implementation/evaluation bugs behind 051's negative signal: `budget_only_tight` was a false baseline that can front-load T3, and BudgetFlow pressure semantics made T3 easier as budget depleted.
- **Code fixes:** added true cost-only `budget_only_t2_*` strategies and `budgetflow_conservative_*` with a conservation factor that makes T3 escalation harder under depletion pressure.
- **Remaining requirement:** any non-equal value-profile run must fail fast when the value matrix/profile/task lookup misses. Silent fallback corrupts Tier 1 metrics.

### 051 后 Phase U 状态

- **Phase U 完成：** 首次 3-policy value-stress experiment。5 tasks × 3 strategies, 15/15 rows, $1.50 total。详细报告：`docs/reports/051.md`。
- **Task A — 050 Review Fix：** Downgraded "First Claim supported" → "First Claim observability validated; independent evidence pending"。Added Phase U Review Fix section。
- **Task B — Preregistration：** 3 policies (BO, SB, BF) × 5 tasks (value spread 4.87x)。Hypotheses preregistered。
- **Task C — Observability：** Added `budget_source` field。127 tests pass。
- **Task D — Paid experiment：** 15/15 rows ($1.50)。Checker WARN on 1 budget_exhausted zero-turn row。JSONL: `/tmp/budgetflow-runtime/051_value_stress.jsonl`。
- **Task E — 关键发现：BF LOSES。** BO 4/5, SB 4/5, BF 3/5。BF 比 BO 贵 20%（commonly-solved tasks）。BF 在 hardest task (sympy-16988) 上 FAIL 而 BO/SB PASS。KV/cache downside 确认：BF rescue_timeout 在已解决 task 浪费 12 turns。
- **Task F — AutoResearch：** exit 0。Infra healthy。
- **Task G — 报告/提交：** 051.md, progress.md, takeaway.md 更新，commit + push。
- **已知 blockers：** (1) Batch cap $0.50 太紧 — 最后一个 task 总是 budget_fail；(2) BF 在 easy task 上过度投资；(3) T3 ≠ 成功保证；(4) Identical resolved sets 无法测试 First Claim；(5) Task ordering effect 污染 comparison。

### 050 后 Phase T 状态

- **Phase T 完成：** P0 value matrix lookup fix + touched_file_paths text_regex enhancement + 049 smoke checker validation + expanded paid smoke 6/6 PASS ($0.66)。详细报告：`docs/reports/050.md`。
- **Task A — P0 Value Matrix Lookup Fix：** `_init_value_observability()` 从 `artifact["tasks"][instance_id]["values"][profile]` 读取（当前 schema），legacy `matrix[profile]` 作为 fallback。修复前所有 049 smoke rows 得到 `value_source=default_equal`、`task_value=1.0`（真实值 0.066-0.097）；修复后 050 smoke 全部 `value_source=value_matrix`。
- **Task B — touched_file_paths text_regex：** `extract_text_file_paths()` + `extract_trace_file_paths()` 覆盖 bash_command、assistant_content_head、parser_input_snippet。9 新 tests。31/31 bash_stage tests pass。
- **Task C — Checker Validation：** 049 smoke checker CLEAN (4/4 rows pass)，050 smoke checker CLEAN (6/6 rows pass)。
- **Task D — Expanded Paid Smoke：** 3 tasks × 2 policies, 6/6 PASS, total $0.6648。BF 比 BO 便宜 36% ($0.0865 vs $0.1351 avg)，RVPD 高 56% ($0.86 vs $0.55)。JSONL: `/tmp/budgetflow-runtime/050_smoke.jsonl`。
- **Task E — Value Matrix Update：** 生成 `050_clean_runs.json`、`050_value_matrix.json`。Sympy smoke 不进入 django clean universe。
- **Task F — AutoResearch 回归：** 96 value tests pass (13 observability + 83 matrix)，31 bash_stage tests pass，goal-loop smoke exit 0。
- **Task G — 报告/提交：** 050.md, progress.md, takeaway.md 更新，commit + push。
- **关键发现：** (1) P0 bug 根因是 `artifact["matrix"]` 在 048+ artifact 中总是 `{}`；(2) touched_file_paths 增强使 text_regex 模式的路径提取覆盖完整；(3) BF 在两个独立 smoke 上一致优于 BO（049: 4/4, 050: 6/6）；(4) First Claim（RVPD）差异主要由 cost efficiency 驱动，需要不同 task subset 才能独立测试 value differentiation。

### 049 后 Phase S 状态

- **Phase S 完成：** Provider 迁移恢复 + 真实 preflight + 小规模 paid smoke 4/4 PASS ($0.36)。详细报告：`docs/reports/049.md`。
- **Task A — 迁移诊断：** Provider 配置新旧 repo 完全一致。唯一差异：旧 repo 有 `.env`，当前 repo 没有。`load_env_file()` 读到空 → API key 未设置 → Phase R 401。
- **Task B — 安全 env 加载：** 从旧 `.env` shell-source 加载（不复制文件），只 export DASHSCOPE_API_KEY + AICODE007_API_KEY，不写任何 key 到 repo。
- **Task C — 真实 provider preflight：** DashScope chat completion PASS (200, qwen3-coder-flash)，AICode007 chat completion PASS (200, gpt-5.4)。Runner preflight 三层全部 PASS。Phase R `/models` endpoint 是 false blocker。
- **Task D — Preflight 代码审查：** `provider_signature.py` 已使用 `litellm.completion()` 做真实 chat preflight。代码正确，无需修改。
- **Task E — Paid smoke：** 2 tasks × 2 policies, 4/4 PASS, total $0.36。JSONL: `/tmp/budgetflow-runtime/049_smoke.jsonl`。BF 比 BO 便宜 22% ($0.0784 vs $0.1010 avg)，RVPD 高 29% ($12.76 vs $9.90)。
- **Task F — Manifest：** 生成 `049_clean_runs.json`。Sympy smoke 不进入 django clean universe（不同 task pool）。
- **Task G — AutoResearch 回归：** 93 value tests pass，goal-loop smoke exit 0。
- **Task H — 报告/提交：** 049.md, progress.md, takeaway.md 更新，commit + push。
- **关键发现：** (1) `.env` 缺失是 Phase R 401 根因，keys 本身有效；(2) `/models` endpoint ≠ chat completion，preflight 必须用真实 chat；(3) BF 在小规模 smoke 上一致优于 BO。

### 048 后 Phase R 状态

- **Phase R 部分完成：** Tasks A/B/C/E/F 完成，Task D (paid smoke) BLOCKED — 两个 API key 均返回 401。详细报告：`docs/reports/048.md`。
- **Task A — Q-fix consistency：** 修复 047.md 中错误的 API key gate（DeepSeek/OpenAI → DashScope/AICode007），regenerate 047_value_matrix.json 使用正确的 Phase Q manifest，新增 manifest provenance test。
- **Task B — Value observability：** `_enrich_record_with_value()` 在每个 run JSONL row 写入 6 个新字段（task_value_profile, task_value, resolved_value, value_source, value_matrix_artifact, resolved_value_per_dollar）。新增 CLI flags `--value-profile` 和 `--value-matrix`。Summary 输出包含 per-strategy value metrics。不改变路由决策。
- **Task C — Tests：** 10 new tests in `test_value_observability.py`（enrichment 6, summary 2, no-secret-leak 2）。93/93 value-related tests pass。
- **Task D — Paid smoke：** BLOCKED。DASHSCOPE_API_KEY 和 AICODE007_API_KEY 均返回 HTTP 401。Preflight check 正确阻止了带无效 key 的 paid run。
- **Task E — Artifact regeneration：** 生成 048_clean_runs.json 和 048_value_matrix.json（无新 paid data）。
- **Task F — AutoResearch 回归：** 93 value tests pass + goal-loop smoke exit 0。
- **333 total tests pass（33 pre-existing failures），git diff --check CLEAN。**
- **关键变化：** 每个 run record 现在携带 value observability 字段，使事后分析可以从 JSONL 中直接读取 value 信息，无需回到 value matrix artifact。Summary 输出也包含 resolved_value 和 resolved_value_per_dollar，使 value-aware 比较成为一等公民。

### 047 后 Phase Q 状态

- **Phase Q 部分完成：** Tasks A/B/C/E 完成，Task D (paid smoke) BLOCKED — API keys 未设置。详细报告：`docs/reports/047.md`。
- **Task A — runtime touched_file_paths：** 在 `bash_stage.py` 添加 `extract_touched_file_paths()`，支持 quoted paths (含空格) 和 unquoted paths，排除 glob/URL。`_build_turn_trace()` 所有 3 个 call site 已接入。22 tests pass (+17 新)。
- **Task B — 离线诊断更新：** `diagnose_localization_progress()` 优先读 `touched_file_paths`，老 trace fallback regex。Artifact 区分 `runtime_field_available` / `runtime_field_turns` / `fallback_regex_turns`。10 tests pass (+3 新)。
- **Task C — Clean universe 扩展：** 扫描所有 JSONL，确认只有 2 strategies (BO, BF)。无 3rd strategy 数据。047 manifest 保留 046 条目，记录 limitation。discriminative_rarity 仍需 3+ strategies 才生效。
- **Task D — Paid smoke：** BLOCKED。DEEPSEEK_API_KEY 和 OPENAI_API_KEY 均未设置。Smoke design 已就绪 ($0.50, 2 tasks × 2-3 strategies)，等待 key。
- **Task E — AutoResearch 回归：** 186/186 focused tests pass。Goal-loop smoke (047-phase-q-smoke) exit 0。
- **322 total tests pass，git diff --check CLEAN。**
- **关键变化：** `touched_file_paths` 字段现已存在于每个 turn trace，localization file-exploration 信号从 "dead" 变为 "recoverable at runtime"。等 paid smoke 产生带此字段的数据后，runtime_field_available 将从 false 变为 true。

### 046 后 Phase P 状态

- **Phase P 完成：** 修复 Phase O 审稿风险。`solve_rarity` 替换为 `discriminative_rarity` (peak at r=0.5) + `unsolved_difficulty` (ceiling candidate)，叙事与公式一致。新增 clean-run manifest (`value_matrix_clean_runs.json`) + `--manifest` CLI。离线 localization 诊断：136/215 turns (63.3%) 有可识别文件路径，progress signal 可恢复。Matched-task de-bias：23 对 task 内 T2/T3 比较，8/12 非 tie 对显示 T3 更低（within-task selection bias 确认）。79 new tests。297 total tests pass。**不建议启动 paid run，数据限制（2 strategies, 10 tasks）使 discriminative_rarity flat。** 详细报告：`docs/reports/046.md`。
- **关键修复：** discriminative_rarity 公式 `1+4r(1-r)` 在 r=0 和 r=1 都返回 1.0（低值），峰值在 r=0.5（2.0）。当前只有 2 strategies，所有 task rarity 都是 0 或 1，所以该 profile 暂时 flat。需要 3+ strategies 才能 differentiate。
- **Localization 根因：** runtime `has_progress` 只在文件修改时触发（REPAIR/VALIDATION），不在文件探索时触发（LOCALIZATION）。离线诊断通过 regex 从 bash_digest 恢复文件路径，证明 agent 确实在探索文件。建议加 `touched_file_paths` 到 trace。
- **Paid-run readiness：** Gate checklist 6/7 PASS。唯一未满足：3+ strategy task pool for discriminative_rarity。给出了 $0.50 paid smoke design（2 tasks × 2 strategies），但建议等 touched_file_paths 修复后再执行。

### 045 后 Phase O 状态

- **Phase O 完成：** Value Matrix + Progress Calibration 基础设施已建成。`src/budgetflow/value_matrix.py` 支持 4 种 ex-ante/cross-strategy value profile（equal, difficulty, solve_rarity, combined）+ sensitivity analysis + 自定义 profile。Progress calibration 从 639 turns 中提取 (stage, tier) 进度率，确认 selection-bias caveat。AutoResearch 回归 186 tests + goal-loop smoke exit 0。**结论与 Phase N 一致：暂不启动 paid run。** 详细报告：`docs/reports/045.md`。
- **Value profiles 的 rank correlation：** difficulty 与 combined 高度相关 (ρ=0.94)，difficulty 与 solve_rarity 中度相关 (ρ=0.44)。不同 profile 对 task 排序不同，说明 value model 的选择会影响 allocation 决策。
- **Progress calibration 关键发现：** LOCALIZATION progress signal 是死的（215 turns, 0% rate）。REPAIR T2=41% vs T3=24%，但这个负 delta 是 selection bias（T3 处理更难的情况），不能误读为"T3 更差"。
- **Paid-run readiness 判断不变：** value matrix 框架就绪但 specific paper value model 未选定；progress table 已 calibrate 但有 selection-bias confound，不能直接插入 routing formula。仍需 de-bias 或 held-out calibration。

### 044 后 Phase N 状态

- **Phase N 完成：** value-aware offline rescore 工具已实现（`src/budgetflow/value_rescore.py`），32 tests pass。030/031 re-score 完成：BF 不赢 BO，两种 value profile 均一致。Second-claim 证据评级：WEAK。建议暂不启动 paid run，先设计 value proxy + calibrate progress table。详细报告：`docs/reports/044.md`。
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

- **Phase U (051)**：首次 3-policy value-stress experiment。5 tasks × 3 strategies (BO/SB/BF), 15/15 rows, $1.50。BF LOSES: 3/5 vs 4/5 PASS。BF 20% 更贵。First Claim 无独立证据。Second Claim 不支持。KV/cache downside 确认。详细报告：`paper1/docs/reports/051.md`。
- **Phase T (050)**：P0 value matrix lookup fix (wrong schema: `matrix[profile]` vs `tasks[id].values[profile]`)。touched_file_paths text_regex 增强。049 smoke checker CLEAN。Expanded paid smoke 6/6 PASS ($0.66)。BF 36% 更便宜，56% 更高 RVPD。127 tests pass。详细报告：`paper1/docs/reports/050.md`。
- **Phase S (049)**：Provider migration recovery + real preflight + paid smoke 4/4 PASS ($0.36)。Diagnose Phase R 401 as false blocker (missing `.env`)。Shell-sourcing keys for secure migration。BF 22% cheaper, 29% higher RVPD。详细报告：`paper1/docs/reports/049.md`。
- **Phase O (045)**：Value Matrix + Progress Calibration 基础设施。4 种 ex-ante value profile（equal/difficulty/solve_rarity/combined）+ sensitivity analysis + 自定义 profile。Progress calibration 从 639 turns 确认 selection-bias caveat。LOCALIZATION progress signal 发现为死信号（0% rate）。AutoResearch 回归 186 + goal-loop smoke exit 0。272 tests pass。建议暂不启动 paid run。详细报告：`paper1/docs/reports/045.md`。
- **Phase N (044)**：Value-aware offline rescore。新增 `value_rescore.py`（equal/heuristic/custom profile）。030/031 re-score：BF 不赢 BO。Routing trace audit：second-claim evidence WEAK。建议暂不启动 paid run。32 tests pass。详细报告：`paper1/docs/reports/044.md`。
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
- 已写：`reports/006.md`、`007.md`、`008.md`、`009.md`、`010.md`、`011.md`、`012.md`、`015.md`、`016.md`、`039.md`、`040.md`、`041.md`、`042.md`、`043.md`、`044.md`、`045.md`、`046.md`。
- 已补：mini-swe-agent 依赖，compare runner import/`--help`/全链路恢复。
- 已实现/接入：Value-Driven Budget Allocation v1（旧称 Automatic Budgeting）与 memory 写入。Memory 已清理（备份至 `.bak_010`），下次运行自动新建。
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
| Value-Driven Budget Allocation v1 | ✅ Memory 清洁，cap 已校准为真实 USD，10-task prior |
| Value-Driven Budget Allocation continual learning | ✅ 默认写 memory；应用 learned cap 仍需显式开启 |
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
| Value Matrix + Progress Calibration | ✅ Phase O：4 profiles, sensitivity, 639-turn calibration, selection-bias documented |
| Paid-run readiness | ⚠️ Phase P 判断：gate 6/7 PASS，缺 3+ strategy pool + touched_file_paths trace fix |
| Value matrix profile fix + manifest + localization diag | ✅ Phase P：discriminative_rarity + unsolved_difficulty, manifest, 63.3% loc activity recovered |
| AutoResearch goal-loop + owner_decision + commit/push | ✅ Phase K：`goal-loop` 一键闭环；owner_decision.md；safe commit/push |
| AutoResearch real API goal-loop smoke + dispatch | ✅ Phase L：dispatch wrapper；real API goal-loop；push-path validated |
| AutoResearch infra audit + paper doc consistency | ✅ Phase M：186 tests pass；no-paid smoke exit 0；4 docs audit clean |
| Value-aware offline rescore | ✅ Phase N：`value_rescore.py` + 32 tests；030/031 re-score done；second-claim WEAK |

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

难度系数跟模型无关——同一题在 all_flash 和 budgetflow_full 下按同一比例缩放。这个系数是 Value-Driven Budget Allocation 的冷启动核心。

012 新增 5 task 的 real-USD 校准值已写入 `_HISTORICAL_PRIOR`（见 auto_budget.py）。

---

## Value-Driven Budget Allocation 路线图

**目标：不跑 pilot，直接给任务估 budget。**

当前状态：

- 已有历史难度系数和 soft-budget 设计。
- `GovernorConfig` 支持 `soft_budget` / `max_overrun`，`run_mini_swe_compare` 暴露对应参数。
- **Value-Driven Budget Allocation v1 已上线：** `_HISTORICAL_PRIOR` 10-task 冷启动 + kNN memory learning + bucket fallback。
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
- `auto_budget.py` — Value-Driven Budget Allocation v1: `_HISTORICAL_PRIOR` + kNN memory + bucket fallback
- `local_harness.py` — worktree 管理 + harness eval（含 `_remove_worktree` / `_worktree_add`）
- `compare_checkpoint.py` — checkpoint/resume 状态持久化

# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 2026-06-22 — Current status (in progress, not final evidence)

- **2026-06-23 / 3x30 stage 2+3 completed after soft-gate fix:** completed
  `mainline_3x30_lhm_cycle_stage23_softgate_kv50_20260623` (60/60 rows).
  Stage 2 showed a real cost-efficiency signal: BF task-level matched pure T3
  Yield 6.0 while spending `$2.2158` vs pure T3 `$2.6567` (Yield/$ 2.7078 vs
  2.2585). Stage 3 reversed the result: BF selected T3 on all 10 tasks but
  finished 4/10, Yield 4.0, cost `$1.9724`, below pure T3's 5/10, Yield 5.0,
  cost `$1.7425`. The stage 3 failure is not a T2/T3 routing-ratio bug; it is a
  Claim 2 warning that BF's task-level control path must preserve pure-T3
  productivity when it degenerates to all Strongest Model, or save enough
  failed-task spend to compensate. Short report:
  `paper1/docs/reports/mainline_3x30_stage23_softgate_result_20260623.md`.
- **2026-06-23 / 3x30 task-start budget gate routefix:** stopped
  `mainline_3x30_lhm_cycle_kv50_20260623` after early evidence showed
  BudgetFlow routing a high-value Seaborn task to T2 even though pure T3 solved
  it faster and cheaper. Root cause was a task-start hard veto:
  conservative `strongest_expected_total_cost > effective_task_budget` overrode
  the marginal Yield/$ frontier. The shared compiler/runtime entry point now
  exposes `budget_soft_allows_strongest` with a 50% strongest-cost coverage
  floor while preserving hard blocks for tiny caps. Recompiled routefix KV50
  plan is PASS with first-10 `5 T2 / 5 T3` and full-30 `17 T2 / 13 T3`;
  readiness 10/20/30 passes. Prior stopped 3x30 runs are forensic-only; the
  next paid attempt should use a new stem.
- **2026-06-22 / Agent-shell contamination fix:** the cold 4x30 stage-1 paid
  run `mainline_4x30_cold_contractfix_stage1_20260622` halted correctly on
  `host_dependency_contamination` after a runtime worktree editable Matplotlib
  install leaked into global site-packages. Added per-worktree agent-shell venvs
  so agent `pip install -e .` commands write into task-local environments, not
  global Python. Cleaned the host contamination; detector now reports zero
  contamination. Trusted pre-halt scoreable rows remain diagnostic evidence;
  invalid abort rows must be retried and excluded from learning/paper metrics.
- **2026-06-22 / Pre-paid 4x30 contract fixes:** closed three paid-run
  blockers before any next run: compiler/runtime task-start effort scaling now
  shares one catalog-runway helper, task-start observability separates planned,
  effective, and runtime task budgets, and active Task Effort inputs now consume
  `final_task_effort` without falling back to retired
  `task_effort.bootstrap_heuristic`. Current 4x30 artifacts were regenerated
  without retired effort fields. The historical-calibrated stage-pressure plan
  is correctly **BLOCKED** as pure Strongest Model (`30 T3 / 0 T2`); the
  cold/no-history stage-pressure plan is readiness **PASS** with mixed
  `15 T2 / 15 T3`, but remains `projection_confidence=unvalidated`.
- **2026-06-22 / Stage-pressure Budget Compiler ready:** added a single
  compiler entrypoint for tight budget regimes:
  `budget_binding calibrate --stage-prefix-count N
  --stage-target-budget-fraction X --stage-reference-strategy STRATEGY`.
  The historical-calibrated 4x30 plan
  `paper1/docs/reports/mainline_4x30_stage_pressure35_budget_plan_20260622.json`
  sets hard cap `$9.6933` so the first 10 tasks' bare T3 projected spend is
  exactly 35% of total budget, but paid-readiness correctly blocks it because
  task-level BudgetFlow projects pure Strongest Model under historical
  calibration. The cold/no-history stage-pressure plan is the only current
  readiness-pass candidate, and it remains diagnostic because projection
  confidence is unvalidated.
- **2026-06-22 / No-paid gate fixes before 4x30 reset:** restored
  shared-cap-aware planned task budget rebalance, split compiler planned task
  runway from runtime effective task cap, added completed-prefix calibration
  audit for 10+10+10 stages, and softened the cold-start task-level effort
  boundary so near-threshold hard SWE tasks can use bounded Strongest Model
  probes. Re-audit of the stopped 4x30 stage-1 now blocks continuation because
  pure T3 used only 54.4% of its stage budget share; the next paid attempt must
  be a clean restart with a recompiled tighter budget plan.
- **2026-06-22 / 4x30 stage-1 stopped for mechanism diagnosis:** staged
  `mainline_4x30_tasklevel_frontier_20260622-0` was stopped after 38/40 stage-1
  rows. BudgetFlow task-level completed 10/10 with Yield 5.0, cost $3.1007,
  Yield/$ 1.6125; pure T3 completed 10/10 with Yield 6.0, cost $3.3926,
  Yield/$ 1.7685. BudgetFlow beat enterprise and partial pure T2 on Yield/$
  but did not beat the pure T3 frontier, so do not continue stage 2 with this
  policy. The main diagnosis is T2 turn inflation and task-level frontier
  misroutes, not provider/infra failure. Offline KV-cache sensitivity for T2/T3
  multi-turn input discounts did not flip the ranking.
- **2026-06-22 / Frontier-boundary routing contract:** current work is
  studying BudgetFlow task-level left/right boundaries, not tuning for one run.
  The left boundary is reference-tier dominance or mostly-T2 with bounded
  Strongest Model probes; the right boundary is Strongest Model dominance when
  it is projected cheaper in total and materially higher fit. Fixed-tier
  BudgetFlow is now acceptable only when trace/readiness explains it as an
  explicit frontier decision; silent pure T2 or pure T3 still trips guards.
- **No-paid fixes completed:** task-start marginal Yield no longer double-counts
  the T3 price ratio, compiler/runtime use the same paid-upgrade gates, cold
  start can do bounded uncertainty probes, missing tier backends fail fast, and
  readiness treats reference-cost-dominant and strongest-cost-dominant
  frontiers symmetrically. The pressure contract now builds after frontier
  diagnostics so a frontier assertion is not also reported as degeneration.
- **Dry-run boundary checks:** cold-start 4x30 projection is mixed
  `24 T2 / 6 T3` with `reference_cost_dominant` warning and readiness PASS.
  Stage-1-calibrated projection is pure T3 with `strongest_cost_dominant`
  warning and readiness PASS. Both are diagnostic, not paper evidence.
- **Verification:** focused no-paid tests passed (`145 passed`), broader related
  suite passed (`142 passed, 5 skipped`), edited modules passed `py_compile`,
  and `git diff --check` passed before this documentation update.

- **Previous agent:** hardened paid-run harness gates; switched scoring to
  workspace-diff-only; raised the step limit to 60; fixed planned-task-budget
  mode behavior; switched the T2 catalog slot to DeepSeek V4 Pro; and treated
  the 4x25 attempts as partial/diagnostic only. Those runs exposed remaining
  harness/runtime risks rather than producing paper-grade evidence.
- **Current main agent:** keeping the current BudgetFlow runtime and running a
  no-paid infrastructure/diagnostic path only. New committed slices harden
  resume accounting from scoreable JSONL rows, keep abort rows retryable, add
  explicit T3 routing-trigger attribution, surface frontier/model-fit
  diagnostics in compact audit, and auto-write official SWE-bench cross-check
  dry-run artifacts after compare runs. These changes do not tune routing
  thresholds or change the BudgetFlow runtime policy.
- **4x25 partial interpretation:** `mainline_4x25_glm51_harness_v2_20260620`
  remains diagnostic-only: 61/100 rows, one Seaborn host-dependency infra
  invalid row, two billing/provider aborts, and uneven strategy progress. It
  exposed old task-level T2-heavy behavior and harness trust risks, but it is
  not paper evidence.

## 2026-06-19 — Harness v2 workspace-diff validation

- **Post-v2 upstream reflection complete.** Re-audited
  `mainline_4x25_glm51_rerun_after_billing_20260618-0` after the v2 slice.
  Removed the checker noise that treated historical submission rows as missing
  `workspace_patch`, persisted `trace_dir`/`trace_steps` for future diagnosis,
  and added regression coverage that baseline-only compat diffs are not scored
  as agent workspace patches.
- **Old partial interpretation:** still diagnostic-only. The remaining real
  issues are 2 old BudgetFlow incomplete rows, partial run status, dead
  heartbeat PID, and cost-accounting summaries. `sympy__sympy-24102` would now
  be a scoreable trusted fail under v2; `sympy__sympy-11870` was baseline/compat
  diff noise that v2 prevents from being scored. T3's 4/12 is not a harness
  incomplete artifact, but it is also not comparable to other strategies because
  the partial stopped with uneven strategy progress.
- **Evaluation harness v2 slice complete.** The no-Docker SWE runner now scores
  runner-side `workspace_diff` patches first and keeps `submitted.patch` as
  auxiliary protocol evidence. This aligns the scoreable artifact with the
  actual repository edits rather than the custom submit protocol.
- **Why it matters:** a real-agent 3-task validation produced 3/3
  `patch_source=workspace_diff` trusted passes. Two of those three rows had no
  `submitted_patch`, so the previous submitted-patch-only path would have lost
  scoreable evidence.
- **Validation:** focused no-paid tests passed (`132 passed`), full no-paid
  suite passed (`680 passed`), `py_compile` and `git diff --check` passed, and
  the real-agent run `data/runs/harness_v2_real_agent_3x1.jsonl` passed checker
  with 0 errors.
- **Evidence status:** this is harness/observability validation, not paper-scale
  Claim 1 evidence. It is the new rollback/forward point for patch extraction
  behavior after the earlier `7b63b23` rollback checkpoint.

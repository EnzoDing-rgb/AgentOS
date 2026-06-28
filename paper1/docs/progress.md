# BudgetFlow — 状态与结果

> 单一入口：进度、跑法、历史结果。

## 2026-06-29 — 5x30 evaluation audit and no-paid fixes

- Stopped paid runs. The current 5x30 line is diagnostic, not paper evidence:
  RouteLLM, budget-only, and BudgetFlow reached 30/30, pure T2 exhausted budget
  at 24/30, and pure T3 is partial at 14/30 after a runner crash.
- Evaluation audit found no fake pass and no resolved-looking false negative in
  the latest JSONL. The risk was reporting: partial lanes, abort rows, and
  scoreable rows must be shown separately before drawing Claim 1 conclusions.
- Fixed no-paid bugs: non-UTF8 workspace diff crash, task-start rule/reason
  mismatch, high-pressure probe guard attribution, paid-abort resume accounting,
  and contradictory harness evidence being silently counted as true fail.

## 2026-06-28 — 5x30 pre-paid prep is ready; do not expand task count

- **Decision:** do not expand the Claim 1 task set to 50. The next paid
  evidence step keeps the fixed 30-task set and adds exactly one baseline,
  making the comparison 5 policies x 30 tasks.
- **New baseline:** `budget_only_baseline`, a value-blind budget-pressure
  control. It sees shared budget pressure and the same generic planned task
  hard cap as RouteLLM-inspired and BudgetFlow. It does not read Task Value and
  does not receive BudgetFlow's value-aware routing or stall guard. This tests
  whether budget pressure alone explains the result.
- **Mainline config:** default paper mainline now points at
  `paper1/docs/config/paper_mainline_strategies.v2.json` with this order:
  pure T2, pure T3, RouteLLM-inspired router, budget-only baseline,
  BudgetFlow task-level. Use `--jobs 5` for the next paid run unless a concrete
  blocker is documented.
- **No-paid budget plan:** generated readiness candidate
  `paper1/docs/reports/mainline_5x30_value_blind_stage_prefix_cold_budget_plan_20260628.json`.
  It keeps the same shared hard cap as the 4x30 line, `$10.4441`, uses the same
  stage-prefix pressure rule, and passes the pressure contract. Planned task
  hard caps apply to RouteLLM-inspired, budget-only, and BudgetFlow.
- **Readiness gate:** `paid-readiness-only` passes for the 5-policy setup with
  the frozen RouteLLM plan and pre-registered value matrix. Projection
  confidence remains `unvalidated`, so the plan is a valid paid-run candidate,
  not a final claim by itself.
- **4x30 evidence audit:** wrote
  `paper1/docs/reports/mainline_4x30_claim1_matrix_order_audit_20260628.md`.
  It confirms the current readout: BudgetFlow wins Total Resolved Value
  (`18.50` vs pure T3 `18.00`) and Total Resolved Value / Dollar (`2.32` vs
  `1.90`), while losing Resolved Count by one task (`14/30` vs `15/30`).

## 2026-06-28 — 4x30 clean-resume Claim 1 readout

- **Run completed:** `mainline_4x30_lhm_cycle_4policy_cleanresume_20260627`
  finished the 4-policy Claim 1 comparison under the shared hard cap. The
  launch was from the repo root; the earlier `paper1/` path issue wrote no task
  rows and is not part of this evidence line.
- **Main result:** BudgetFlow did **not** win all three headline metrics, but
  the result is still strong for Claim 1. It resolved one fewer task than pure
  T3, while producing higher Total Resolved Value at lower spend.

  | Policy | Resolved Count | Total Resolved Value | Total Spend | Total Resolved Value / total$ |
  |---|---:|---:|---:|---:|
  | pure T2 | 12/30 | 13.50 | $10.44 | 1.29 |
  | pure T3 | 15/30 | 18.00 | $9.46 | 1.90 |
  | RouteLLM-inspired router | 13/30 | 15.00 | $9.37 | 1.60 |
  | BudgetFlow task-level | 14/30 | 18.50 | $7.98 | 2.32 |

- **Honest interpretation:** BudgetFlow wins the value objective and the value
  efficiency objective: `18.50 > 18.00` Total Resolved Value, and `2.32 > 1.90`
  Total Resolved Value / total$ against the best pure-tier baseline. It loses
  Resolved Count to pure T3 by one task (`14/30` vs `15/30`). The paper should
  present this as value-aware allocation under a shared cap, not as a raw pass
  count victory.
- **Diagnostics:** the run did not show a provider, path, or hard-budget
  enforcement blocker. The main mechanism issue is policy quality in the back
  half: BudgetFlow saved budget, but several T2 or bounded-runway tasks produced
  patches that failed validation, or stopped before converting progress into a
  verified result. This points to better task-level runway and stop/continue
  decisions, not to Claim 2 segment-level rescue.
- **Checker status:** observability audit completed with warnings, not clean
  green. The important warnings are expected for this run shape: pure T2 hit the
  shared cap and only executed 26/30 rows; several budget-exhausted/no-patch
  rows are incomplete true-fails. There were no suspicious passes, invoice
  accounting was consistent, and provider usage was settled.
- **Evidence status:** use this as a strong diagnostic/positioning result for
  the next draft: BudgetFlow beats pure T3 on Total Resolved Value and value per
  dollar while spending less, but it still needs one more verified task to claim
  a clean three-metric main-table win.

## 2026-06-22 — Current status (in progress, not final evidence)

- **2026-06-23 / Claim 1 sensitivity baseline for draft:** current draft can
  stand on the corrected 3x30 fixed-workload readout plus three offline
  sensitivity views. All use the same completed task set, keep base CostSource
  fixed, and apply documented patch-cleaner forensic corrections only in
  derived analysis.

  **KV Cache Sensitivity, current ValueSource**

  | KV input discount | pure T2 Cost / Y$ | pure T3 Cost / Y$ | BF Cost / Y$ | Yield Winner | Efficiency Winner |
  |---:|---:|---:|---:|---|---|
  | 0% | `$17.9595 / 1.0858` | `$8.7395 / 2.0024` | `$12.7868 / 1.7205` | BF `22.0` | pure T3 |
  | 50% | `$9.7729 / 1.9953` | `$5.1336 / 3.4089` | `$7.1727 / 3.0672` | BF `22.0` | pure T3 |
  | 80% | `$4.8610 / 4.0116` | `$2.9701 / 5.8921` | `$3.8043 / 5.7830` | BF `22.0` | pure T3 |
  | 90% | `$3.2236 / 6.0491` | `$2.2489 / 7.7816` | `$2.6814 / 8.2045` | BF `22.0` | BF |
  | 98% | `$1.9138 / 10.1893` | `$1.6720 / 10.4667` | `$1.7832 / 12.3374` | BF `22.0` | BF |
  | 99% | `$1.7500 / 11.1426` | `$1.5998 / 10.9385` | `$1.6709 / 13.1664` | BF `22.0` | BF |

  **Value Sensitivity, KV50**

  | Value profile | pure T2 Yield | pure T3 Yield | BF Yield | BF vs best baseline |
  |---|---:|---:|---:|---:|
  | `equal` | 18.0 | 16.0 | 20.0 | +2.0 |
  | `current` | 19.5 | 17.5 | 22.0 | +2.5 |
  | `current_high_to_2.0` | 21.0 | 19.0 | 24.0 | +3.0 |
  | `current_high_to_2.5` | 22.5 | 20.5 | 26.0 | +3.5 |
  | `top20_effort_critical` | 22.5 | 20.5 | 25.0 | +2.5 |
  | `top33_effort_critical` | 24.5 | 21.5 | 28.5 | +4.0 |
  | `effort_tertiles_1_1.5_2.5` | 27.5 | 24.0 | 31.5 | +4.0 |
  | `both_fail_critical` | 19.5 | 17.5 | 23.5 | +4.0 |
  | `top10_effort_critical` | 24.5 | 21.5 | 28.5 | +4.0 |

  **Budget Cap Sensitivity, KV50 and current ValueSource**

  | Cap | pure T2 Yield / Cost / Y$ | pure T3 Yield / Cost / Y$ | BF Yield / Cost / Y$ | Yield Winner | Efficiency Winner |
  |---:|---:|---:|---:|---|---|
  | `$3.00` | `9.5 / $2.9401 / 3.2312` | `10.0 / $2.9445 / 3.3961` | `13.5 / $2.9813 / 4.5283` | BF | BF |
  | `$4.00` | `12.5 / $3.9541 / 3.1612` | `14.5 / $3.9682 / 3.6540` | `16.0 / $3.9972 / 4.0028` | BF | BF |
  | `$5.00` | `12.5 / $4.9650 / 2.5176` | `17.5 / $4.9101 / 3.5641` | `18.0 / $4.9581 / 3.6304` | BF | BF |
  | `$6.00` | `13.5 / $5.9444 / 2.2710` | `17.5 / $5.1336 / 3.4089` | `20.0 / $5.9992 / 3.3338` | BF | pure T3 |
  | `$7.00` | `15.5 / $6.9965 / 2.2154` | `17.5 / $5.1336 / 3.4089` | `22.0 / $6.9740 / 3.1546` | BF | pure T3 |
  | `$8.00` | `17.5 / $7.9361 / 2.2051` | `17.5 / $5.1336 / 3.4089` | `22.0 / $7.1727 / 3.0672` | BF | pure T3 |
  | `$9.00` | `17.5 / $8.9609 / 1.9529` | `17.5 / $5.1336 / 3.4089` | `22.0 / $7.1727 / 3.0672` | BF | pure T3 |
  | `$11.02` | `19.5 / $9.7729 / 1.9953` | `17.5 / $5.1336 / 3.4089` | `22.0 / $7.1727 / 3.0672` | BF | pure T3 |

  Readout: BF's corrected Yield advantage is stable across value profiles and
  KV assumptions. The budget mechanism is strongest when cap is actually
  binding: in offline KV50 replay at `$3-$5`, BF wins both Yield and Yield/$.
  The next paid run should therefore be pre-registered as binding cap plus a
  wider ValueSource, rather than another loose-cap repetition.

- **2026-06-23 / Claim 1 offline sensitivity and recost fix:** fixed the
  offline `budgetflow.recost` sensitivity tool so `--ratios 5.0` means target
  `T3 = 5x T2`, not an extra multiplier on an already-5x catalog; high KV
  sensitivity no longer silently floors KV90/98/99 to KV50. New offline report:
  `paper1/docs/reports/claim1_offline_sensitivity_20260623.md`. Key readout:
  with current values, BF keeps the highest corrected Yield across KV0/50/80/90
  /98/99. Pure T3 remains best Yield/$ at KV0/KV50/KV80, while BF overtakes on
  Yield/$ at KV90+ and in tighter-cap KV50 replay at roughly `$3-$5`. This
  supports treating KV cache as explicit sensitivity, not as a hidden CostSource
  change.

- **2026-06-23 / Claim 1 cost-value diagnostic:** the corrected full 3x30 run is complete (90 scoreable rows). BudgetFlow's extra turns come from T2-routed tasks, not from a systemic all-T3 runtime slowdown: on the 13 tasks where BF used all T3, BF turns were 102 vs pure T3's 103. On the 17 BF-all-T2 tasks, BF used 512 turns vs pure T3's 123 on those same tasks. Value sensitivity does not flip the Claim 1 Yield result: equal values give BF 20.0 vs pure T2 18.0 and pure T3 16.0; current values give BF 22.0 vs 19.5/17.5. Short report: `paper1/docs/reports/claim1_cost_value_diagnostic_20260623.md`.
  Follow-up offline diagnostics show the next paid-run issue is T3-route
  precision and stop-loss, not simple T3 recall: the task set has only one
  T3-only task, BF catches it, but BF also routes many non-exclusive tasks to
  T3 and lets several ceiling tasks consume long T2 runs. CostSource should stay
  fixed; next sensitivity should use a wider pre-registered ValueSource
  gradient and better high-effort no-progress stop discipline.

- **2026-06-23 / Patch-cleaner false-negative fixed; Claim 1 re-read:**
  found and fixed an evaluation bug where `clean_scoreable_patch()` used
  `.rstrip()` and could remove a trailing blank-context line from a valid git
  diff, causing `model_patch=error: corrupt patch`. Canonical case:
  `sphinx-doc__sphinx-8801` BF task-level selected T3 and originally failed
  patch apply; re-evaluating the original submitted patch after the cleaner fix
  resolves. Historical JSONL remains immutable; forensic re-read of the full
  30-task run `mainline_3x30_lhm_cycle_routefix_kv50_20260623` gives corrected
  Yield: pure T2 `19.5`, pure T3 `17.5`, BudgetFlow task-level `22.0`.
  Corrected Yield/$: pure T2 `1.9953`, pure T3 `3.4089`, BudgetFlow
  task-level `3.0672`. Initial draft scope is now Claim 1 only; Claim 2 is
  parked. Short report:
  `paper1/docs/reports/patch_cleaner_false_negative_fix_20260623.md`.
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

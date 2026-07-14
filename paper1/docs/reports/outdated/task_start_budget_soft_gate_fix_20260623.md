# Task-start budget soft gate fix (2026-06-23)

Objective: fix a task-level routing contract bug exposed by the stopped
`mainline_3x30_lhm_cycle_kv50_20260623` stage-1 run. A high-value Seaborn task
cleared the marginal Yield/$ frontier, but BudgetFlow still chose T2 because
the conservative T3 expected-total-cost forecast exceeded the live effective
task cap.

Change:
- Kept `task_start_tier_decision()` as the single compiler/runtime routing
  entry point.
- Added `TASK_START_STRONGEST_MIN_BUDGET_COVERAGE = 0.50`.
- Split the old hard `budget_allows_strongest` veto from an observable
  `budget_soft_allows_strongest` gate.
- Extremely small task caps still hard-block T3. High-value or effortful
  cold-start tasks can probe T3 only when fit gain, marginal Yield/$, pressure,
  and budget coverage all clear the shared gate.

Resulting no-paid plan:
- `mainline_3x30_lhm_cycle_routefix_stage_prefix10_kv50_budget_plan_20260623.json`
- decision `PASS`, hard cap `$10.2310`
- first 10 projection: `T2=5 / T3=5`
- full 30 projection: `T2=17 / T3=13`
- `mwaskom__seaborn-3190` now projects T3 with reason
  `uncertain_frontier_probe`.

Verification:
- `test_task_level_expected_cost.py`: 37 passed
- related no-paid suite: 208 passed
- `py_compile`: OK
- `git diff --check`: clean
- paid readiness for staged 10/20/30: PASS

Residual risk: projection confidence remains `unvalidated`, as expected for
the cold KV50 routefix plan. The next paid attempt should use a new run stem
and treat prior stopped runs as forensic only.

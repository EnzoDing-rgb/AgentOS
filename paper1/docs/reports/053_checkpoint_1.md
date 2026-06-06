# 053 Checkpoint 1 — 2026-06-06 01:57 UTC

## Status: Experiment in progress

### Environment
- Provider preflight: T1 PASS (DashScope qwen3-coder-flash, 976ms), T2 PASS (DashScope qwen3-coder-plus, 475ms), T3 PASS (AICode007 gpt-5.4, 4489ms)
- CLI strategy recognition: all 4 strategies recognized (bo2, bo, bf, bfc)
- Tests: 141/141 passed (Phase V + value obs + value matrix + scoreboard + bash stage)

### Per-task-cap experiment (running)
- 10/12 rows complete
- Design: 3 tasks × 4 policies, per-task cap $0.15
- Tasks: sympy-13480, sympy-13647, sympy-16988
- Policies: budget_only_t2_tight, budget_only_tight, budgetflow_full_tight, budgetflow_conservative_tight
- Expected total cost: ~$1.50

### Early observations (10 rows)
- BFC (conservative) shows lower pass rate than BF so far: BO2 failed sympy-16988, BFC failed sympy-13647 and sympy-16988
- BF full passed sympy-13647 and sympy-16988
- Need all 12 rows for complete analysis

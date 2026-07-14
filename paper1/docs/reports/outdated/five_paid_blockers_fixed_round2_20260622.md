# Five paid-run blockers fixed — round 2 (2026-06-22)

**Date:** 2026-06-22
**Scope:** `paper1/src/budgetflow/`, `paper1/docs/config/`, `paper1/tests/`
**Decision:** Verified (no paid providers)

## Changes

### 1. Regenerated 30-task stage-prefix KV50 budget plan

Old 20-task Sympy plan deleted. New plan generated from:
- Task order: `docs/reports/mainline_4x30_stratified_task_order_20260622.json` (30 tasks, 3 stages of 10)
- Value matrix: `docs/reports/mainline_4x30_criticality_value_matrix_20260622.json` (criticality_value profile)
- Catalog: KV50 (symmetric 50% T2/T3 post-first-turn input discount)
- Mode: `stage_prefix_pressure` with `stage_prefix_count=10`
- Strategies: bare_t2_baseline, bare_t3_baseline, budgetflow_task_level

Plan saved to `docs/reports/mainline_4x30_stage_prefix10_kv50_budget_plan_20260622.json`.

| Metric | Value |
|--------|-------|
| hard_cap_usd | $9.29 |
| generation_mode | stage_prefix_pressure |
| decision | PASS |
| projected_spend (bare_t2) | $3.2189 |
| projected_spend (bare_t3) | $11.0363 |
| projected_spend (budgetflow) | $5.7609 |
| degeneration (overall) | mixed (T2=18, T3=12, 40% T3) |
| stage prefix degeneration | mixed (T2=6, T3=4, 40% T3 first 10) |
| pressure_contract | grade=pass |
| frontier_diagnostic | mixed_or_unproven |

Mixed tier usage — not pure T2 or pure T3 — readiness gate passes.

### 2. Projection observability — routing_reason and routing_scores

`budget_binding.py` `_project_task_level_choice_cost()` now returns `(tier, cost, routing_reason, routing_scores)` instead of `(tier, cost)`. `_build_projection_diagnostics()` records both fields in each `task_choices` entry:

```json
"task_choices": {
  "django__django-15814": {
    "runtime_projected_tier": 2,
    "projected_cost_usd": 0.0823,
    "routing_reason": "reference_frontier",
    "routing_scores": {"rule": "reference_frontier", "t3_acceptance_margin": 0.1, ...}
  }
}
```

This is critical Claim 2 mechanism evidence: "why did these tasks get T3 / why not T3?"

### 3. Runtime observability — last_policy_decision.reason fixed

`strategies.py` `_choose_task_level_backend()` now sets `last_policy_decision.reason` to the real routing reason (`marginal_yield_per_dollar`, `uncertain_frontier_probe`, `reference_frontier`) instead of the generic `"task_level_fixed_task_start"` label. `last_policy_decision.scores` already carried the complete scores dict from the shared function.

Also restored the call to `_task_level_max_tier(ctx)` that was dropped in the session-1 refactor, fixing `ctx.max_tier` and `ctx.tier_frontier_score` for `value_aware_task_level` strategy.

### 4. Catalog revisions bumped to 2026-06-22

| File | Old revision | New revision |
|------|------------|-------------|
| model_tiers.default.json | 2026-06-20 | 2026-06-22 |
| model_tiers.t3x2.json | 2026-06-20 | 2026-06-22 |
| model_tiers.t3x3.json | 2026-06-20 | 2026-06-22 |
| model_tiers.kv50.json | 2026-06-22 | (unchanged) |

Revision notes mention T3 progress_prior update. Prevents drift in `catalog_record_exact_match()` fallback.

### 5. progress_score and progress_prior semantics unified

**Before:** task-level `progress_score` said T3=0.35 (stronger than T2's 0.24), but stage-level `progress_prior` said T3 only 0.01-0.03 above T2. Two conflicting ModelFit stories.

**After:** T3 `progress_prior` updated in all 4 catalog files:

| Dimension | T2 | T3 (old) | T3 (new) | Delta |
|-----------|----|---------|---------|-------|
| localization | 0.67 | 0.68 | 0.72 | +0.05 |
| repair | 0.65 | 0.68 | 0.72 | +0.07 |
| validation | 0.63 | 0.66 | 0.70 | +0.07 |

`progress_score` is the task-level cold-start prior (used by `task_level_routing.py`). `progress_prior` is the stage-level decomposition (used by `tier_frontier.py` and observability). Both now express the same hypothesis: T3 has a meaningful capability advantage over T2.

### 6. t3_acceptance_margin field bug fixed

`task_level_routing.py` `_scores()` line 315 now records `TASK_START_T3_ACCEPTANCE_MARGIN` (=0.10) instead of `TASK_START_COLD_FRONTIER_EFFORT_TOLERANCE` (=0.95) for the `t3_acceptance_margin` field. Added import of `TASK_START_T3_ACCEPTANCE_MARGIN` from `defaults`. Test added: `test_t3_acceptance_margin_uses_correct_constant`.

### 7. Lightweight observability tests added

Three new tests in `TestObservabilitySeams`:
- `test_t3_acceptance_margin_uses_correct_constant` — prevents field-value bug regression
- `test_last_policy_decision_reason_is_real_routing_reason` — verifies reason is not generic
- `test_runtime_compiler_parity_cold_start_probe` — verifies runtime and compiler produce identical tier/reason/scores for the same inputs

## Test changes

### Added tests (3 in TestObservabilitySeams)

See section 7 above.

### Updated tests

- `test_compiler_projection_matches_effortful_cold_start_probe` — unpack 4-tuple, assert routing_reason/routing_scores
- `test_compiler_projection_matches_near_boundary_cold_start_probe` — same
- `test_two_tier_catalog_fallback_reference_cheapest` — added explicit `max_turns: 35` to mock (pre-existing regression from `FRONTIER_DEFAULT_RUNWAY_TURNS` changing to 60)
- `test_tier_frontier.py` — 3 `TestMaxTierWithFrontier` tests now pass (restored `_task_level_max_tier` call)

## Verification

```
PYTHONPATH=src pytest -q \
  tests/test_task_level_expected_cost.py \
  tests/test_budget_binding.py \
  tests/test_compare_readiness.py \
  tests/test_compare_setup.py \
  tests/test_compare_record_schema.py \
  tests/test_model_tiers.py \
  tests/test_tier_frontier.py

234 passed in 8.20s
```

```
py_compile: task_level_routing.py PASS, strategies.py PASS, budget_binding.py PASS
All 4 catalog JSONs valid, T3 progress_score=0.35 confirmed, T3 progress_prior={0.72, 0.72, 0.70}
KV50 budget plan: docs/reports/mainline_4x30_stage_prefix10_kv50_budget_plan_20260622.json
```

## Uncertainties

- T3 progress_prior values (0.72/0.72/0.70) are heuristic — must be sensitivity-checked before paper-scale paid runs
- No calibration evidence in plan (bootstrap_estimate only) — projection confidence is `unvalidated`
- KV50 is a diagnostic sensitivity catalog; default (no KV discount) is the primary evidence catalog
- frontier_diagnostic remains `mixed_or_unproven` — needs trusted ModelFit evidence from a calibration run

# Five paid-run blockers fixed before next 4x30 candidate

**Date:** 2026-06-22
**Scope:** `paper1/src/budgetflow/` — task-level routing, catalog prior, tests, budget plan
**Decision:** Verified (no paid providers)

## Changes

### 1. Single shared task-level routing module

`src/budgetflow/task_level_routing.py` — new module with one entry point `task_start_tier_decision()`.

Callers:
- Runtime: `strategies.py` → `_choose_task_level_backend()` calls `task_start_tier_decision()`
- Compiler: `budget_binding.py` → `_project_task_level_choice_cost()` calls `task_start_tier_decision()`

Deleted duplicate code:
- `strategies.py`: `_task_start_effort_multiplier`, `_strongest_price_ratio`, `_expected_total_cost`, `_task_start_t3_score` (~190 lines), `_uncertain_frontier_probe_candidate` (~40 lines)
- `budget_binding.py`: `_projection_effort_multiplier` and mirror tier-selection formulas

The compiler now projects tier choices via the same formula the runtime uses. It does **not** assign model tiers — it only compiles budget, Task Value, Task Effort, CostSource, ModelFit.

### 2. Catalog T3 progress_score prior

All 4 catalog JSON files updated:

| File | Old T3 progress_score | New T3 progress_score | progress_updated |
|------|----------------------|----------------------|-------------------|
| model_tiers.default.json | 0.25 | 0.35 | 2026-06-22 |
| model_tiers.kv50.json | 0.25 | 0.35 | 2026-06-22 |
| model_tiers.t3x2.json | 0.25 | 0.35 | 2026-06-22 |
| model_tiers.t3x3.json | 0.25 | 0.35 | 2026-06-22 |

Old T2=0.24, T3=0.25 gave only 0.01 progress gap — biased routing toward T2. New gap is 0.11, reflecting observed T3 capability advantage.

### 3. KV cache decoupling (unchanged)

KV50 catalog already had symmetric T2/T3 50% post-first-turn input discount via `turn_cache_policy`. No changes needed.

### 4. Stale schema fields cleaned

- `runtime_projected_tier` / `runtime_projected_tier_counts` — already in use in projection diagnostics
- `task_level_model_plan` — already deleted from active paths
- `projected_tier_counts` — renamed to `runtime_projected_tier_counts`
- `task_tier_fit_overrides` — rejected at readiness gate (test exists: `test_budget_plan_model_fit_rejects_retired_task_local_overrides`)
- Retired `difficulty` / `bootstrap_difficulty` — rejected at value feature load (test exists: `test_value_matrix_schema_is_normalized_at_single_projection_entry`)

### 5. No-paid evidence — KV50 budget plan

Regenerated 3-policy 20-task budget plan with KV50 catalog:

```
hard_cap_usd: $10.1250
generation_mode: target_utilization
decision: PASS
projected_spend_by_strategy:
  bare_t2_baseline: $2.3625
  bare_t3_baseline: $8.1000
  budgetflow_task_level: $3.2231
degeneration: mixed (T2=17, T3=3, 15% T3)
pressure_contract: grade=pass
frontier_diagnostic: mixed_or_unproven
```

Plan saved to `data/kv50_budget_plan.json`. Mixed tier usage — not pure T2 or pure T3 — readiness gate passes.

## Test changes

### Deleted tests

| Test | Reason |
|------|--------|
| `TestExpectedTotalCost` (5 tests) | Tested deleted `_expected_total_cost` internal function from strategies.py |
| `test_missing_expected_costs_do_not_make_t3_look_free` | Tested stale "missing cost estimates" special case removed in refactor |
| `test_projection_effort_multiplier_uses_catalog_reference_runway` | Tested deleted `_projection_effort_multiplier` function |

### Rewritten tests (18 in TestChooseTaskLevelBackend)

- Removed `_expected_total_cost` imports and pre-condition assertions
- Updated `last_policy_decision.reason` assertions to `last_decision.reason` (new code uses `task_level_fixed_task_start` for policy reason; routing detail is in `last_decision`)
- Updated score field names: `planned_task_budget` → `task_budget`, removed `reference_frontier_candidate` / `decision_cost_source` / `strongest_price_ratio` / `cost_estimate_available` / `expected_value_gain` (no longer in schema)
- Kept all behavioral assertions: tier selection, budget gating, cold start probe, marginal yield, degeneracy gates

## Verification

```
PYTHONPATH=src pytest -q \
  tests/test_task_level_expected_cost.py \
  tests/test_budget_binding.py \
  tests/test_compare_readiness.py \
  tests/test_compare_setup.py \
  tests/test_compare_record_schema.py \
  tests/test_model_tiers.py

209 passed in 4.42s
```

```
py_compile: task_level_routing.py PASS, strategies.py PASS, budget_binding.py PASS
All 4 catalog JSONs valid, T3 progress_score=0.35 confirmed
```

# Pre-paid Closure Report: Value / Effort / Model Fit Decoupling

Date: 2026-06-15

## Objective

Refactor BudgetFlow from a value-only mixed router into a value-first allocation
system per North Star definitions.  Separate three allocation inputs (Task Value,
Task Effort, Model Fit) into independent namespaces.  Prepare 5x16 artifacts for
paid diagnostic.  Audit and fix schema/artifact consistency as final pre-paid
closure.

## Files Changed (18 files, audit + artifact regeneration)

| File | Change |
|---|---|
| `paper1/src/budgetflow/allocation.py` | **NEW** — AllocationContext dataclass |
| `paper1/src/budgetflow/adapter/runner.py` | Accept allocation param, pass to build_routing_context |
| `paper1/src/budgetflow/adapter/strategies.py` | RoutingContext.allocation field + __post_init__ sync |
| `paper1/src/budgetflow/adapters/swebench_value.py` | Read task_value[profile] only, no values fallback |
| `paper1/src/budgetflow/value_efficiency.py` | Add _extract_effort_lookup, enrich_record writes effort |
| `paper1/src/budgetflow/value_matrix.py` | bootstrap_task_values → bootstrap_task_effort; values → task_value+task_effort+model_fit |
| `paper1/src/budgetflow/experiments/budget_binding.py` | Read task_effort.bootstrap_heuristic, no legacy path |
| `paper1/src/budgetflow/experiments/compare_cli.py` | Remove bootstrap_difficulty from --value-profile choices |
| `paper1/src/budgetflow/experiments/compare_execution.py` | Create AllocationContext, wire AutoBudget→effort, PolicyMemory→model_fit |
| `paper1/tests/test_allocation_context.py` | **NEW** — 10 concept-separation tests |
| `paper1/tests/test_value_efficiency.py` | Fix bootstrap_difficulty → task_effort diagnostic |
| `paper1/tests/test_value_matrix_bootstrap.py` | Update assertions for new schema |
| `paper1/tests/test_policy_backend.py` | Fix test matrix to use task_value key |
| `paper1/tests/test_compare_readiness.py` | Fix test matrices to use task_value key |
| `paper1/tests/test_experiment_observability.py` | bootstrap_difficulty → difficulty profile |
| `paper1/tests/test_test_inventory.py` | Register test_allocation_context.py |

## Deleted Stale Paths (no backward compat)

- `_extract_lookup()` — removed `values[profile]` fallback
- `_load_matrix()` (swebench_value.py) — removed `values[profile]` fallback
- `_load_value_features()` — removed `values.bootstrap_difficulty` legacy read
- CLI: `bootstrap_difficulty` removed from valid `--value-profile` choices

## Current Schema Contract

```json
{
  "tasks": {
    "<instance_id>": {
      "task_value": {"equal": 1.0},
      "task_effort": {"bootstrap_heuristic": <float>, "source": "task_metadata_formula", "features": {...}},
      "model_fit": null
    }
  }
}
```

- `task_value` — Claim 1 input.  Profiles: `equal`, `manual_value`.
- `task_effort` — diagnostic.  `bootstrap_heuristic` from pre-registered task metadata formula.
- `model_fit` — reserved.  Populated from PolicyMemory when enabled, else null.

## AllocationContext Boundary

Three inputs flow through a single dataclass into policy/routing:

```
ValueEfficiencyContext.task_value()  ──→  AllocationContext.task_value
ValueEfficiencyContext.task_effort() ──→  AllocationContext.task_effort
  (bootstrap_heuristic from matrix)
AutoBudget.estimated_cost             ──→  AllocationContext.task_effort (override, when memory)
PolicyMemory.repo_prior().tier_rates ──→  AllocationContext.model_fit (when enabled)
  (else: null, source="catalog_progress_prior")
```

- `RoutingContext.__post_init__` syncs `task_value` from allocation
- `task_value` / `value_source` / `task_effort` / `effort_source` / `model_fit_source`
  written to every JSONL record

## No-paid Gate Results

### Test Suite
```
465 passed, 2 skipped — all clean
```

### 5x16 Artifacts
```
Value matrix coverage:  16/16
Frozen plan coverage:   16/16
Budget cap sum:         $3.58 (matches frozen plan meta.hard_cap_usd)
Budget plan decision:   PASS
Budget plan catalog:    model_tiers.t3x2.json (revision 2026-06-10-t3x2)
Max utilization:        33.2% (bare_t3_baseline), 21.6% (budgetflow_full)
Strategies:             5 (bare_t2, bare_t3, enterprise_router, bf_same_router, bf_full)
No old schema keys:     PASS
task_effort coverage:   16/16
Manual matrix features: consistent with SWE-bench Lite task data (PASS)
Auto-generated matrix:  regenerated, consistent with manual matrix (PASS)
```

### Contamination Checks
```
bootstrap_difficulty as task_value profile:  0 occurrences (deleted)
Old values[profile] fallback:                0 occurrences (deleted)
Bare baselines modified:                     No
```

### Audit Fixes (2026-06-15 closure audit)
```
Manual value matrix django-16046 features:   patch_lines 2→12, effort 8.98→18.98
Manual value matrix django-15388 features:   patch_lines 2→12, effort 10.13→20.13
Auto-generated value matrix:                 regenerated (now consistent with manual)
Budget plan catalog:                         default→t3x2 (matches paid command)
Budget plan regenerated:                     PASS, 33.2% max utilization
Preflight updated:                           utilization, budget binding, risks
```

## Paid Readiness Verdict: GO

All no-paid gates pass.  5x16 artifacts regenerated with new schema.
AllocationContext is the unified input boundary.  Task Value, Task Effort,
Model Fit are auditable in every JSONL row.

## Residual Risks

1. `model_fit` dict is observability-only; not yet wired into per-turn selector decisions
2. PolicyMemory is disabled for Claim 1 main run; model_fit_source defaults to `catalog_progress_prior`
3. The `bootstrap_heuristic` value_source_kind path in `_resolve_value_source_info` is dead code
   (profile names starting with "bootstrap_" can no longer reach it via CLI) but kept for
   diagnostic matrix compatibility
4. `compare_execution.py` still passes `median_task_value` separately from allocation
   (population stat, not per-task input — intentionally kept on RoutingContext)
5. `budget_binding.py._load_value_features` normalises `task_effort.bootstrap_heuristic` into
   a local `bootstrap_difficulty` key internally for cost estimation. Naming is vestigial but
   contained within the calibrator — no runtime impact.

## Exact Next Paid Command

```bash
PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare \
  --strategies "bare_t2_baseline,bare_t3_baseline,enterprise_router_baseline,budgetflow_same_router,budgetflow_full" \
  --ids "sympy__sympy-13480,sympy__sympy-14774,sympy__sympy-16988,sympy__sympy-20212,sympy__sympy-12419,sympy__sympy-19007,sympy__sympy-20154,sympy__sympy-20639,sympy__sympy-15011,sympy__sympy-16792,sympy__sympy-21055,sympy__sympy-23117,django__django-10924,django__django-12113,django__django-16046,django__django-15388" \
  --value-profile manual_value \
  --value-matrix docs/reports/mainline_5x16_manual_value_matrix.json \
  --value-source-kind pre_registered_manual \
  --frozen-plan docs/reports/mainline_5x16_frozen_router_plan.json \
  --model-catalog docs/config/model_tiers.t3x2.json \
  --budget-plan docs/reports/mainline_5x16_budget_plan.json \
  --disable-policy-memory \
  --no-auto-budget-learn \
  --jobs 5 \
  --run-series mainline_5x16_v2
```

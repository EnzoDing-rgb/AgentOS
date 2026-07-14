# No-paid gate fixes before next 4x30 candidate (2026-06-22)

## Objective

Remove five paid-run blockers that would have contaminated the next 4x30
calibrated paper-level candidate. No paid/provider experiments were run. No
historical JSONL was modified. No directory renames.

The strategic posture is unchanged: Claim 1 first, shared hard budget,
maximize verified Yield and Yield per Dollar. BudgetFlow is not required to
be mixed; if Strongest Model truly dominates, T3-heavy routing is acceptable.
But the main experiment plan must not silently degenerate into near-pure
T2/T3 and then claim to be rich task-level routing.

## Files changed

- `paper1/src/budgetflow/defaults.py` — new home for task-level routing
  constants and `task_start_t3_acceptance_threshold`. Shared neutral module.
- `paper1/src/budgetflow/adapter/strategies.py` — imports constants/function
  from `defaults.py`; `_runtime_task_budget` helper prefers
  `effective_task_budget` over `planned_task_budget`; `_expected_cost_fits_task_budget`
  and `_task_start_t3_score` headroom math consume the helper.
- `paper1/src/budgetflow/experiments/budget_binding.py` — imports routing
  constants from `defaults.py` (no longer from `adapter/strategies.py`);
  removed `_merge_task_fit_override`, `_task_fit_overrides_from_plan`,
  `_parse_tier_fit_map`, `task_fit_override` projection parameter, and
  `tier_boundary_source` projection label. `_build_same_task_fit_overrides`
  still writes the annotation to `model_fit_evidence.task_tier_fit_overrides`
  for audit/report-only purposes.
- `paper1/src/budgetflow/experiments/compare_execution.py` — removed
  `calibrated_task_model_fit` parameter and the runtime override of
  `AllocationContext.model_fit`. Runtime no longer consumes task-local
  same-task history.
- `paper1/src/budgetflow/experiments/compare_setup.py` —
  `calibrated_model_fit_from_budget_plan` returns a 3-tuple again; task-local
  overrides in the budget plan are intentionally not parsed into a runtime
  signal.
- `paper1/src/budgetflow/experiments/compare_readiness.py` —
  `stage_prefix_pressure` contract now blocks when `stage_prefix_count`
  exceeds selected task count, when `stage_prefix_count` does not match
  `--max-tasks-per-strategy`, or when task order differs from the budget
  plan. Removed the frontier-posture exemption that downgraded
  `budgetflow_task_level_degenerated` pressure-contract violations to
  warnings; any such violation now blocks.
- `paper1/src/budgetflow/run_mini_swe_compare.py` — reverted to 3-tuple
  unpacking; `calibrated_task_model_fit` no longer threaded to
  `run_strategy_batch`.
- `paper1/tests/test_budget_binding.py` — deleted
  `test_task_level_projection_respects_same_task_t2_success_frontier`.
- `paper1/tests/test_compare_record_schema.py` — deleted
  `test_runner_applies_task_model_fit_override` and
  `test_task_model_fit_override_only_applies_to_task_level`; added
  `test_runner_ignores_task_local_model_fit_override` to lock the
  diagnostic-only contract.
- `paper1/tests/test_compare_setup.py` — deleted
  `test_budget_plan_model_fit_evidence_parses_task_overrides`; added
  `test_budget_plan_model_fit_ignores_task_local_overrides`; reverted
  4-tuple unpackings to 3-tuple.
- `paper1/tests/test_compare_readiness.py` — added
  `test_readiness_blocks_stage_prefix_count_mismatch_with_max_tasks`,
  `test_readiness_blocks_stage_prefix_count_exceeds_task_count`,
  `test_readiness_blocks_stage_prefix_pressure_task_order_mismatch`.
- `paper1/tests/test_task_level_expected_cost.py` — added
  `test_effective_task_budget_overrides_planned_for_t3_affordability`.
- `paper1/docs/progress.md` — trimmed to last few days per repo discipline.
- `paper1/docs/reports/mainline_4x30_stage_pressure35_budget_plan_20260622.json`
  — left in place; its `task_tier_fit_overrides` annotation is now inert at
  runtime. Historical JSONL not modified.

## Interface decisions

1. **Same-task history is annotation-only.** The compiler may still write
   `model_fit_evidence.task_tier_fit_overrides` so reviewers can see which
   tasks had clean same-task T2 wins. But neither the runtime
   `AllocationContext.model_fit` nor the compiler's
   `_project_task_level_choice_cost` tier-fit lookup consumes it. This
   removes the route lock without losing the audit signal.
2. **Effective-first task budget.** `_runtime_task_budget` returns
   `effective_task_budget` when present, otherwise `planned_task_budget`.
   Both `_expected_cost_fits_task_budget` and the headroom math in
   `_task_start_t3_score` go through this helper, so a runtime rebalance
   that shrinks the task cap can no longer be masked by a generous compiler
   cap.
3. **stage_prefix_pressure is order-sensitive.** Task order mismatch is a
   warning under `target_utilization` mode (runtime uses selected order) but
   a block under `stage_prefix_pressure` mode (the prefix spend is
   order-sensitive). `stage_prefix_count` must equal
   `min(--max-tasks-per-strategy, len(tasks))` when the CLI flag is set.
4. **Constants live in `defaults.py`.** `MARGINAL_YIELD_PER_DOLLAR_THRESHOLD`,
   all `TASK_START_*` constants, and `task_start_t3_acceptance_threshold`
   moved from `adapter/strategies.py` to `defaults.py`. Compiler
   (`budget_binding.py`) and runtime (`adapter/strategies.py`) both import
   from the same neutral source. Values unchanged.
5. **Degeneration gate is absolute.** `_apply_task_level_degeneracy_gate`
   blocks any `pure_reference_tier` or `pure_strongest_tier` projection
   regardless of frontier posture. The readiness mirror and the
   pressure-contract violation path no longer exempt
   `strongest_cost_dominant` / `reference_cost_dominant` postures. Frontier
   posture remains a separate warning/diagnostic.

## Deleted stale paths/tests

- `_merge_task_fit_override`, `_task_fit_overrides_from_plan`,
  `_parse_tier_fit_map` in `budget_binding.py`.
- `task_fit_override` parameter on `_project_task_level_choice_cost` and
  `task_fit_overrides` parameter on `_build_projection_diagnostics`.
- `tier_boundary_source` label on `task_choices` projection entries.
- `calibrated_task_model_fit` parameter on `run_task_record` and
  `run_strategy_batch`.
- 4-tuple return of `calibrated_model_fit_from_budget_plan` (back to 3-tuple).
- `_parse_budget_plan_tier_fit` helper in `compare_setup.py` (inlined back).
- Three route-lock tests (listed above).
- Frontier-posture exemption in the `budgetflow_task_level_degenerated`
  pressure-contract handling.

## Verification

```
PYTHONPATH=paper1/src pytest -q \
  paper1/tests/test_budget_binding.py \
  paper1/tests/test_compare_readiness.py \
  paper1/tests/test_compare_setup.py \
  paper1/tests/test_compare_record_schema.py \
  paper1/tests/test_task_level_expected_cost.py
```

Result: `206 passed in 4.08s`.

```
python -m py_compile \
  paper1/src/budgetflow/defaults.py \
  paper1/src/budgetflow/adapter/strategies.py \
  paper1/src/budgetflow/experiments/budget_binding.py \
  paper1/src/budgetflow/experiments/compare_execution.py \
  paper1/src/budgetflow/experiments/compare_setup.py \
  paper1/src/budgetflow/experiments/compare_readiness.py \
  paper1/src/budgetflow/run_mini_swe_compare.py
```

Result: `py_compile OK`.

```
git diff --check
```

Result: clean (exit 0).

## Residual risks

- **Frontier posture still warns.** `reference_cost_dominant` and
  `strongest_cost_dominant` postures still emit readiness warnings. That is
  intentional — the diagnostic signal is preserved. But it means a
  frontier-dominant plan with a *mixed* projection can still pass readiness.
  The gate only fires on pure degeneration.
- **`_build_same_task_fit_overrides` still runs.** It writes annotation
  that nothing consumes. If a future change accidentally wires it back into
  projection or runtime, the route lock returns. The new
  `test_runner_ignores_task_local_model_fit_override` and
  `test_budget_plan_model_fit_ignores_task_local_overrides` guard the
  runtime side; the compiler side is guarded only by deletion of the merge
  helper. A positive compiler-side test (annotation written, projection
  unchanged) would be a stronger guard if regression risk grows.
- **`stage_prefix_count` vs `max_tasks_per_strategy` is a hard equality.**
  If a future staged run legitimately wants the compiled prefix shorter
  than the staged execution limit, this gate will block. That is the
  intended contract — the prefix determines the cap — but it is stricter
  than before.
- **Historical 4x30 plan JSON still contains `task_tier_fit_overrides`.**
  The field is now inert at runtime. Re-running the existing plan will not
  reproduce the old route-lock behavior, so projection may shift. A fresh
  `budget_binding calibrate` is recommended before the next paid attempt.
- **No paid validation.** These are no-paid gate fixes only. The next
  no-paid readiness run on a freshly compiled 4x30 plan is the validation
  step.

## Next recommended slice

1. Recompile the 4x30 stage-pressure budget plan with the current compiler
   so the JSON reflects the new projection (no task-local override
   consumption).
2. Run `run_mini_swe_compare.py --readiness-only` (or equivalent no-paid
   preflight) against the recompiled plan. Confirm:
   - Readiness passes for the stage_prefix_pressure contract.
   - If the projection still degenerates to pure T3, readiness blocks and
     the run must be labeled as a frontier diagnostic, not a 4x30 paper
     candidate.
3. Only after no-paid readiness passes with a non-degenerate projection,
   consider the 10+10+10 paid staged run. If the projection is pure T3,
   do not enter the paid run; treat it as a frontier-diagnostic line and
   revisit ModelFit/value/cost calibration before retrying.

# Task-Level Mechanism Cleanup - 2026-06-16

## Objective

Make the Claim 1 task-level BudgetFlow policy runnable before the paid 6x5
diagnostic by cleaning up routing semantics, removing stale protocol/parser
observability, and validating the 6x5 paid-readiness gate without provider
calls.

## Files Changed

- `src/budgetflow/routing_sets.py`
- `src/budgetflow/adapter/mini_swe_proxy.py`, `strategies.py`, `turn_trace.py`
- `src/budgetflow/adaptive_routing.py`, `selector.py`, `tier_frontier.py`
- `src/budgetflow/experiment_observability.py`, `policy_memory.py`
- `src/budgetflow/run_observability/audit.py`
- `docs/north_star.md`
- focused tests for routing state, task-level observability, tier threshold
  scoring, parser audit buckets, trace fields, readiness, and budget binding

## Interface Decisions

- `value_aware_task_level` is now an adaptive BudgetFlow policy, not a fixed
  baseline/control. It participates in adaptive starter state, rescue,
  progress escalation, reserve floors, and value-triggered escalation.
- Budget pressure is scarcity. It no longer directly opens the strongest tier.
  Strongest-tier access comes from value density or explicit bounded
  progress/rescue paths.
- The strongest-tier advisory score now compares incremental model cost against
  expected value gain over the reference tier runway:
  `incremental_cost_ratio / (progress_delta * task_value * reference_runway)`.
- The old `max_tier_pressure_threshold` runtime path was deleted because it
  encoded the wrong semantics.

## Deleted Or Retired Paths

- Removed the active parser audit bucket for `empty_response`; current runtime
  no longer emits that parser reason.
- Removed the turn-trace field `max_tier_pressure_threshold`; traces now expose
  `tier_frontier_score`.
- Did not rename `tier_frontier` yet. It is a naming issue, not a paid-run
  correctness issue, and changing JSONL schema right before 6x5 would add
  unnecessary noise.

## Verification

- `PYTHONPATH=paper1/src pytest -q paper1/tests/test_value_aware.py paper1/tests/test_tier_frontier.py paper1/tests/test_allocation_context.py paper1/tests/test_learn_policy.py paper1/tests/test_adaptive_routing.py paper1/tests/test_protocol_retry.py paper1/tests/test_trace_fields.py paper1/tests/test_experiment_observability.py paper1/tests/test_compare_readiness.py paper1/tests/test_compare_record_schema.py paper1/tests/test_budget_binding.py`
  - `166 passed, 14 skipped`
- `PYTHONPATH=paper1/src:external/mini-swe-agent/src python -m py_compile $(find paper1/src paper1/tests -name '*.py' -not -path '*/__pycache__/*')`
  - PASS
- 6x5 paid-readiness-only:
  - 5 tasks, 6 strategies
  - `mainline_6x5_budget_plan.json`
  - `model_tiers.t3x3.json` with `--diagnostic-catalog`
  - catalog hash `edd5cb2e038e`
  - hard cap `$0.3321`
  - result: PASS

## Residual Risks

- Projected 90 percent utilization is still unvalidated. The next paid 6x5 is
  a diagnostic to measure actual utilization, protocol stability, and task-level
  policy behavior.
- The long-term cleaner entrypoint is still a single pre-registered run
  manifest. Current readiness gates block known 6x5/6x30 mismatches, but the
  CLI still accepts multiple artifact paths.
- Internal names containing `frontier` remain. They should be renamed later
  only with a deliberate JSONL/schema migration.

## Next Step

Run the paid 6x5 diagnostic. Stop if provider/model access fails, protocol
owner aborts exceed the gate, required trace/cost/value fields are missing, or
actual budget utilization is too loose to support a scarcity claim.

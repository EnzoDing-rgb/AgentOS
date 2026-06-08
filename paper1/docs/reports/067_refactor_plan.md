# 067 Core Refactor Plan

Date: 2026-06-06

## Goal

Make BudgetFlow's T1-first architecture explicit in code before running more paid experiments.

T1 is the North Star: maximize verified resolved task value per dollar. T2 remains as an equal-value mechanism ablation and related-work bridge, not an independent optimization target.

## Non-Negotiables

- Do not edit historical JSONL.
- Do not run paid experiments until focused tests, dry-run gates, and observability checks are clean.
- If BFV/BFC repeatedly underperform BO, investigate learning, routing, observability, inference, task, and harness bugs before treating it as evidence against the paper.
- Keep `run_mini_swe_compare.py` as orchestration, not as the home for value metrics, learning source selection, or schema definitions.

## Module Seams

### 1. `learning_context.py`

Purpose: continual-learning source selection and loading.

- Cap/value-cost memory: `auto_budget_memory.jsonl`.
- Routing memory: full run JSONL with routing outcomes, backend picks, and turn traces.
- The runner should call one interface to load routing `PolicyMemory`.

### 2. `value_efficiency.py`

Purpose: T1/T2 metric semantics.

- Owns task value lookup initialization.
- Enriches rows with `task_value`, `resolved_value`, `value_source`, `yield_per_dollar`, `va_active`, and `task_value_multiplier`.
- Defines T2 as equal-value T1, not a separate metric family.
- Provides compatibility wrappers while tests and runner migrate.

### 3. Routing Observability

Purpose: make routing decisions explainable and learnable.

Each row/turn should expose:

- objective: `t1_value_efficiency` or `t2_equal_value_ablation`;
- value multiplier;
- policy memory source and learned action;
- whether the decision used imitation/fallback;
- why the router escalated, de-escalated, continued, or stopped.

Do not rewrite the whole routing algorithm in this pass. First stabilize the inputs and traces that future routing learning will consume.

### 4. Experiment Observability Schema

Purpose: one row schema for checker and summary.

Core groups:

- value fields;
- learning fields;
- routing decision fields;
- cost fields;
- harness fields;
- patch-quality fields.

Checker and summary must consume this shared schema rather than infer separate meanings.

## Phases

1. Finish `learning_context.py` and its tests.
2. Extract `value_efficiency.py` with compatibility wrappers in `run_mini_swe_compare.py`.
3. Add routing objective / learned-prior observability fields without changing the algorithm.
4. Run no-paid gates:
   - focused unit tests;
   - `--auto-budget-dry-run`;
   - checker on latest JSONL.
5. Update `north_star.md`, `CONTEXT.md`, and `progress.md` only where the semantics changed.
6. Commit and push once the focused refactor is stable.

## Stop Conditions

Stop and report instead of pushing forward if:

- provider auth/billing/rate-limit appears;
- Docker official harness becomes required for a claim;
- a test failure points to a broader evaluator bug;
- the implementation would require changing the T1/T2 value proposition;
- paid spend would be needed before no-paid gates are clean.

## Execution Notes

Status: implemented and no-paid verified.

- Added `learning_context.py` so `auto_budget_memory.jsonl` is cap/value-cost memory only, while routing `PolicyMemory` loads from recent run JSONL with routing evidence.
- Added `value_efficiency.py` so T1/T2 value semantics are centralized outside the runner.
- Added `experiment_observability.py` so persisted rows expose routing objective, policy family, memory source, learned action, imitation fields, and schema version.
- Fixed a schema bug caught during review: `budgetflow_value_aware` under `value_profile=equal` is now labeled `bfv_equal_value_ablation`, not `bfv_t1_value_aware`.
- Updated the compact checker to consume standardized `routing_policy_memory_source` / `routing_learned_action` first, while keeping legacy `routing_prior_summary` fallback for old artifacts.
- No paid experiment was run in this phase.

Verification:

- `183 passed, 8 skipped` focused tests.
- `py_compile` passed for the touched runtime modules.
- `git diff --check` passed.
- `--auto-budget-dry-run` loaded cap memory from `data/runs/auto_budget_memory.jsonl` and routing memory from `data/runs/066_postfix_3x3.jsonl`, with no provider preflight.
- Checker on `066_postfix_3x3.jsonl` remains forensic-only: it is pre-refactor, `policy_memory_used=False`, and invoice trace is incomplete.

Residual risk:

- `run_mini_swe_compare.py` still has `_VALUE_*` compatibility globals because older tests and debug paths mutate them directly. Core value logic is now delegated, but a later cleanup should remove the compatibility layer once callers migrate.

# Calibration Runtime Boundary Refactor - 2026-06-17

## Objective

Clean up the BudgetFlow calibration/runtime boundary before the next paid
experiment. The target was program generality rather than tuning a specific
6x5 or 6x10 slice:

- The Budget Regime Compiler compiles a shared hard budget for a fixed task set
  and fixed task order.
- The compiler may publish workload-level Model Fit evidence, but it must not
  assign model tiers to individual tasks.
- BudgetFlow Runtime consumes Model Fit only as an abstract per-tier allocation
  signal and must not derive it from repo/task-id policy memory.
- Budget-exhausted rows remain censored runway evidence: not complete cost
  samples, not discarded.
- Active compare setup preserves the registered task order.

No paid experiments were run.

## Files Changed

- `paper1/src/budgetflow/model_fit_estimator.py`
- `paper1/src/budgetflow/allocation.py`
- `paper1/src/budgetflow/adapter/strategies.py`
- `paper1/src/budgetflow/experiments/budget_binding.py`
- `paper1/src/budgetflow/experiments/compare_config.py`
- `paper1/src/budgetflow/experiments/compare_setup.py`
- `paper1/src/budgetflow/experiments/compare_execution.py`
- `paper1/src/budgetflow/run_mini_swe_compare.py`
- Focused contract tests under `paper1/tests/`

`paper1/docs/related_work_comparison.html` was already dirty and was not part
of this slice.

## Interface Decisions

- Model Fit is canonical per-tier data in `AllocationContext.model_fit`, for
  example `{"tier2": 0.08, "tier3": 0.65}`. Higher means more expected
  progress per unit runway; it is not model cost.
- The old `strongest_vs_reference` Model Fit compatibility input was removed.
  Runtime allocation now computes deltas from canonical tier keys only.
- `run_mini_swe_compare.py` reads `model_fit_evidence.tier_fit` from the
  budget plan and passes it into every task record as workload-level calibrated
  Model Fit.
- `compare_execution.run_task_record()` no longer converts
  `PolicyMemory.repo_prior(instance_id)` into Model Fit. Policy memory can
  still supply routing-memory audit fields, but not runtime Model Fit.
- `budget_binding._cold_start_cost_estimate()` is now strategy-independent. It
  uses a workload reference tier cost scale and optional global fit overrides;
  it does not choose T2/T3 per strategy.
- Pure-tier diagnostic controls are the exception: their compiler projection
  uses the tier declared by the control itself. This protects Strongest Model
  boundary audits without assigning tiers to BudgetFlow tasks.
- Current-schema calibration requires `harness_trust="trusted"`, including
  budget-exhausted censored rows. Missing or untrusted rows are forensic-only.
- Compare task loading returns the registered task order. The retired
  medium-set easy-first reorder helper was deleted.

## Deleted Stale Paths And Tests

- Deleted `model_fit_override` from `build_routing_context()`.
- Deleted `_cold_start_backend()` and strategy-name based cold-start tier
  selection.
- Deleted `task_difficulty_key()` / `order_tasks_easy_first()` from active
  compare configuration.
- Removed active-test references that treated `policy_memory` as a valid
  Model Fit provenance.
- Reworked tests that expected BudgetFlow task-level projections to inherit a
  bare T2 censored floor. That old assertion would have turned the compiler
  into a hidden tier router.
- Added regression coverage for untrusted budget-exhausted rows being excluded
  from both censored spend floors and Model Fit censored tiers.

## Verification

Commands run from `/root/.dev/AgentOS`:

- `PYTHONPATH=paper1/src:external/mini-swe-agent/src pytest -q paper1/tests`
  - Result: `608 passed in 4.00s`
- `python3 -m compileall -q paper1/src/budgetflow`
  - Result: pass
- `git diff --check`
  - Result: pass
- Stale-path scan:
  - `rg -n "model_fit_override|_cold_start_backend|order_tasks_easy_first|task_difficulty_key|\"strongest_vs_reference\"|model_fit_source=\"policy_memory\"|task-specific model_fit|per-task priors|NO per-task model_fit|penalis" paper1/src paper1/tests`
  - Result: no matches

## Residual Risks

- The current Model Fit estimator is still deliberately simple. It is suitable
  as frozen diagnostic calibration input, not as paper-level proof by itself.
- Censored-only evidence uses the observed upper bound without an extra magic
  multiplier. That is auditable, but future larger calibration sets should
  check projection error before paid evidence runs.
- Historical rows without explicit trusted harness evidence are excluded from
  active calibration. This is intentionally strict and may reduce available
  calibration sample size until current-schema records accumulate.
- Continual Cost Memory, Routing Memory, and Escalation Memory remain optional
  Claim 2 variants. This slice does not enable active continual learning.
- No provider/model-access preflight or paid run was performed.

## Next Recommended Slice

Before the next paid run, generate a fresh budget plan from the current
compiler and inspect the artifact for:

- hard cap and target utilization pressure;
- `model_fit_evidence` source, confidence, and censored tiers;
- projected spend by strategy and task;
- absence of per-task model-tier assignments;
- fixed task list and fixed task order matching the intended evidence run.

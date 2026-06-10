# Task-ID Hardcoding Fix Report — 2026-06-10

## What was fixed

`src/budgetflow/experiments/budget_binding.py`: `_estimate_t3_cost_share()` had
two SymPy task IDs hardwired as "the only tier3 tasks in the frozen plan":

```python
# BEFORE (line 292):
if task_id in ("sympy__sympy-16988", "sympy__sympy-20639"):
    return 1.0
```

Replaced with a data-driven lookup from the frozen router plan's
`preferred_model` field, loaded by a new helper `_load_frozen_preferred_models()`.

```python
# AFTER:
if strategy in ("enterprise_router_baseline", "budgetflow_same_router"):
    if preferred_models:
        model = preferred_models.get(task_id, "")
        if model == "tier3":
            return 1.0
    return 0.0
```

No other changes to `budget_binding.py`.

## Why this matters for paid-run readiness

The hardcoded task IDs were an **infrastructure orthogonality violation**:

1. **Repo leak**: budget_binding.py had knowledge of specific SymPy task IDs.
   If the frozen plan changes (different tasks, different repos, different
   tier assignments), the calibrator would silently give wrong T3 cost shares
   for the new tasks.

2. **Frozen plan is the single source of truth**: the plan already declares
   `preferred_model` per task. The calibrator should read it, not duplicate it.

3. **Paid-run correctness**: T3 cost re-normalization depends on accurate
   per-task T3 share estimates. Wrong T3 share → wrong projected spend →
   wrong utilization → wrong budget decision.

## Test results

| Test suite | Result |
|---|---|
| `tests/test_budget_binding.py` (new) | 8/8 passed |
| `tests/test_compare_readiness.py` | 18/18 passed |
| `tests/test_local_harness_pytest_nodes.py` | 31/31 passed |
| Full test suite | 456 passed, 1 skipped, 0 failed |

### Key test: `test_t3_share_reads_preferred_model_not_task_id`

Constructs a frozen plan with arbitrary non-SymPy task id `some_arbitrary__repo-999`
and `preferred_model=tier3`. Verifies `_estimate_t3_cost_share` returns 1.0.
Proves the function has zero dependency on task-id naming.

### Key test: `test_no_sympy_task_id_hardcoding`

Uses `inspect.getsource()` to verify the source of `_estimate_t3_cost_share`
contains no reference to `16988`, `20639`, or `sympy__`.

## Budget plan re-verification

| Field | Value | Status |
|---|---|---|
| hard_cap_usd | 3.58 | unchanged |
| decision | PASS_WITH_DIAGNOSTIC_OVERRIDE | unchanged |
| frozen plan cap sum | 3.58 | unchanged |
| override_reason | intact | unchanged |

## Verdict: GO for 5x16

The task-id hardcoding is removed. T3 cost estimation is now purely data-driven
from the frozen plan. No regression in budget plan output. All gates pass.

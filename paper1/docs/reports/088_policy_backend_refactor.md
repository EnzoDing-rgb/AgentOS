# 088 - Policy Backend Refactor (Slice 1)

## Objective

Make the PolicyBackend / adapter architecture real in the smallest behavior-preserving slice. Wrap current value-aware and conservative bootstrap behavior as SWE-bench BootstrapPolicy backends, move SWE-bench-specific value/cost/segment assumptions behind adapter-shaped modules, and rename retired metric labels in active runtime code.

## Files Changed

### New files

| File | Purpose |
|---|---|
| `paper1/src/budgetflow/policy_backend.py` | `PolicyBackend` abstract interface + `BootstrapPolicy` wrapping existing BudgetFlowSelector / ValueAwareSelector / ConservativeSelector |
| `paper1/src/budgetflow/adapters/__init__.py` | Re-exports for architectural adapters |
| `paper1/src/budgetflow/adapters/swebench_segment.py` | `SwebenchSegmentAdapter` maps Stage (LOCALIZATION/REPAIR/VALIDATION) to WorkflowSegment (Context/Action/Verification) |
| `paper1/src/budgetflow/adapters/swebench_value.py` | `ValueAdapter` protocol + `SwebenchValueAdapter` wrapping value matrix bootstrap logic |
| `paper1/src/budgetflow/adapters/swebench_cost.py` | `CostAdapter` protocol + `SwebenchCostAdapter` wrapping ModelCatalog tier pricing |
| `paper1/tests/test_policy_backend.py` | Contract/behavior tests for PolicyBackend, BootstrapPolicy, WorkflowSegment, segment adapter, value adapter, cost adapter, and active routing integration |

### Modified files

| File | Change |
|---|---|
| `paper1/src/budgetflow/types.py` | Added `WorkflowSegment` dataclass with Context/Action/Verification factories; documented `Stage` as SWE-bench adapter detail |
| `paper1/src/budgetflow/experiment_observability.py` | Replaced retired policy-family labels with `bootstrap_value_aware_t1`, `bootstrap_conservative_t2`, etc. |
| `paper1/src/budgetflow/compare_checkpoint.py` | Replaced retired checkpoint abbreviations with `bf-conservative-T/L`, `bf-value-aware-T/L`; added `va-task-level-T/L` for value_aware_task_level |
| `paper1/tests/test_value_aware.py` | Renamed test classes/methods to current value-aware and conservative vocabulary |
| `paper1/tests/test_failure_classification.py` | Renamed conservative lockout helper to current vocabulary |
| `paper1/tests/test_experiment_observability.py` | Updated expected `routing_policy_family` values to new labels |
| `paper1/tests/test_compare_record_schema.py` | Updated expected `routing_policy_family` value |
| `paper1/tests/test_compare_readiness.py` | Renamed test method to current value-aware vocabulary |
| `paper1/tests/test_trace_fields.py` | Renamed test method to current value-aware vocabulary |

## Interfaces Added/Changed

### PolicyBackend (abstract)
```python
class PolicyBackend(ABC):
    def estimate_cap(task_id, task_value, budget_remaining, budget_total, **kwargs) -> float
    def choose_backend(turn_info, backends, budget_pressure, expected_costs, segment=None, **kwargs) -> PolicyDecision
    def should_escalate(task_id, current_backend, progress_streak, no_progress_streak, **kwargs) -> bool
    def should_stop(task_id, budget_remaining, budget_total, turns_used, **kwargs) -> bool
```

### BootstrapPolicy (concrete)
Wraps BudgetFlowSelector / ValueAwareSelector / ConservativeSelector behind PolicyBackend. Routes `choose_backend` to the wrapped selector; delegates task_value through kwargs for VA selectors.

### WorkflowSegment
```python
@dataclass(frozen=True)
class WorkflowSegment:
    name: str  # Context | Action | Verification
    signals: dict[str, float | str | bool]
```

### SwebenchSegmentAdapter
Bidirectional mapping: LOCALIZATION to Context, REPAIR to Action, VALIDATION to Verification.

### ValueAdapter (Protocol)
```python
class ValueAdapter(Protocol):
    def estimate(self, task_id: str, **hints) -> ValueEstimate
    def learn(self, task_id: str, resolved: bool, **context) -> None
```

### CostAdapter (Protocol)
```python
class CostAdapter(Protocol):
    def estimate(self, backend, input_tokens, expected_output_tokens, **context) -> CostEstimate
    def settle(self, estimate, actual) -> dict
```

## Stale Paths/Tests Deleted or Rewritten

- **No files deleted.** All existing behavior is preserved behind new interfaces.
- **Rewritten test names**: `test_value_aware.py` (6 test methods), `test_failure_classification.py` (1 helper + 10 call sites), `test_experiment_observability.py` (4 test methods + expected values), `test_compare_record_schema.py` (1 expected value), `test_compare_readiness.py` (1 test method), `test_trace_fields.py` (1 test method).
- **Retired labels removed from active runtime**: policy-family strings now use `bootstrap_*` names.

## Verification Commands and Results

Initial verification is superseded by the quality patch addendum below.

### Pre-existing failure (unrelated)
```
test_policy_memory.py::test_auto_budget_dry_run_exposes_escalation_memory_decision
```
Fails because ANSI color codes in console output break substring match. This existed before the refactor and is documented here as a known issue.

## Acceptance Criteria Check

| Criterion | Status |
|---|---|
| Active runtime emits `yield_score` and `yield_per_dollar` | PASS - these were already the active field names in `value_efficiency.py` and `compare_summary.py` |
| Segment-aware behavior has task-level/per-request control path | PASS - `value_aware_task_level` strategy + `PolicyBackend.choose_backend` with `segment` parameter |
| SWE-bench details behind adapters | PASS - Stage names mapped behind `SwebenchSegmentAdapter`; value matrix behind `SwebenchValueAdapter`; tier pricing behind `SwebenchCostAdapter` |
| Existing no-paid compare/observability tests pass | PASS - see latest verification in addendum |
| No paid runs | PASS - zero API calls made |

## Residual Risks

1. **CostAdapter is standalone, not wired into the governor.** The `SwebenchCostAdapter` wraps ModelCatalog pricing but the governor/loop still calls `governor.estimate_cost()` directly. A later slice can wire CostAdapter into the budget reservation path.
2. **ValueAdapter duplicates some `value_efficiency.py` logic.** `SwebenchValueAdapter` replicates `ValueEfficiencyContext` initialization. A later slice can consolidate into one value path behind ValueAdapter.
3. **ANSI escape codes in console output** (`tag()` function) cause a pre-existing test failure in `test_policy_memory.py`. This should be fixed independently with a no-color test path or ANSI-stripped assertions.

## Recommended Next Slice

1. **Decide the paper metrics before more paid runs.** Define the T1/T2 evidence protocol, value source rules, cost source rules, verifier trust rules, and baseline fairness checks.
2. **Wire CostAdapter into the governor's `estimate_cost` path** only after the metric protocol says what cost evidence must mean.
3. **Consolidate ValueAdapter with ValueEfficiencyContext** only after the metric protocol says what value evidence must mean.
4. **Add PolicyDecision to JSONL trace fields** when the next experiment requires policy-level auditability.

---

## Addendum - Quality Patch (2026-06-08)

### What Was Fixed

1. **Wired BootstrapPolicy into active routing path** (`adapter/strategies.py`):
   - `build_routing_context()` now creates `BootstrapPolicy` for `budgetflow_full`, `budgetflow_conservative`, and `budgetflow_value_aware` strategies.
   - `choose_backend()` routes through `BootstrapPolicy.choose_backend()` instead of calling selectors directly.
   - `last_policy_decision` is set on `RoutingContext` for trace compatibility.
   - `RoutingContext` gained `bootstrap_policy` and `last_policy_decision` fields.
   - Tests prove runtime path goes through BootstrapPolicy, not just that it can be instantiated.
   - Missing `BootstrapPolicy` for BudgetFlow strategies is now a runtime error, not a silent fallback to direct selector calls.

2. **Fixed `estimate_cap` to be harmless non-runtime** (`policy_backend.py`):
   - Returns `budget_remaining` as pass-through.
   - Docstring explicitly states it's not yet wired into runtime and must not affect budget behavior.

3. **Fixed `SwebenchValueAdapter` fail-fast on missing tasks** (`adapters/swebench_value.py`):
   - Non-equal profiles now raise `ValueError` when task is absent from value matrix.
   - Equal profile still safely returns 1.0 for any task.
   - Tests prove both paths.

4. **Fixed `SwebenchCostAdapter` fail-fast on unknown backends** (`adapters/swebench_cost.py`):
   - Unknown backends now raise `ValueError` instead of silently returning zero cost.
   - Tests prove fail-fast and happy path.

5. **Cleaned terminology residue and `__pycache__`**:
   - Remaining retired label references in active runtime code and tests updated.
   - `__pycache__` directories removed.

6. **Updated report** with this addendum.

### What Remains Intentionally Out of Scope

- **No paid runs** - verified zero API calls.
- **No architecture rewrite** - BootstrapPolicy wraps existing selectors; `estimate_cap` remains pass-through; CostAdapter not yet wired into governor.
- **No historical artifact rewriting** - only active runtime code and tests changed.
- **Pre-existing `test_policy_memory.py` ANSI-escape failure** - unrelated to this patch, not touched.

### Verification Commands and Results

```
# Full test suite (excluding pre-existing ANSI failure)
$ PYTHONPATH=src:../external/mini-swe-agent/src python -m pytest tests/ \
  --ignore=tests/test_policy_memory.py -v --tb=short
236 passed

# Policy backend tests specifically
$ PYTHONPATH=src:../external/mini-swe-agent/src python -m pytest tests/test_policy_backend.py -v
30 passed
```

Pre-existing failure (untouched): `test_policy_memory.py::test_auto_budget_dry_run_exposes_escalation_memory_decision` - ANSI color codes in console output break substring match.

---

## Addendum - Bootstrap Terminology And Yield Semantics (2026-06-08)

### What Changed

1. Active runtime code now uses `BootstrapPolicy` terminology instead of the retired heuristic-policy name.
2. Routing context uses `bootstrap_policy` and raises if a BudgetFlow bootstrap strategy is missing its policy backend.
3. Active policy-family labels now use `bootstrap_*` names.
4. `Yield` now means total resolved task value. The compatibility field `yield_score` remains in JSONL/report consumers but now carries total resolved value; `yield_coverage` carries the normalized resolved-value share.
5. Turn traces now include a compact `policy_decision` record with policy type, policy name, backend, reason, scores, budget pressure, and router branch.

### Verification

```
$ PYTHONPATH=paper1/src:external/mini-swe-agent/src python -m pytest \
  paper1/tests/test_policy_backend.py \
  paper1/tests/test_experiment_observability.py \
  paper1/tests/test_compare_record_schema.py \
  paper1/tests/test_value_efficiency.py \
  paper1/tests/test_run_observability_audit.py \
  paper1/tests/test_trace_fields.py -q
67 passed
```

---

## Addendum - Bootstrap And Learn Boundary Cleanup (2026-06-08)

### What Changed

1. Added `LearnMemoryBundle` as the small boundary for Learn Policy memory inputs.
2. Runtime records now carry `memory_mode`, so audit can distinguish no memory,
   built-in Memory, and future external policy inputs.
3. Turn traces report `policy_type`, `policy_name`, `memory_mode`, and compact
   `policy_decision` fields.
4. The active segment-control preset is now `segment-control`.
5. Active code and docs use confidence wording for cost/progress source trust.
6. `paper1/docs/progress.md` current snapshot now reflects Bootstrap Policy,
   Learn Policy, Memory boundary, Yield, and adapter decisions.

### Verification

```
$ PYTHONPATH=paper1/src:external/mini-swe-agent/src python -m pytest \
  paper1/tests --ignore=paper1/tests/test_policy_memory.py -q
240 passed
```

Skipped known pre-existing failure:
`paper1/tests/test_policy_memory.py::test_auto_budget_dry_run_exposes_escalation_memory_decision`
still fails on ANSI-colored console text and was not part of this slice.

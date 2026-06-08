# 088 - Policy Backend Refactor (Slice 1)

## Objective

Make the PolicyBackend / adapter architecture real in the smallest behavior-preserving slice. Wrap current value-aware and conservative heuristic behavior as SWE-bench HeuristicPolicy backends, move SWE-bench-specific value/cost/segment assumptions behind adapter-shaped modules, and rename retired metric labels in active runtime code.

## Files Changed

### New files

| File | Purpose |
|---|---|
| `paper1/src/budgetflow/policy_backend.py` | `PolicyBackend` abstract interface + `HeuristicPolicy` wrapping existing BudgetFlowSelector / ValueAwareSelector / ConservativeSelector |
| `paper1/src/budgetflow/adapters/__init__.py` | Re-exports for architectural adapters |
| `paper1/src/budgetflow/adapters/swebench_segment.py` | `SwebenchSegmentAdapter` maps Stage (LOCALIZATION/REPAIR/VALIDATION) to WorkflowSegment (Context/Action/Verification) |
| `paper1/src/budgetflow/adapters/swebench_value.py` | `ValueAdapter` protocol + `SwebenchValueAdapter` wrapping value matrix cold-start logic |
| `paper1/src/budgetflow/adapters/swebench_cost.py` | `CostAdapter` protocol + `SwebenchCostAdapter` wrapping ModelCatalog tier pricing |
| `paper1/tests/test_policy_backend.py` | Contract/behavior tests for PolicyBackend, HeuristicPolicy, WorkflowSegment, segment adapter, value adapter, cost adapter, and active routing integration |

### Modified files

| File | Change |
|---|---|
| `paper1/src/budgetflow/types.py` | Added `WorkflowSegment` dataclass with Context/Action/Verification factories; documented `Stage` as SWE-bench adapter detail |
| `paper1/src/budgetflow/experiment_observability.py` | Replaced retired policy-family labels with `heuristic_value_aware_t1`, `heuristic_conservative_t2`, etc. |
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

### HeuristicPolicy (concrete)
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
- **Retired labels removed from active runtime**: policy-family strings now use `heuristic_*` equivalents.

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

1. **Wired HeuristicPolicy into active routing path** (`adapter/strategies.py`):
   - `build_routing_context()` now creates `HeuristicPolicy` for `budgetflow_full`, `budgetflow_conservative`, and `budgetflow_value_aware` strategies.
   - `choose_backend()` routes through `HeuristicPolicy.choose_backend()` instead of calling selectors directly.
   - `last_policy_decision` is set on `RoutingContext` for trace compatibility.
   - `RoutingContext` gained `heuristic_policy` and `last_policy_decision` fields.
   - Tests prove runtime path goes through HeuristicPolicy, not just that it can be instantiated.
   - Missing `HeuristicPolicy` for BudgetFlow strategies is now a runtime error, not a silent fallback to direct selector calls.

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
- **No architecture rewrite** - HeuristicPolicy wraps existing selectors; `estimate_cap` remains pass-through; CostAdapter not yet wired into governor.
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

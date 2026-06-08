# BudgetFlow Worker Handoff

This document is for DeepSeek V4 or another fresh worker taking over the next
implementation slice. It is not a prompt. Treat `paper1/docs/north_star.md` as
the terminology and architecture source of truth.

## Current System Definition

BudgetFlow is value-aware budget governance for multi-step agent workflows under
shared hard budgets. The primary goal is to maximize **Yield**: verified
resolved task value divided by total task value at a fixed budget.

The system has three layers:

| Layer | Owns |
|---|---|
| BudgetFlow core | hard budget ledger, reservation, settlement, verified outcome, memory contracts, trace/audit/replay, stop-loss primitives, same-budget policy comparison |
| Policy Backend | cap, model-tier choice, escalation, de-escalation, stop, and continue recommendations |
| Domain Adapters | task, segment, verifier, value, cost, model-tier, progress-signal, and runtime mappings for SWE-bench or an enterprise workflow |

SWE-bench is an adapter and testbed. SWE-bench concepts such as localization,
repair, validation, fail-to-pass tests, patch extraction, and worktree diffs
must not define BudgetFlow core.

## Required Vocabulary

Use these terms exactly:

- `Yield`: verified resolved value divided by total task value at a fixed budget.
- `Yield per Dollar`: verified resolved value divided by model spend.
- `PolicyBackend`: pluggable strategy interface.
- `HeuristicPolicy`: default explainable cold-start and safety policy.
- `Memory-Tuned HeuristicPolicy`: heuristic policy tuned from verified outcomes.
- `Adaptive Learning Policy`: learned backend satisfying the same policy interface.
- `Workflow Segment`: coarse policy signal; defaults are `Context`, `Action`, `Verification`.
- `Segment-Aware Routing`: routing that can use segment as a feature.
- `Task-Level Policy`: policy/control that chooses at task or request level and preserves cache/context continuity.
- `ValueSource` / `CostSource`: versioned value/cost inputs.
- `ValueAdapter` / `CostAdapter`: adapters that normalize value/cost signals.
- `Confidence`: compact record of where a value/cost estimate came from and how trustworthy it is.

Use the vocabulary above in active code and docs. Remove retired names, unclear
research jargon, old metric abbreviations, and workflow-stage wording that
treats a SWE-bench schema as BudgetFlow core.

## Interface Shape

The implementation does not need to match this pseudocode exactly, but it
should preserve the boundaries.

```python
@dataclass
class TaskContext:
    task_id: str
    task_type: str
    description: str
    features: dict[str, float | str | bool]
    verifier: Verifier
    runtime: AgentRuntime

@dataclass
class WorkflowSegment:
    name: str  # Context, Action, Verification, or adapter-defined equivalent
    signals: dict[str, float | str | bool]

@dataclass
class ValueEstimate:
    value: float
    source: str
    confidence: dict[str, float | str | bool]

@dataclass
class CostEstimate:
    usd: float
    source: str
    confidence: dict[str, float | str | bool]

class ValueAdapter:
    def estimate(self, task: TaskContext, history: HistoryContext) -> ValueEstimate: ...
    def learn(self, task: TaskContext, outcome: VerifiedOutcome) -> None: ...

class CostAdapter:
    def estimate(self, backend: str, state: WorkflowState, budget: BudgetContext) -> CostEstimate: ...
    def settle(self, estimate: CostEstimate, actual: CostActual | None) -> CostRecord: ...

class PolicyBackend:
    def estimate_cap(
        self,
        task: TaskContext,
        value: ValueEstimate,
        budget: BudgetContext,
        history: HistoryContext,
    ) -> float: ...

    def choose_backend(
        self,
        task: TaskContext,
        segment: WorkflowSegment,
        state: WorkflowState,
        budget: BudgetContext,
    ) -> str: ...

    def should_escalate(self, task: TaskContext, state: WorkflowState, history: HistoryContext) -> bool: ...
    def should_stop(self, task: TaskContext, state: WorkflowState, budget: BudgetContext) -> bool: ...
    def learn(self, task: TaskContext, outcome: VerifiedOutcome) -> None: ...
```

`WorkflowSegment` is a policy signal, not a forced model-switch boundary. A
segment-aware policy may keep one model for the whole task to preserve KV cache,
prefix reuse, context continuity, and lower coordination cost.

## Implementation Assignment

Build the smallest clean architecture slice that makes the above boundaries
real:

1. Introduce a `PolicyBackend` interface and wrap current BFV/BFC behavior as
   SWE-bench `HeuristicPolicy` implementations.
2. Move SWE-bench-specific stage and harness assumptions behind adapter-shaped
   modules. Use `Workflow Segment` naming for active interfaces.
3. Introduce `ValueAdapter` and `CostAdapter` contracts or contract-shaped
   modules. The existing SWE-bench value matrix and public model price catalog
   should become concrete adapters, not core assumptions.
4. Rename active metric fields and display labels to `yield_score` and
   `yield_per_dollar`. Active code should not emit old metric abbreviations or
   their old long-form field names.
5. Keep `run_mini_swe_compare.py` and `check_run_observability.py` thin. Move
   policy, value, cost, and adapter semantics out of entrypoints where practical.
6. Delete or rewrite tests that only preserve old names, old aliases, or retired
   paths. Keep tests that protect current evidence quality, budget accounting,
   adapter boundaries, Yield calculation, and policy comparison.

## Evidence Rules

- Same policy comparison means same task set, verifier, hard budget,
  ValueSource, CostSource, model-tier catalog, and run shape.
- A run's ValueSource and CostSource must be frozen before that run starts.
  Learning from the run can update the next run.
- Historical JSONL and historical reports are evidence records. Do not patch
  them to change past facts; update active code, active docs, and new reports.
- Stop on provider billing, authentication, model-access, preflight, missing
  cost confidence, or missing value confidence blockers.
- Report segment-aware policy against a task-level or per-request control when
  evaluating the segment mechanism.

## Non-Goals

- Do not build a full learned policy in this slice.
- Do not make the strongest model tier the center of the architecture.
- Do not add a new decision-record system.
- Do not preserve old terms for compatibility if they only keep obsolete tests
  or retired code paths alive.

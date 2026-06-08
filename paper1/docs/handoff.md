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

@dataclass
class PolicyDecision:
    backend: str
    cap_usd: float | None
    should_stop: bool
    should_escalate: bool
    reason: str
    scores: dict[str, float]
    confidence: dict[str, float | str | bool]

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

## Boundary Contracts

Keep these contracts explicit in code:

- `PolicyBackend` receives normalized task, value, cost, budget, segment,
  history, and runtime state. It returns recommendations and reasons. It should
  not read SWE-bench files, parse pytest output, inspect worktrees directly, or
  load provider price files by itself.
- `TaskAdapter` turns a benchmark or enterprise item into `TaskContext` and
  task features. SWE-bench instance IDs, fail-to-pass tests, patch metadata, and
  repo names belong here.
- `SegmentAdapter` maps runtime signals into `Context`, `Action`, or
  `Verification`. SWE-bench localization/repair/validation names may exist
  inside this adapter but should not be the core interface.
- `VerifierAdapter` owns verifier execution and converts raw harness output into
  `VerifiedOutcome`. Policy code should consume verifier-grounded outcome, not
  raw harness logs.
- `ValueAdapter` owns task-value estimation and calibration. It may use a value
  matrix, natural-language rules translated into config, enterprise imports, or
  learned estimates. The core consumes `ValueEstimate`.
- `CostAdapter` owns public price catalogs, provider estimates, invoices,
  enterprise rate cards, and settlement. The core consumes `CostEstimate` and
  `CostRecord`.
- Memory stores should stay separate: Cost Memory for cap/cost/value-cost
  evidence, Routing Memory for route outcomes, and Escalation Memory for
  expensive-tier escalation outcomes.

The core may orchestrate these contracts, but it should not know the details of
SWE-bench, provider pricing files, task-value matrix schemas, or pytest output.

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

Suggested order:

1. Add the interfaces/types in a small module before moving behavior.
2. Wrap the current behavior behind those interfaces with minimal logic change.
3. Move one concern at a time behind adapters: value, cost, segment, verifier.
4. Update entrypoints to call the interfaces instead of owning the semantics.
5. Delete stale tests and add focused contract tests for each interface.

Do not perform a broad rewrite first. The first passing slice should behave like
the current runtime while making the boundaries visible.

## Acceptance Criteria

- Current compare and observability paths still run through no-paid tests.
- Active JSONL rows and summaries use `yield_score` and `yield_per_dollar`.
- `budgetflow_value_aware_tight`, `budgetflow_conservative_tight`, and
  task-level controls are represented as policy backends or thin wrappers over
  policy backends.
- SWE-bench-specific names are behind adapters or compatibility edges, not in
  core policy interfaces.
- A task-level or per-request control remains available for segment-aware
  evaluations.
- New tests exercise the interfaces through behavior, not string snapshots of
  old implementation details.
- `paper1/docs/north_star.md` stays the terminology source of truth.

## Decision Rules

Use these rules when the implementation has multiple reasonable paths:

- Prefer preserving current runtime behavior while moving boundaries.
- Prefer active runtime and active tests over historical reports and artifacts.
- Prefer deleting stale compatibility tests over keeping old names alive.
- Prefer making entrypoints thinner and adapters clearer.
- Prefer behavior-based tests over string snapshots and alias-preservation tests.
- If a change alters paid-run semantics, stop and document the risk before
  continuing.
- If two designs both work, choose the one that makes BudgetFlow core less aware
  of SWE-bench, provider pricing files, value-matrix schemas, and pytest output.
- If a learned policy would complicate the slice, keep the interface ready for
  it and leave the implementation as HeuristicPolicy.

## Eight Gold Standards

Keep these checks visible while working:

- T1 first: report Yield and Yield per Dollar before mechanism storytelling.
- T2 frontier: compare verified resolution and cost under the same budget.
- Model-tier diagnosis: report productive use, no-progress spend, and why
  expensive tiers were selected.
- No-patch rate: distinguish no-patch exits, failed patches, verifier failures,
  and infra failures.
- Segment control: compare Segment-Aware Routing against a task-level or
  per-request control.
- Checker first: inspect JSONL, trace, checker, compact audit, and harness trust
  before drawing conclusions.
- No-paid gates first: pass no-paid tests, dry-runs, value/cost confidence, and
  provider preflight before paid runs.
- Historical evidence is immutable: do not patch historical JSONL or old reports
  to make a current story cleaner.

## Worker Report

At the end of the implementation slice, write a new report:

```text
paper1/docs/reports/088_policy_backend_refactor.md
```

The report should be concise and include:

- objective and scope;
- files changed;
- interfaces added or changed;
- stale paths/tests deleted or rewritten;
- verification commands and results;
- residual risks;
- recommended next slice.

Do not edit old reports for terminology cleanup. This report records the new
work only.

## Evidence Rules

- Same policy comparison means same task set, verifier, hard budget,
  ValueSource, CostSource, model-tier catalog, and run shape.
- A run's ValueSource and CostSource must be frozen before that run starts.
  Learning from the run can update the next run.
- Historical JSONL and historical reports are evidence records. Do not patch
  them to change past facts; update active code, active docs, and new reports.
- Do not spend implementation time batch-editing `paper1/docs/reports/`,
  historical JSONL, or old experiment artifacts for terminology cleanup. Touch
  historical material only when active code/tests import it or a current doc
  directly depends on it.
- Stop on provider billing, authentication, model-access, preflight, missing
  cost confidence, or missing value confidence blockers.
- Report segment-aware policy against a task-level or per-request control when
  evaluating the segment mechanism.

## Non-Goals

- Do not build a full learned policy in this slice.
- Do not make the strongest model tier the center of the architecture.
- Do not add a new decision-record system.
- Do not burn tokens rewriting historical reports.
- Do not preserve old terms for compatibility if they only keep obsolete tests
  or retired code paths alive.

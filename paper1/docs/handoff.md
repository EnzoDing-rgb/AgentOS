# BudgetFlow Adapter Refactor Handoff

This document is for a fresh worker taking the next implementation slice. It is
not a prompt. Do not redesign the architecture; implement the design below.

`paper1/docs/north_star.md` is the terminology source of truth. `AGENTS.md`
contains run and evidence discipline.

## Objective

Make BudgetFlow's active code match the adapter boundary we have now chosen:
BudgetFlow Mechanism and PolicyBackend consume a small set of standard signals.
SWE-bench is one integration that maps its task/harness/runtime details into
those signals.

The core theme is **decoupling**:

- BudgetFlow Mechanism must not know SWE-bench stages, mini-SWE-agent, pytest
  output, worktree details, value-matrix schemas, or old JSONL schemas.
- Policy and Memory must use BudgetFlow terms: task, value/difficulty hints,
  workflow segment, progress/outcome, cost, budget, and verified result.
- Historical artifacts are forensic evidence. Active runtime and active tests do
  not keep old schema compatibility.
- Adapter design should not shift most implementation burden to the customer.
  Task is the only mandatory input. Workflow, progress, and cost can start from
  conservative defaults or unknown signals if those defaults are auditable.
- Bootstrap Policy is the cold-start behavior. As clean current-schema records
  accumulate, Learn Policy Inputs should naturally improve decisions behind the
  same Policy Backend interface. Do not require a user-facing manual mode switch.
- Observability must follow the same abstractions: task/value source, workflow
  segment, progress/outcome confidence, cost source, policy decision, final
  acceptance, and failure attribution.

## Final Adapter Set

Use four adapter families. Do not add more unless a concrete current runtime
need proves it.

| Adapter | Responsibility |
|---|---|
| `TaskAdapter` | Convert an external task into BudgetFlow task inputs, including description, metadata, difficulty hints, value hints, manual pre-registered value, bootstrap value, and learned-value input hooks. This absorbs the old separate `ValueAdapter` boundary. |
| `WorkflowAdapter` | Convert concrete work phases into `WorkflowSegment` values: `Context`, `Action`, `Verification`. SWE-bench localization/repair/validation belongs here only. |
| `ProgressAdapter` | Convert process and acceptance evidence into standard progress/outcome signals: progress/no-progress, patch/no-patch, verifier pass/fail, human acceptance, failure reason. This absorbs the old separate verifier/outcome adapter boundary. |
| `CostAdapter` | Convert public model prices, provider estimates, invoices, enterprise rate cards, and manual overrides into standard cost estimates/records. |

There is no `RuntimeAdapter` in the BudgetFlow architecture. The agent harness
is execution integration, not BudgetFlow Mechanism. For SWE-bench, the
mini-SWE-agent bridge should live in the SWE-bench runner/integration layer and
emit standard BudgetFlow records. Enterprises can use their own agent harness as
long as it emits the required standard signals.

## Current Refactor State

The main agent has an active worktree with cleanup already started:

- `ValueSourceInfo` now distinguishes `equal_sanity`,
  `bootstrap_heuristic`, `pre_registered_manual`,
  `value_matrix_diagnostic`, and `learned_calibrated`.
- `equal_sanity` is a diagnostic fallback, not T1 evidence.
- `pre_registered_manual` is the main T1 value-source path.
- `PolicyMemory` is being moved from SWE-bench `Stage` to
  `WorkflowSegment`.
- old `value_proxy_noise.py`, `swebench_runtime.py`, and
  `swebench_verifier.py` were removed from active source.
- `AutoBudgetEstimator` is being moved away from repo-specific hardcoding;
  benchmark-specific floors belong in `TaskAdapter` output.

Before editing, inspect `git status --short` and the relevant diffs. Do not
revert main-agent changes.

## Required Code Direction

### 1. Task + Value Merge

Keep `ValueAdapter` retired as a standalone architecture concept.
Value belongs inside `TaskAdapter` / task context.

Expected shape:

- `TaskAdapter` returns task identity, description, normalized features,
  difficulty hints, value hints, and value-source metadata.
- SWE-bench task/value matrix handling becomes part of the SWE-bench
  `TaskAdapter` implementation or a helper owned by it.
- active docs/tests should not describe `ValueAdapter` as a separate core
  adapter.

Do not delete value observability behavior. Move the boundary, not the evidence.

### 2. Workflow Segment Boundary

`Stage` is SWE-bench-specific. It may exist inside SWE-bench adapter/runtime
code, but PolicyMemory, Learn Policy Inputs, PolicyBackend contracts, JSONL
standard fields, and audit logic should use `WorkflowSegment`.

Required cleanup:

- `PolicyMemory.routing_prior_summary(...)` should accept a segment, not a
  SWE-bench `Stage`.
- standard record fields should use `routing_prior_segment`, not
  `routing_prior_stage`.
- test fixtures for PolicyMemory should use `workflow_segment`.
- Stage-to-segment mapping belongs in `SwebenchWorkflowAdapter` or the existing
  SWE-bench segment adapter, not in memory or policy logic.

### 3. Progress + Outcome Boundary

Keep the name `ProgressAdapter`.

It should own both process progress and final acceptance/outcome translation:

- progress/no-progress/unknown;
- first useful action / no-progress streak inputs;
- patch/no-patch;
- verifier pass/fail;
- harness trust;
- human or enterprise acceptance when available.

Do not keep a separate verifier adapter as a core architecture concept. A
SWE-bench progress adapter may internally call verifier/harness helpers. For
enterprise tasks without reliable intermediate signals, record unknown/no-signal
instead of inventing progress scores.

### 4. Runtime/Harness Boundary

Do not keep `RuntimeAdapter` as a BudgetFlow adapter.

The mini-SWE-agent bridge can remain as SWE-bench integration code, but it
should not be exported as a core adapter or appear in North Star architecture.
BudgetFlow expects standard events/records; it does not care whether they came
from mini-SWE-agent, Claude Code, Codex, LangChain, or an enterprise harness.

### 5. No Historical Compatibility

Active runtime and tests should not preserve old schemas or old names.

Allowed:

- provider/runtime failure fallback;
- current Bootstrap Policy fallback when no history exists;
- current global fallback cap diagnostic, clearly labeled.

Not allowed:

- old JSONL schema loading into Learn Policy Inputs;
- old value-matrix schema fallback;
- retired terms in active code/tests/docs;
- compatibility tests whose only purpose is to keep old field names alive.

Historical JSONL and old reports are immutable forensic artifacts. Do not edit
them.

## Files To Inspect First

Start with these files:

- `paper1/src/budgetflow/adapters/__init__.py`
- `paper1/src/budgetflow/adapters/swebench_task.py`
- `paper1/src/budgetflow/adapters/swebench_value.py`
- `paper1/src/budgetflow/adapters/swebench_segment.py`
- `paper1/src/budgetflow/adapters/swebench_progress.py`
- `paper1/src/budgetflow/policy_memory.py`
- `paper1/src/budgetflow/learn_policy.py`
- `paper1/src/budgetflow/learning_context.py`
- `paper1/src/budgetflow/experiments/compare_execution.py`
- `paper1/src/budgetflow/run_observability/schema.py`
- `paper1/docs/north_star.md`
- `AGENTS.md`

## Implementation Rules

- Keep behavior stable unless a behavior was only historical compatibility.
- Prefer deleting stale wrappers/tests over preserving aliases.
- Make entrypoints thinner; do not move more semantics into
  `run_mini_swe_compare.py`.
- Do not introduce a new universal runtime abstraction.
- Do not write or rewrite historical reports.
- Do not commit runtime artifacts under `paper1/data/`.
- If a change would alter paid-run semantics, stop and report the exact risk.

## Acceptance Criteria

- Active adapter vocabulary is four families:
  `TaskAdapter`, `WorkflowAdapter`, `ProgressAdapter`, `CostAdapter`.
- `RuntimeAdapter`, `VerifierAdapter`, and standalone `ValueAdapter` are not
  presented as core BudgetFlow architecture.
- PolicyMemory and Learn Policy Inputs consume `WorkflowSegment`, not
  SWE-bench `Stage`.
- SWE-bench-specific concepts are confined to SWE-bench integration/adapters.
- Active value-source records clearly separate sanity fallback, bootstrap
  heuristic, manual pre-registered values, diagnostic matrices, and learned
  calibrated values.
- Old schema compatibility tests are deleted or rewritten as current contract
  tests.
- No-paid tests pass.

## Verification

Run at minimum:

```bash
PYTHONPATH=paper1/src:paper1/../external/mini-swe-agent/src python -m pytest paper1/tests/test_policy_memory.py paper1/tests/test_learning_context.py paper1/tests/test_value_efficiency.py paper1/tests/test_compare_readiness.py paper1/tests/test_experiment_observability.py paper1/tests/test_run_observability_audit.py -q
PYTHONPATH=paper1/src:paper1/../external/mini-swe-agent/src python -m pytest paper1/tests/ -q
git diff --check
```

## Report Back

Return a concise summary with:

- files changed;
- stale abstractions deleted or renamed;
- remaining places where SWE-bench concepts still touch non-adapter code;
- tests run and exact results;
- any paid-run semantic risk.

Do not write a new report file unless explicitly asked.

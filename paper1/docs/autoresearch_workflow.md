# BudgetFlow AutoResearch Workflow

## Current Position

AutoResearch is a research-productivity idea, not the current BudgetFlow paper
mechanism.

This document is durable. It preserves the owner's process thinking about how
to make Codex/worker research loops faster, safer, and easier to resume. The
implementation around it is disposable: coordinator code, worker adapters,
tests, and old workflow directories may be deleted or rewritten whenever they
stop serving the current research loop.

Its value is the operating model it captures:

- remove the owner from manual message-passing between Codex and worker agents;
- keep Codex as the research lead and evidence gate;
- preserve checkpoints so long-running agent work can resume after terminal or
  server failure;
- stop before expensive experiments or direction changes;
- turn worker output into auditable artifacts instead of trusting chat reports.

The current paper path is different and narrower:

```text
T1: maximize verified resolved task value per dollar under a hard budget
T2: explain value-fixed routing efficiency as a mechanism ablation inside T1
```

Therefore AutoResearch code, worker dispatch, and old coordinator tests are
non-blocking unless they affect the BudgetFlow compare path, JSONL
observability, value/RVPD accounting, policy memory, or no-paid verification
gates. This document should stay because it preserves useful thinking about
research acceleration. Stale implementation details should not slow the core
BudgetFlow refactor.

## Role In The Project

AutoResearch is a possible future shell around the BudgetFlow research loop.

It may later coordinate bounded chores such as:

- generating a worker prompt from a Codex-approved goal;
- running a worker in a constrained workspace;
- writing prompts, outputs, reviews, and summaries to disk;
- retrying small failures with consolidated feedback;
- committing and pushing accepted changes;
- pausing for owner approval before large paid experiments.

It should not:

- redefine the BudgetFlow North Star;
- decide whether T1/T2 claims are supported;
- launch large paid experiments on its own;
- edit or migrate historical JSONL;
- make worker self-report equivalent to evidence;
- preserve obsolete code/tests just because they once belonged to AutoResearch.

If there is a conflict between preserving AutoResearch implementation code and
simplifying the current BudgetFlow paper path, simplify the paper path. Keep
the workflow document as the memory artifact; do not keep stale runtime code as
an archive by default.

## Operating Model

```text
Owner <-> Codex reviewer/front-end <-> AutoResearch coordinator <-> Worker
```

| Role | Responsibility |
|---|---|
| Owner | Sets research direction and approves expensive or strategic moves. |
| Codex | Writes goals/issues, reviews artifacts, decides whether evidence changes the paper state. |
| Worker | Executes bounded implementation, debugging, or experiment tasks. |
| AutoResearch | Stores state, invokes workers, checkpoints progress, and enforces pause gates. |

The important design decision is that AutoResearch is coordination, not
governance. Codex remains responsible for interpreting evidence against
`north_star.md`.

## Durable Principles

| Principle | Rule |
|---|---|
| Evidence first | Worker reports are ledgers; JSONL, logs, tests, traces, and commits are facts. |
| Bounded autonomy | AutoResearch can run small approved tasks, not change research direction. |
| Recoverability | Every accepted stage should have enough disk state to resume after interruption. |
| Human approval for risk | Large paid runs, official harness runs, and architecture rewrites pause for owner/Codex judgment. |
| Non-invasive runtime | AutoResearch must be removable without changing BudgetFlow experiment semantics. |
| Document over code | Preserve this workflow document; treat AutoResearch implementation code as replaceable support machinery. |
| Current paper priority | Runtime/evaluation/observability/routing bugs in BudgetFlow outrank AutoResearch implementation bugs. |

## Pause Conditions

AutoResearch must stop and surface the decision to Codex/owner before:

- any paid 3 policies x 10 tasks experiment or larger run;
- changing T1/T2 claims, value metric, or evaluation protocol;
- official SWE-bench Docker runs;
- bulk deletion, migration, or rewriting of experiment data;
- provider billing/auth/model-access failure;
- repeated worker failure after bounded retries;
- any action with materially higher cost, runtime, or rollback risk than the
  active issue.

## Artifact Contract

The source of truth is disk state plus git history, not chat.

Useful artifact classes:

- worker prompt;
- worker output;
- Codex review;
- run JSONL;
- summary log;
- heartbeat/checkpoint;
- final report;
- accepted commit hash.

High-churn temporary files belong under `/tmp`. Durable accepted artifacts
belong in git-tracked docs/reports or the relevant workflow directory.

## Future Reintroduction Gate

AutoResearch can become active again when the core BudgetFlow loop is stable
enough that automation accelerates rather than obscures debugging.

Minimum gate:

- compare runner and checker boundaries are stable;
- JSONL schema captures value, budget mode, policy memory, routing decision,
  and failure axis;
- no-paid gates are fast and meaningful;
- policy-parallel experiment execution is reliable;
- provider/billing failures stop cleanly;
- Codex can review artifacts without reading long chat transcripts;
- old AutoResearch tests/code do not dominate the test suite.

Until then, use AutoResearch as a design note and optional productivity tool,
not as part of the paper's proof path.

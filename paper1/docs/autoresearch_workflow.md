# BudgetFlow AutoResearch Workflow

## Current Status — 2026-06-05

AutoResearch is now a usable semi-automatic research coordinator for bounded
infrastructure tasks in this repository. It is not a fully autonomous research
system and must not change the BudgetFlow paper direction or launch major paid
experiments without Codex/owner approval.

Implemented pieces:

- `src/budgetflow/autoresearch_coordinator.py` state machine;
- `src/budgetflow/autoresearch_goal.py` goal-level coordinator;
- `src/budgetflow/run_autoresearch.py` CLI, including `goal-loop`,
  `goal-review`, `owner_decision.md`, and safe post-gate commit/push;
- `src/budgetflow/autoresearch_codex_gate.py` deterministic artifact review;
- `scripts/autoresearch_fake_worker.py` no-paid Worker smoke;
- `scripts/autoresearch_api_worker.py` thin real-API Worker;
- `scripts/autoresearch_worker_dispatch.py` marker-based fake/API dispatch;
- focused tests for coordinator, guard, gate, goal, CLI, fake worker, and API
  worker;
- reports `034.md` through `042.md`.

Current implementation stage:

```text
design + guard + coordinator + CLI + goal-loop + deterministic gate
+ fake worker + thin real-API worker + dispatch wrapper
+ safe commit/push path validated in Phase L
= runnable semi-automatic coordinator
```

Phase L (`docs/reports/042.md`) validated a real API goal-loop smoke with one
fake-worker issue and one thin-API issue. The goal completed with PASS reviews,
consistent metadata, and successful commit/push. The remaining boundary is
strategic: AutoResearch should coordinate bounded Worker issues, not
automatically iterate the BudgetFlow paper direction.

## Confirmed Direction

AutoResearch exists to remove the owner from the manual copy-paste loop between
Codex and the Worker. It should not become a fully autonomous system that
silently changes research direction or starts expensive experiments.

The intended interaction model is:

```text
Owner <-> Codex front-end/reviewer <-> AutoResearch coordinator <-> Worker
```

Codex remains the research lead, reviewer, and owner-facing front-end.
AutoResearch is the local coordinator that writes prompts, invokes the Worker,
captures outputs, stores checkpoints, and asks Codex for a gate decision.

Worker agents may modify `src/`, `tests/`, docs, and reports when an issue
explicitly authorizes that work. AutoResearch itself should not expand scope. It
records and coordinates the authorized work.

## Implementation Principles

| Principle | Rule |
|---|---|
| Non-invasive by default | AutoResearch must be removable without changing BudgetFlow experiment semantics. |
| Human intervention preserved | The owner can pause, override, or manually continue at any point. |
| Codex gate required | Worker self-report is never enough; Codex reviews artifacts before acceptance. |
| Two retries for small tasks | A failed bounded issue may be retried automatically up to two times. The third failure escalates to Codex/owner judgment. |
| Frequent commits | Accepted small changes should be committed and pushed regularly, with a practical target around ten-minute cadence rather than every tiny file write. |
| Every interaction lands on disk | Worker prompts, worker outputs, Codex reviews, status, and final reports must be written under `.autoresearch/` and/or `docs/reports/`. |
| Paid experiment gate | Any paid 3x10 or larger experiment requires owner approval before execution. |
| Runtime locality | High-churn workflow runtime belongs under `/tmp`; durable state belongs under `.autoresearch/`, `docs/reports/`, and git history. |

## Pause Conditions

AutoResearch must stop and ask the owner through Codex before:

- any paid 3 policies x 10 tasks experiment or larger run;
- changing the paper's main claim, North Star, or evaluation metric;
- large runner, workflow, harness, or storage architecture rewrites;
- deleting, migrating, or bulk-cleaning experiment data;
- official SWE-bench Docker runs or other high-operational-risk harness runs;
- worker failure after two automatic retries;
- any action whose expected cost, runtime, or rollback risk is materially higher
  than the current issue scope.

## Target Directory Layout

```text
paper1/
  .autoresearch/
    program.md
    agents/
      codex.md
      worker.md
    issues/
      034-runtime-fix.md
    workflows/
      034/
        state.json
        worker_prompt.md
        worker_output.md
        codex_review.md
        attempts/
          001/
          002/
        final.md
  docs/
    autoresearch_workflow.md
    reports/
      034.md
```

High-churn temporary files, subprocess logs, scratch checkouts, and intermediate
Worker runtime state should go under a `/tmp/budgetflow-autoresearch-<goal>/`
runtime root. Accepted prompts, reviews, reports, and checkpoint summaries
belong under `.autoresearch/` and `docs/reports/`.

## Minimum Viable Coordinator

The first useful AutoResearch implementation should support:

1. create an issue from a Codex-approved prompt;
2. write the Worker prompt to `.autoresearch/workflows/<id>/worker_prompt.md`;
3. invoke the Worker through a local CLI/script in the current workspace;
4. capture stdout/stderr and require a Markdown worker report on disk;
5. ask Codex to review artifacts;
6. retry a bounded failed issue up to two times;
7. stop on pause conditions;
8. commit and push accepted small changes after Codex gate approval;
9. write a final workflow summary so work can resume after a server crash.

This is deliberately lighter than a full autonomous merge/experiment system. It
is enough to remove manual message carrying while preserving owner control.

## Goal

Use AutoResearch to remove the human operator from the message-passing loop between Codex and Claude Code.

The owner should provide medium-term BudgetFlow goals and approve paid experiment gates. Codex should translate those goals into worker issues, review the evidence, decide the next step, and report status. Claude Code should execute the assigned work and produce verifiable artifacts.

## Why

The current workflow still depends on the owner copying outputs between agents:

- Claude Code runs implementation or experiment work.
- The owner forwards results to Codex.
- Codex reviews and writes the next instruction.
- The owner forwards that instruction back to Claude Code.

This keeps the owner trapped as a manual queue. AutoResearch should automate that loop while preserving Codex as the research lead and preserving owner control over API-cost experiments.

## Operating Model

### Roles

| Role | Responsibility |
|---|---|
| Owner | Defines the Goal, reviews high-level progress, approves 3x10 or larger paid experiments. |
| Codex | Research lead, issue author, reviewer, gatekeeper, and owner reporter. |
| Claude Code | Worker that executes assigned issues and produces artifacts. |
| AutoResearch | Scheduler that runs the loop, stores workflow logs, and supports continuation. |

### Units Of Work

| Unit | Audience | Meaning |
|---|---|---|
| Goal | Owner and Codex | A medium-term research objective, such as reaching credible 3 policies x 10 tasks readiness. |
| Issue | Codex and Claude Code | A bounded execution package generated by Codex for Claude Code. |
| Gate | Codex | A review checkpoint based on tests, run artifacts, reports, and North Star alignment. |

The owner should not manage issue numbers or small task sequencing. Codex owns the issue queue under the active Goal.

## Active Goal Shape

The first intended Goal is:

```text
Make BudgetFlow credible enough to run a 3 policies x 10 tasks experiment.
```

The Goal is complete only when Codex verifies:

- focused tests pass;
- BudgetMemory fixed-normalization evidence is clean;
- observability can distinguish completed, aborted, and stuck runs;
- Budget-only and BudgetFlow baselines are semantically valid enough for the comparison;
- exit reasons and failure axes are not misleading;
- turn traces are preserved for audit;
- policy-level parallelism is ready for a controlled 3x10 run;
- a readiness report is written and matches the artifacts.

## Hard Constraints

### Parallelism

BudgetFlow experiments must follow this execution model:

```text
policy_parallelism = 3 by default
task_parallelism_per_policy = 1
```

Meaning:

- policies may run in parallel when resources allow;
- tasks inside one policy run sequentially;
- budget state, memory updates, and batch accounting must not be mixed across task-level parallel retries.

### Owner Approval

Codex may approve local tests, dry-runs, smoke checks, and paid runs below 3x10.

The owner must approve before:

- any 3x10 paid experiment;
- any larger paid experiment, such as 3x20;
- any run whose expected API cost or operational risk is materially higher than the current smoke/repeat level.

### Checkpointing

After every Codex-accepted stage, the workflow must create a recoverable checkpoint.

A checkpoint should include:

- current issue status;
- worker artifacts;
- Codex gate verdict;
- next action;
- git commit for accepted code/config/report changes;
- push when the remote is available and the branch policy allows it.

This prevents long autonomous loops from drifting without a recoverable history.

## Codex Gate

Codex should review evidence, not worker self-report.

The gate should check:

- command output summaries;
- test results;
- JSONL row counts;
- heartbeat terminal state;
- source distribution and budget-memory fields;
- observability output;
- process state when relevant;
- report-to-data consistency;
- whether the next action still serves the Goal and the BudgetFlow North Star.

Codex verdicts:

| Verdict | Meaning |
|---|---|
| PASS | The issue or Goal stage is accepted. |
| FAIL | The worker must retry with consolidated Codex feedback. |
| BLOCKED | The loop cannot proceed without external input or environment change. |
| NEED_OWNER_APPROVAL | A paid experiment or strategic decision requires owner approval. |

## Claude Code Worker Boundary

Claude Code should receive as much work as is safe for one round.

Each worker round should ask Claude Code to:

- diagnose the relevant problem;
- implement fixes if needed;
- run the required verification;
- produce or update reports;
- summarize artifacts and residual risk.

Claude Code should not:

- redefine the Goal;
- declare the Goal complete;
- decide to start 3x10 or larger paid experiments;
- expand scope beyond the active issue;
- rely on self-report when artifacts can be inspected.

## Reporting To Owner

Codex should report at a high level, not expose internal issue bookkeeping.

Default reporting interval:

```text
10 minutes, or immediately on major state changes.
```

Major state changes:

- entering owner-approval gate;
- discovering a blocker;
- accepting an issue;
- completing the Goal;
- detecting budget, parallelism, or artifact-integrity risk.

Owner reports should answer:

- what changed;
- whether the Goal is closer;
- what remains before 3x10 readiness;
- whether any paid experiment needs approval.

## Reused AutoResearch Concepts

The workflow should reuse these AutoResearch ideas:

- local issue mode;
- project-level `program.md`;
- project-level agent prompt overrides;
- workflow logs;
- continue mode;
- multiple agents in a controlled sequence;
- hard gates plus Codex semantic gates.

The workflow should avoid full automatic merge/close behavior until BudgetFlow-specific gates are proven reliable.

## Source Of Truth

The source of truth is artifacts, not chat.

Expected artifact classes:

- JSONL run records;
- heartbeat files;
- summary logs;
- reports under `docs/reports/`;
- Codex gate notes;
- git commits for accepted changes.

If the chat session is lost, work should resume from this document, the active Goal, workflow logs, reports, and git history.

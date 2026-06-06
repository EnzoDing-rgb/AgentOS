# BudgetFlow AutoResearch Program

## Purpose

Use AutoResearch to coordinate Codex-led research review and Claude Code worker execution without requiring the owner to manually copy messages between agents.

## Roles

- Codex is the research lead, issue author, reviewer, gatekeeper, and owner reporter.
- Claude Code is the worker executor.
- AutoResearch runs the loop and records workflow state.
- The owner defines the Goal and approves expensive experiment gates.

## Goal And Issue Model

- A Goal is the owner-facing medium-term objective.
- Issues are internal worker execution units generated or approved by Codex under the active Goal.
- The owner should not need to manage issue numbers or small sequencing details.

## BudgetFlow Hard Constraints

- Policy-level parallelism is allowed.
- Task-level parallelism inside one policy is not allowed by default.
- Default execution model: `policy_parallelism=3`, `task_parallelism_per_policy=1`.
- 3x10 or larger paid experiments require owner approval before execution.
- Tests, dry-runs, read-only checks, and paid runs smaller than 3x10 may proceed under Codex gate.
- Accepted stages must create recoverable checkpoints.

## Runtime And Storage

- `/tmp` is preferred for AutoResearch runtime logs, scratch repositories, temporary prompts, and high-churn files.
- `/Lishun` is preferred for accepted reports, durable artifacts, JSONL, checkpoints, final traces, and git history.
- Avoid broad filesystem scans on `/Lishun`; prefer precise paths and `rg`.

## Worker Rules

- Execute the active issue as completely as is safe in one round.
- Produce verifiable artifacts, not only prose.
- Run the requested checks and summarize actual outputs.
- Do not redefine the Goal.
- Do not declare the Goal complete.
- Do not start 3x10 or larger paid experiments.
- Do not expand scope beyond the active issue.

## Gate Rules

Codex should review:

- command outputs;
- run artifacts;
- JSONL row counts when applicable;
- heartbeat terminal state when applicable;
- source distribution when applicable;
- report-to-data consistency;
- alignment with `docs/north_star.md`;
- alignment with `docs/takeaway.md`;
- whether owner approval is required.

Valid verdicts:

- `PASS`
- `FAIL`
- `BLOCKED`
- `NEED_OWNER_APPROVAL`

## Read-Only Smoke Policy

During AutoResearch loop testing, BudgetFlow is a test case only.

Allowed:

- read exact files;
- run non-mutating checks;
- write AutoResearch workflow logs;
- write an explicit smoke report only when the issue asks for it.

Not allowed during smoke:

- modify `src/`;
- modify `tests/`;
- modify `data/runs/`;
- start paid API experiments;
- change experiment code.

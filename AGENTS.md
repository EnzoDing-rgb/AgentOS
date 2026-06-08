# Agent Operating Rules

This file is the repo-level operating contract for Codex-style agents working in this repository.

## North Star

- BudgetFlow's Tier 1 claim is the compass: under a shared hard budget, maximize Yield.
- Tier 2 is a mechanism claim: policy/routing efficiency must not be weaker than dummy/static/budget-tight baselines, and must show whether model-tier decisions improve value and cost efficiency.
- Tier 2 serves Tier 1. Do not optimize routing savings in a way that reduces value-weighted outcomes.

## Experiment Gold Standard

After every experiment, inspect artifacts before drawing conclusions:

- Evaluation Validity: do the T1/T2 metrics really measure the claim?
- Harness & Task Trust: did the harness, task, verifier, and task environment behave credibly?
- Infra Health: check runtime, worktrees, NFS, provider, parser, trace, checker, budget mode, and value source.
- Learning Loop Reality: Cost Memory, Routing Memory, and Escalation Memory must actually affect the next decision, not only appear in logs.
- Mechanism Diagnosis: explain whether outcomes came from model capability, task difficulty, routing, caps, Value-Triggered Escalation, evaluation, or observability.
- Segment-Splitting Risk: workflow-segment-aware routing is a mechanism hypothesis, not an axiom. It may improve T2 by using tiers at the right work segment, but it may also add switching noise, cache loss, prompt drift, or brittle heuristics that hurt T1.
- Segment-Aware Control: when evaluating the T2 mechanism, report segment-aware BudgetFlow against a task-level or per-request control. Explain pass/value delta, cost delta, model-tier use, and whether segment signals helped routing or merely added noise.
- Strong Baseline Diagnosis: `budget_only_tight` is a strong budget-pressure baseline and diagnostic mirror, not the paper target. When a Bootstrap Policy loses to it, first diagnose which reusable mechanism principle the budget-only control exposed, such as early expensive-tier frontload, pressure gating, repair runway, or stop-loss behavior, then decide whether BudgetFlow should absorb that principle through its own value-aware, segment-aware, repair/escalation/stop mechanisms. Do not weaken the control, cherry-pick tasks, tune values after outcomes, or turn the story into "BudgetFlow copied the baseline."
- Long-Term Iteration Value: before fixing a symptom, ask whether the fix improves future diagnosis, scale-up, or paper evidence. Do not overfit the current five familiar tasks.
- Reflection Loop: after each experiment, audit whether the metric matrix, logs, checker output, and memory updates are sufficient to support the next learning/routing decision. Do not treat pass rate alone as an explanation.

## Eight Gold Standards

These are the short-form checks every worker should keep in view:

- T1 first: report Yield and Yield per Dollar before mechanism storytelling.
- T2 frontier: compare verified resolution and cost under the same budget.
- Model-tier diagnosis: report productive use, no-progress spend, and why expensive tiers were selected.
- No-patch rate: distinguish no-patch exits, failed patches, verifier failures, and infra failures.
- Segment control: compare Segment-Aware Routing against a task-level or per-request control.
- Checker first: inspect JSONL, trace, checker, compact audit, and harness trust before drawing conclusions.
- No-paid gates first: pass no-paid tests, dry-runs, value/cost confidence, and provider preflight before paid runs.
- Historical evidence is immutable: do not patch historical JSONL or old reports to make a current story cleaner.
- SWE-bench as testbed: SWE-bench is the current strongest pressure test for the abstraction, not the BudgetFlow Mechanism itself. If an interface makes SWE-bench adaptation awkward, it is probably over-abstracted or misplaced; if it only works for SWE-bench, benchmark detail has leaked into the mechanism.

## Run Discipline

- Fix known infra, learning, observability, value-source, or harness bugs before running paid experiments.
- For policy comparisons, tasks are serial within each policy and policies run in parallel. For three strategies, `--jobs 3` is the default unless a concrete blocker is documented.
- Before paid runs, check strategy count, task count, `--jobs`, value profile, value matrix path, budget mode, output stem, provider, runtime root, worktree isolation, trace, and checker path.
- Small paid runs, such as 3 policies x 3-5 tasks, are infra and learning diagnostics. Do not treat them as paper-level evidence.
- When segment-aware routing is a suspect root cause, include a task-level or per-request routing control. A four-policy diagnostic is acceptable when it cleanly separates baseline, segment-aware routing, value-aware segment routing, and value-aware task-level routing.
- Paper-level evidence should scale beyond the recurring gold-pass task set. The target shape is at least three policies across roughly 30-50 tasks per policy, after the infra and learning gates are trustworthy.
- Stop on provider billing/auth/model-access/preflight blockers. Do not reinterpret provider failures as model or routing evidence.
- Historical JSONL and historical reports are immutable evidence. Mark old artifacts forensic-only when needed; do not patch them in place.
- Runtime artifacts under `paper1/data/` are not source code. Do not commit trace, heartbeat, checkpoint, or run-output files unless explicitly requested.
- Model pricing and capability priors belong in a versioned tier catalog. Web search is allowed for offline catalog calibration, but paid-run execution must use the pre-registered catalog and stop if cost/progress confidence is missing or stale.
- Local harness results are part of the evidence system. Because nested Docker is not assumed available, local harness adapters, compat patches, host dependencies, and checker invalidation rules must be treated as first-class evaluation risks.

## Current Vocabulary

- Use the terminology in `paper1/docs/north_star.md`.
- Use Value-Driven Budget Allocation in research prose.
- Use Cost Memory, Routing Memory, and Escalation Memory for the three learning views.
- Use Value-Triggered Escalation for the high-value pre-patch T3 window.
- Use Strongest Model for the strongest configured tier. Prefer model-tier diagnostics unless a specific runtime field is explicitly tier-specific.
- Say infra. Do not introduce infer, info, or other speech-to-text artifacts as project concepts.

## Agent Workflow

- Main-agent judgment owns architecture, routing, evaluation, learning, and paper-claim decisions.
- Use subagents for low-value, high-token scans, narrow code/test edits, artifact enumeration, or failure classification when it saves cost or wall time without outsourcing main-agent judgment. Main-agent judgment owns architecture, routing, evaluation, learning, and paper-claim decisions.
- Use skills only when they materially improve the current work. Do not mechanically read or invoke generic system skills in a way that distracts from BudgetFlow's north star, experiment discipline, or the user's immediate instruction. In particular, do not force a Test-Driven Development workflow for documentation-only work, experiment judgment, review, or other changes where it is not actually needed.
- Avoid broad, unbounded repo archaeology. Read the few files and artifacts needed to answer the current evidence question, then act or summarize the remaining uncertainty.
- Do not keep historical compatibility in active runtime, tests, or current docs unless it protects a current paid-run safety boundary. Historical JSONL/reports are forensic evidence; old schemas and retired terms must not drive Learn Policy Inputs, ValueSource, CostSource, routing, or paper metrics.
- Keep docs meaningful: update `paper1/docs/north_star.md` or `paper1/docs/progress.md` only when a real decision changes.
- Commit and push stable slices after no-paid gates pass. Avoid noisy commits, but do not leave verified mechanism changes uncommitted.

## Worker Reports

- For substantial worker implementation slices, write a new report under `paper1/docs/reports/`.
- The report should include: objective, files changed, interface decisions, deleted stale paths/tests, verification commands and results, residual risks, and next recommended slice.
- Do not spend time rewriting historical reports. New reports describe new work.

## Learning Scope

- Do not assume every failure signal is learnable. Pick a few general, reusable signals and make sure the runtime actually consumes them.
- Current learning signals are cap sufficiency/cost, routing outcome by task/repo/segment, model-tier productivity versus no-progress cost, provider/parser failures, and harness-trusted verified outcome.
- A new signal earns its place only if it can influence a future cap, route, stop/continue, or escalation decision and can be audited from JSONL.
- Schema-aware learning matters: Memory loading uses current-schema, harness-trusted records. Archived rows are forensic and cannot enter active Learn Policy Inputs.
- Cost Memory, Routing Memory, and Escalation Memory learn from clean current records and explicit adapter configuration. Historical runs inform design review and reports, not runtime routing behavior.

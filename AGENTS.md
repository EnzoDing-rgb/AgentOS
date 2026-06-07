# Agent Operating Rules

This file is the repo-level operating contract for Codex-style agents working in this repository.

## North Star

- BudgetFlow's Tier 1 claim is the compass: under a shared hard budget, maximize verified resolved task value.
- Tier 2 is a mechanism claim: routing/cost-efficiency must not be weaker than dummy/static/budget-tight baselines, and must explain whether T3 / Strongest Model is used productively.
- Tier 2 serves Tier 1. Do not optimize routing savings in a way that reduces value-weighted outcomes.

## Experiment Gold Standard

After every experiment, inspect artifacts before drawing conclusions:

- Evaluation Validity: do the T1/T2 metrics really measure the claim?
- Harness & Task Trust: did the harness, task, verifier, and task environment behave credibly?
- Infra Health: check runtime, worktrees, NFS, provider, parser, trace, checker, budget mode, and value source.
- Learning Loop Reality: Cost Memory, Routing Memory, and Escalation Memory must actually affect the next decision, not only appear in logs.
- Mechanism Diagnosis: explain whether outcomes came from model capability, task difficulty, routing, caps, Value-Triggered Escalation, evaluation, or observability.
- Stage-Splitting Risk: localization/repair/validation routing is a mechanism hypothesis, not an axiom. It may improve T2 by using tiers at the right workflow stage, but it may also add switching noise, cache loss, prompt drift, or brittle heuristics that hurt T1.
- Strong Baseline Diagnosis: `budget_only_tight` is a strong budget-pressure baseline and diagnostic mirror, not the paper target. When BFV/BFC lose to it, first diagnose which reusable mechanism principle BO exposed, such as early T3 frontload, pressure gating, repair runway, or stop-loss behavior, then decide whether BudgetFlow should absorb that principle through its own value-aware, stage-aware, repair/escalation/stop mechanisms. Do not weaken BO, cherry-pick tasks, tune values after outcomes, or turn the story into "BudgetFlow copied BO."
- Long-Term Iteration Value: before fixing a symptom, ask whether the fix improves future diagnosis, scale-up, or paper evidence. Do not overfit the current five familiar tasks.

## Run Discipline

- Fix known infra, learning, observability, value-source, or harness bugs before running paid experiments.
- For policy comparisons, tasks are serial within each policy and policies run in parallel. For three strategies, `--jobs 3` is the default unless a concrete blocker is documented.
- Before paid runs, check strategy count, task count, `--jobs`, value profile, value matrix path, budget mode, output stem, provider, runtime root, worktree isolation, trace, and checker path.
- Small paid runs, such as 3 policies x 3-5 tasks, are infra and learning diagnostics. Do not treat them as paper-level evidence.
- When stage-aware routing is a suspect root cause, include a no-stage or task-level routing control instead of assuming the three-stage split is beneficial. A four-policy diagnostic is acceptable when it cleanly separates baseline, stage-aware routing, value-aware stage routing, and value-aware no-stage/task-level routing.
- Paper-level evidence should scale beyond the recurring gold-pass task set. The target shape is at least three policies across roughly 30-50 tasks per policy, after the infra and learning gates are trustworthy.
- Stop on provider billing/auth/model-access/preflight blockers. Do not reinterpret provider failures as model or routing evidence.
- Historical JSONL and historical reports are immutable evidence. Mark old artifacts forensic-only when needed; do not patch them in place.
- Runtime artifacts under `paper1/data/` are not source code. Do not commit trace, heartbeat, checkpoint, or run-output files unless explicitly requested.
- Model pricing and capability priors belong in a versioned tier catalog. Web search is allowed for offline catalog calibration, but paid-run execution must use the pre-registered catalog and stop if cost/progress provenance is missing or stale.

## Current Vocabulary

- Use Value-Driven Budget Allocation, not Automatic Budgeting, in research prose.
- Use Cost Memory, Routing Memory, and Escalation Memory for the three learning views.
- Use Value-Triggered Escalation, not salvage, for the high-value pre-patch T3 window.
- Use T3 / Strongest Model, T3 Productive Rate, and T3 No-Progress Cost. Avoid strong-tier phrasing.
- Say infra. Do not introduce infer, info, or other speech-to-text artifacts as project concepts.

## Agent Workflow

- Main-agent judgment owns architecture, routing, evaluation, learning, and paper-claim decisions.
- Use subagents for low-value, high-token scans or classification work when it saves cost without outsourcing core judgment.
- Use skills only when they materially improve the current work. Do not mechanically read or invoke generic system skills in a way that distracts from BudgetFlow's north star, experiment discipline, or the user's immediate instruction. In particular, do not force a Test-Driven Development workflow for documentation-only work, experiment judgment, review, or other changes where it is not actually needed.
- Keep docs load-bearing: update `paper1/docs/north_star.md`, `paper1/docs/CONTEXT.md`, or `paper1/docs/progress.md` only when a real decision changes.
- Commit and push stable slices after no-paid gates pass. Avoid noisy commits, but do not leave verified core changes uncommitted.

## Learning Scope

- Do not assume every failure signal is learnable. Pick a few general, reusable signals and make sure the runtime actually consumes them.
- Current core learning signals are cap sufficiency/cost, routing outcome by task/repo/stage, T3 productivity versus no-progress cost, provider/parser failures, and harness-trusted verified outcome.
- A new signal earns its place only if it can influence a future cap, route, stop/continue, or escalation decision and can be audited from JSONL.
- Schema-aware learning matters: old trace fields may be forensic or weak positive evidence, but schema-mismatched missing/false progress must not create negative T3 no-progress evidence that changes routing.

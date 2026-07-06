# Agent Operating Rules

This file is the repo-level operating contract for Codex-style agents working in this repository.

## Experiment Gold Standard

After every experiment, inspect artifacts before drawing conclusions:

- Evaluation Validity: do the Claim 1 and Claim 2 metrics measure the claim? Confirm that the value proxy is frozen, reasonable, and not post-hoc fitted. Keep auxiliary metrics secondary.
- Harness & Task Trust: did the local harness, task, verifier, and task environment behave credibly? Check for false positives, false negatives, unstable tasks, and tasks that are too easy or too hard for the current evidence question.
- Infrastructure Health: check runtime, worktrees, concurrency, NFS, provider, parser, trace, checker, budget mode, value source, and cost source.
- Learning Loop Reality: Cost Memory, Routing Memory, and Escalation Memory must affect the next cap, route, stop/continue decision, or Strongest Model escalation, not only appear in logs.
- Mechanism Diagnosis: explain whether outcomes came from model capability, task difficulty, routing, caps, Value-Triggered Escalation, evaluation, or observability.
- Stage/Segment-Splitting Risk: workflow-stage or segment-aware routing is a mechanism hypothesis, not an axiom. It may improve Claim 2 by using model tiers at the right work segment, but it may also add switching noise, cache loss, prompt drift, or brittle heuristics that hurt Claim 1.
- Stage/Segment-Aware Control: when evaluating the Claim 2 mechanism, report stage/segment-aware BudgetFlow against a task-level or per-request control. Explain pass/value delta, cost delta, Strongest Model productive-use delta, and whether stage signals helped routing or merely added noise.
- Strong Baseline Diagnosis: pure-tier, budget-only, and static-router baselines are diagnostic mirrors, not paper targets. When BudgetFlow loses to one, first diagnose the reusable principle it exposed, such as all-T2/all-Strongest frontier posture, early expensive-tier frontload, pressure gating, repair runway, or stop-loss behavior. Then decide whether BudgetFlow should absorb that principle through value-aware frontier selection, routing, repair, escalation, or stop mechanisms. Keep the control strong, keep tasks fixed, keep values frozen, and avoid a "BudgetFlow copied the baseline" story.
- Long-Term Iteration Value: before fixing a symptom, ask whether the fix improves future diagnosis, scale-up, or paper evidence. Do not overfit the current five familiar tasks.
- Reflection Loop: after each experiment, audit whether the metric matrix, logs, checker output, and memory updates are sufficient to support the next learning/routing decision. Do not treat pass rate alone as an explanation. Each experiment should identify which layer limits paper value: claim, metric, harness, task, infrastructure, learning loop, or mechanism.

## Short Gold Standards

These are the short-form checks every worker should keep in view:

1. Claim 1 first: under a fixed shared hard budget, maximize Total Resolved Value. Report Resolved Count, Resolved Rate, Total Spend, Cost per Resolved Task, Total Resolved Value, and Total Resolved Value per Dollar before mechanism storytelling.
2. Claim 2 explains Claim 1: compare verified resolution, cost efficiency, and Strongest Model productive use under the same budget. Routing savings are useful only when they protect or improve Claim 1.
3. Strong baselines stay strong: when BudgetFlow loses to pure-tier, budget-only, or static-router controls, diagnose what the control exposed and absorb only the reusable principle. Keep tasks fixed and values frozen.
4. Checker first: inspect JSONL, trace, checker, compact audit, harness trust, value source, cost source, and memory inputs before drawing conclusions.
5. No-paid gates first: pass no-paid tests, dry-runs, value/cost confidence, provider preflight, parser checks, budget-mode checks, and worktree isolation before paid runs.
6. Stage/segment control: compare stage-aware routing against task-level or per-request controls. Report pass/value/cost and Strongest Model productive-use deltas.
7. Memory must be real: Cost Memory, Routing Memory, and Escalation Memory must consume fresh, schema-compatible, harness-trusted records and influence the next cap, route, stop/continue, or escalation decision.
8. SWE-bench is a testbed: local harness adapters, compat patches, and repo-specific test runners are evaluation infra, not the BudgetFlow mechanism. Benchmark detail must not leak into Learn Policy Inputs, ValueSource, CostSource, routing, or paper metrics.
9. Research code clarity beats compatibility: this is top-conference research code, not a stable public API. Prefer clean architecture, deletion, and auditable schemas over compatibility fallbacks or retired aliases. Keep historical artifacts immutable and keep paid-run safety gates; do not preserve stale runtime paths merely because old reports used them.

## Run Discipline

- Fix known infra, learning, observability, value-source, or harness bugs before running paid experiments.
- For policy comparisons, tasks are serial within each policy and policies run in parallel. For the current five-policy Claim 1 mainline, `--jobs 5` is the default unless a concrete blocker is documented.
- Before paid runs, check strategy count, task count, `--jobs`, value profile, value matrix path, budget mode, output stem, provider, runtime root, worktree isolation, trace, and checker path.
- Runtime/I/O discipline: keep source code, configs, docs, value matrices, frozen/budget plans, and final JSONL/checkpoint/summary evidence in the repo. Put high-churn regenerable files under local scratch, normally `/tmp/budgetflow-runtime`: git worktrees, repo mirrors, locks, trace scratch, pytest caches, editable installs, temporary build trees, and agent temp files. `/tmp` is acceptable scratch but not the only evidence store.
- Do not use `/Lishun` or other NFS paths for runtime root, worktree root, repo cache, locks, trace scratch, mini-swe-agent source, or SWE-bench export fallback. If a needed dependency is only on NFS, localize it into the repo or `/tmp` scratch and make the resolver fail fast instead of silently falling back.
- Small paid runs, such as 4 policies x 3-5 tasks, are infra and learning diagnostics. Do not treat them as paper-level evidence.
- When segment-aware routing is a suspect root cause, include a task-level or per-request routing control. A four-policy diagnostic is acceptable when it cleanly separates baseline, segment-aware routing, value-aware segment routing, and value-aware task-level routing.
- Paper-level Claim 1 evidence currently targets five policies across the fixed 30-task set, after the infra and learning gates are trustworthy. Do not expand to 50 tasks unless a new evidence question requires it.
- Stop on provider billing/auth/model-access/preflight blockers. Do not reinterpret provider failures as model or routing evidence.
- Historical JSONL and historical reports are immutable evidence. Mark old artifacts forensic-only when needed; do not patch them in place.
- Runtime artifacts under `paper1/data/` are not source code. Do not commit trace, heartbeat, checkpoint, or run-output files unless explicitly requested.
- Model pricing and capability priors belong in a versioned tier catalog. Do not recalibrate paper experiments from public provider prices during a paid-run line; use the frozen normalized catalog unless the run is explicitly a new CostSource study. Paid-run execution must use the pre-registered catalog and stop if cost/progress confidence is missing or stale.
- Mainline task values use `criticality_level = normal | high | critical` mapped through the frozen ValueSource. Manual overrides may change only `criticality_level` and Estimated Task Token Demand fields, with from/to/source/reason recorded. Do not directly override model_fit, expected uplift, route, or budget cap.
- Use Estimated Task Token Demand in prose for the run-before estimate of token/runway need. The active schema path remains `task_effort_multiplier` / `final_task_effort` until the code schema is renamed. Runtime, compiler, and ModelFit estimation consume final estimated token demand through that path; do not add Difficulty aliases or revive retired effort fields.
- The mainline catalog must not hide asymmetric KV-cache discounts. Cache discount experiments belong in explicit sensitivity catalogs/reports.
- Local harness results are part of the evidence system. Because nested Docker is not assumed available, local harness adapters, compat patches, host dependencies, and checker invalidation rules must be treated as first-class evaluation risks.

## Current Vocabulary

- Use the terminology in `paper1/docs/north_star.md`.
- Use Value-Driven Budget Allocation in research prose.
- Use Cost Memory, Routing Memory, and Escalation Memory for the three learning views.
- Use Value-Triggered Escalation for the high-value pre-patch T3 window.
- Use Strongest Model for the strongest configured tier. Prefer model-tier diagnostics unless a specific runtime field is explicitly tier-specific.
- Say infra. Do not introduce infer, info, or other speech-to-text artifacts as project concepts.
- The user often uses speech input. Treat odd symbols, malformed words, and sudden unfamiliar terms as possible speech-to-text noise unless the user explicitly introduces them as new vocabulary, concepts, symbols, or terms. Filter obvious noise silently; when meaning is unclear, ask the user instead of adopting the noisy phrase into project terminology.

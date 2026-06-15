# BudgetFlow North Star

This file is the project vocabulary and paper-claim source. Use it for current
docs, prompts, handoffs, reports, and reviewer-facing prose.

## Core Terminology

Use **Claim 1** and **Claim 2** for paper claims. Reserve **T1/T2/T3** for model
tiers only.

| Term | Meaning |
|---|---|
| BudgetFlow | Value-aware budget governance for multi-step agent workflows under shared hard budgets. |
| Claim 1 | Under one shared hard budget, BudgetFlow maximizes normalized verified resolved value, called Yield. |
| Claim 2 | BudgetFlow's value-aware budget allocation, routing, escalation, stop, and learning mechanisms explain how Claim 1 is achieved and must improve or preserve value/cost efficiency against strong diagnostic controls. |
| Yield | Total resolved task value within a shared budget window. It is not raw task count. |
| Yield per Dollar | Total resolved task value divided by model spend. It is the main efficiency diagnostic. |
| Value-Driven Budget Allocation | Allocation of task caps and spend from Task Value, Task Effort, Model Fit, expected payoff, cost, and budget pressure. |
| Task Value | Estimated utility of a verified resolved outcome. It answers "what is this task worth if solved?" |
| Task Effort | Estimated work, runway, or expected cost needed to resolve a task. It answers "how much budget should this task need?" |
| Model Fit | Estimated suitability of each model tier for a task, repo, or workflow stage. It answers "which tier is likely to make verified progress here?" |
| AllocationContext | Standard decision input that carries Task Value, Task Effort, Model Fit, budget state, cost source, and confidence into policy decisions. |
| Tier Boundary Selection | Choosing whether a BudgetFlow policy should behave near the T2 boundary, near the T3 boundary, or use mixed model-tier routing for the current allocation context. |
| ValueSource | Versioned input that defines or estimates task value for one run or deployment. |
| CostSource | Versioned input that defines or estimates model cost for one run or deployment. |
| TaskAdapter | Adapter that turns external work into standard BudgetFlow task inputs: identity, description, features, difficulty/value hints, and value-source metadata. |
| BudgetAdapter | Adapter that turns customer or experiment budget input into a standard budget window, hard/soft cap, shared scope, allowed model pool, source, and confidence. |
| CostAdapter | Adapter that turns public price catalogs, provider estimates, invoices, enterprise rate cards, or manual overrides into a standard cost signal. |
| ProgressAdapter | Adapter that turns process evidence and final acceptance into standard progress/outcome signals. Intermediate progress can be unknown; final acceptance defines resolved. |
| Policy Backend | Pluggable strategy that recommends cap, model tier, escalation, de-escalation, stop, and continue decisions. |
| Cost Memory | Memory for cost, cap sufficiency, task value, and Yield per Dollar evidence. |
| Routing Memory | Memory for backend choices, stage/segment outcomes, failure axes, and route effectiveness. |
| Escalation Memory | Memory for whether Strongest Model turns were productive. |
| Value-Triggered Escalation | Bounded use of a stronger model tier for high-value tasks when expected marginal value justifies it. |
| Strongest Model | The strongest configured model tier. It is one model-tier option, not the system claim. |
| Infra | Runtime, provider, parser, harness, filesystem, worktree, and environment health. |

## What BudgetFlow Is

BudgetFlow is a governance layer above agent runtimes such as Codex, Claude
Code, mini-SWE-agent, or enterprise workflows. It owns shared budget accounts,
task value, cost source, policy decisions, verified outcomes, learning inputs,
and audit.

For this paper, SWE-bench is the pressure test because it provides repeatable
tasks and verifiers. It is not the BudgetFlow mechanism. SWE-bench-specific details such
as fail-to-pass tests, pass-to-pass tests, patch extraction, worktree diffs, and
repo-specific runners belong behind adapters.

The product goal is simple: every dollar of model spend should create more
verified task value. BudgetFlow allocates spend from an AllocationContext:
Task Value sets the utility target, Task Effort estimates required runway, and
Model Fit estimates which model tier is likely to make verified progress. This
keeps the system broader than a routing heuristic.

## Claims And Metrics

| Claim | Main question | Primary evidence |
|---|---|---|
| Claim 1 | Under the same shared hard budget, does BudgetFlow resolve more normalized task value? | Yield and Yield per Dollar at fixed budget. |
| Claim 2 | Why did that happen, and are the mechanisms reusable? | Resolution-cost frontier, Strongest Model productive use, Tier Boundary Selection, stop-loss behavior, stage/task routing controls, memory effect, and failure attribution. |

Claim 1 is the objective. Claim 2 explains the mechanism. Routing savings,
stage-aware routing, Tier Boundary Selection, stop-loss, escalation, and memory
are useful only when they protect or improve Claim 1.

Resolved task count, pass rate, Pass per Dollar, average turns, and no-patch
rate are diagnostics. They must not replace Yield or Yield per Dollar as the
main claim metric.

## Value And Cost Discipline

Task Value is a proxy, so every paid run must make the proxy auditable.

- Freeze the ValueSource before execution. Do not change task values after
  seeing outcomes.
- Manual value, when used, is a pre-registered researcher value proxy based on
  task priority, expected user impact, scope, and benchmark diversity. Treat it
  as a proxy, not ground truth.
- Report at least equal value and the chosen Task Value profile. Task Effort
  diagnostics can be reported separately, but they must not be presented as
  Claim 1 value.
- Explain whether the direction of the signal depends on the chosen value
  profile.
- Do not treat "easy to solve" as "high value." Task Effort can inform budget
  runway and cost estimates, but it is not Task Value.
- In enterprise deployments, value may be supplied by customer priority,
  revenue, SLA, risk, or an external system. In SWE-bench experiments, value is
  a pre-registered research proxy and must be treated as a threat to validity.

Task Effort and cost follow the same rule.

- Use a versioned model-tier catalog for paid runs.
- Record catalog path, revision, provider, and any price multipliers.
- Keep Task Effort separate from Task Value. Metadata heuristics, historical
  cost, turns, test counts, patch size, and repo priors estimate runway or
  expected cost; they do not define outcome utility.
- Treat pure T2 and pure T3 baselines as boundary diagnostics. If a pure tier is
  best for a task distribution and model catalog, BudgetFlow should diagnose
  and absorb the reusable principle through Tier Boundary Selection, not weaken
  the baseline.

## Mechanism Layers

| Layer | Responsibility |
|---|---|
| BudgetFlow Mechanism | Shared hard-budget ledger, reservation, settlement, verifier-grounded outcome, stop-loss primitives, trace/audit/replay, and same-budget policy comparison. |
| Domain Adapters | Task, workflow stage/segment, progress/outcome, repo runner, and cost mappings for one benchmark or enterprise workflow. |
| Policy Backend | Cap recommendation, Tier Boundary Selection, model-tier routing, escalation, de-escalation, stop/continue, and learned or heuristic priors. |
| Learn Policy Inputs | Cost Memory, Routing Memory, and Escalation Memory. These are optional Claim 2 inputs for policy and audit, not hidden Claim 1 requirements. |
| Observability | JSONL schema, turn traces, checker, compact audit, failure attribution, and reports. |

Adapter boundaries should be useful but not ceremonial. If an interface makes
SWE-bench adaptation awkward, it is probably misplaced. If an interface only
works for SWE-bench, benchmark detail has leaked into the mechanism.

## Evaluation Controls

Use these controls to evaluate the claims. Keep tasks, value source, cost
source, budget, model catalog, and harness fixed within one comparison.

| Control | Role |
|---|---|
| Bare T2 | Pure middle-tier boundary. Tests whether a conservative fixed model is enough. |
| Bare T3 | Pure strongest-tier boundary. Tests whether the current price frontier makes "use the strongest model" optimal. |
| Static/Frozen Enterprise Router | Pre-registered non-learning router. Tests a realistic enterprise routing baseline without BudgetFlow's shared-budget adaptation. |
| BudgetFlow Same Router | Same frozen router inside BudgetFlow. Isolates shared ledger, accounting, stop/escalation primitives, and observability from routing quality. |
| BudgetFlow Full | Value-aware BudgetFlow policy with AllocationContext, Tier Boundary Selection, routing, escalation, stop, and learning inputs when enabled. |
| Task-level or Per-request Control | Control for stage/segment-aware routing. Tests whether stage signals help or add switching noise. |

Strong controls stay strong. Do not weaken pure-tier, budget-only, or static
router baselines to make BudgetFlow look better. When BudgetFlow loses, explain
what principle the control exposed and whether BudgetFlow should absorb it.

## Experiment Audit After Every Paid Run

Run this audit before writing conclusions:

1. Evaluation Validity: do Claim 1 and Claim 2 metrics measure the claim? Is the
   ValueSource frozen, reasonable, and not post-hoc fitted?
2. Harness & Task Trust: did the local harness, task, verifier, and repo
   environment behave credibly? Check false positives, false negatives, overly
   easy tasks, ceiling tasks, and unstable tasks.
3. Infra Health: check runtime, worktrees, NFS, provider, parser, trace,
   checker, budget mode, value source, and cost source.
4. Learning Loop Reality: did Cost Memory, Routing Memory, and Escalation
   Memory actually affect the next cap, route, stop/continue, or escalation
   decision? If memory is disabled for a clean Claim 1 run, say so explicitly.
5. Mechanism Diagnosis: explain whether outcomes came from model capability,
   Task Value, Task Effort, Model Fit, routing, budget caps,
   Tier Boundary Selection, Value-Triggered Escalation, evaluation,
   observability, parser/harness failures, or model-price boundary.

The point of each experiment is not to "get a good result." The point is to
identify which layer currently limits paper value: claim, metric, harness,
infra, learning loop, or mechanism.

## Evidence Discipline

- Historical JSONL and historical reports are immutable evidence. Do not patch
  old artifacts to make the current story cleaner.
- Small paid runs are diagnostics, not paper-level evidence.
- Local harness results are part of the evidence system. Because nested Docker
  is not assumed available, local harness adapters, compat patches, host
  dependencies, and checker invalidation rules are first-class evaluation
  risks.
- Runtime artifacts under `paper1/data/` are not source code. Do not commit
  trace, heartbeat, checkpoint, or run-output files unless explicitly requested.
- Before paid runs, pass no-paid gates for tests, value/cost confidence,
  provider access, parser behavior, budget mode, worktree isolation, and
  checker output.

# BudgetFlow North Star

## Vision

BudgetFlow is a value-aware budget governance layer for multi-step agent workflows.

It manages model choice, task budget, escalation, and stop decisions under a shared budget account. The target is to make value flow through an organization under hard budget constraints: complete the highest-value verified work per dollar, not simply minimize tokens for a single request.

The core product problem is organizational rather than only technical. A company may have engineers, analysts, operations staff, and researchers sharing one AI budget. Fixed per-person or per-team quotas force awkward manual exceptions and can discriminate against non-technical work whose value is real but harder to price. BudgetFlow allocates spend by task value, expected payoff, difficulty, and budget pressure instead of by identity or role.

## Generality Beyond SWE-bench

The current implementation uses SWE-bench because it gives reproducible tasks, executable verification, and clean pass/fail evidence. The framework is designed around pluggable task context, budget context, history, and verifier interfaces, so the same router can be applied to other enterprise agent workflows.

BudgetFlow's generic unit is not a SWE-bench issue. The generic unit is a `TaskContext`: a piece of work with value, difficulty signals, budget constraints, runtime state, and a verifier.

Different organizations should be able to inject their own context:

| Enterprise Input | BudgetFlow Use |
|---|---|
| Task priority | Convert business value into budget willingness. |
| Task batch | Evaluate a stable stream of work against one shared budget pool. |
| Business direction | Bias allocation toward strategic areas without hard-coding per-team budgets. |
| Value signal | Weight tasks by impact when known; fall back to heuristics when unknown. |
| Historical outcomes | Estimate task cap, success probability, and escalation timing. |
| Department or project budget | Select the relevant budget account and time window. |
| Model price table | Compute real cost for local, proxy, or API models. |
| Verification rule | Decide whether the task is actually complete. |
| Risk policy | Set max spend, allowed backends, retry policy, and audit requirements. |
| Runtime adapter | Connect BudgetFlow to Claude Code, Codex, mini-SWE-agent, internal tools, or workflow engines. |

Conceptual interface:

```python
@dataclass
class TaskContext:
    task_id: str
    task_type: str
    description: str
    value: float
    priority_hint: str | None
    features: dict[str, float | str | bool]
    verifier: Verifier
    runtime: AgentRuntime

@dataclass
class BudgetContext:
    account_id: str
    window: str              # task, day, week, project, organization
    remaining_usd: float
    hard_cap_usd: float
    soft_cap_usd: float | None
    allowed_backends: list[str]

@dataclass
class HistoryContext:
    similar_tasks: list[OutcomeRecord]
    model_success_rates: dict[str, float]
    cost_priors: dict[str, float]
    value_priors: dict[str, float]
    difficulty_priors: dict[str, float]
    escalation_priors: dict[str, float]

class BudgetFlowPolicy:
    def estimate_value(self, task: TaskContext, history: HistoryContext) -> float: ...
    def estimate_cap(self, task: TaskContext, budget: BudgetContext, history: HistoryContext) -> float: ...
    def choose_backend(self, task: TaskContext, state: WorkflowState, budget: BudgetContext) -> str: ...
    def should_escalate(self, task: TaskContext, state: WorkflowState, history: HistoryContext) -> bool: ...
    def should_stop(self, task: TaskContext, state: WorkflowState, budget: BudgetContext) -> bool: ...
    def learn(self, task: TaskContext, outcome: VerifiedOutcome) -> None: ...
```

SWE-bench supplies one concrete adapter:

```text
TaskContext.features = repo, failing tests, pass-to-pass tests, patch size, task family
Verifier = local harness / official SWE-bench harness
Runtime = mini-SWE-agent
Outcome = resolved, cost, turns, patch source, failure axis
```

An enterprise deployment can supply another adapter:

```text
TaskContext.features = ticket type, customer tier, deadline, codebase area, expected labor saved
Verifier = tests, reviewer approval, document QA, workflow completion check
Runtime = Claude Code, Codex, internal agent, or orchestration platform
Outcome = accepted work, cost, latency, retries, human intervention
```

## Product Shape

BudgetFlow should become a governance layer above existing agent runtimes such as Claude Code, Codex, mini-SWE-agent, or future enterprise agent systems.

A user, team, project, or organization owns a budget account. Tasks arrive over time. For each task, BudgetFlow decides:

- what value the task appears to have;
- what budget cap the task deserves;
- which model tier to start with;
- when to escalate to a stronger model;
- when to continue, stop, or retry;
- how to learn from the verified outcome.

The product interface should be task-oriented rather than role-oriented. A programmer, analyst, researcher, or operations user can all submit work. The system allocates budget based on task value, difficulty, progress, and historical evidence.

The budget pool should be shared by default. For example, an organization may allocate one quarterly AI budget across three teams while temporarily prioritizing a World Model team. BudgetFlow should accept that directional priority through a simple API, but it should not blindly give every World Model task a premium model. Some tasks in a high-priority team are token-intensive but not intelligence-intensive. Some tasks in a lower-priority team are urgent and high-value. The system should decide at the task level which work deserves scarce model budget.

## Core Claim

BudgetFlow studies online budget-aware routing for multi-step agent tasks.

SWE-bench is the controlled evaluation proxy: it gives repeatable tasks, clear pass/fail signals, and clean cost accounting. The real product setting is continuous enterprise agent work under shared budgets, quota limits, and model cost constraints.

BudgetFlow now uses a two-level claim ladder.

| Claim | Meaning | Status |
|---|---|---|
| First claim / North Star | Value-driven token efficiency: under a shared hard budget, complete the highest verified task value per dollar. | Primary paper direction. |
| Second claim / mechanism | Workflow-stage and progress-aware routing can also beat dummy, budget-only, or market routing policies on per-step/per-task cost efficiency. | Still valuable, but must be empirically verified rather than assumed. |

Evidence discipline:

- A Tier 1 result requires non-equal task values from an explicit value source. If a run falls back to `value_i=1`, it can only support Tier 2 or instrumentation claims.
- A Tier 2 result can be shown with equal values, but it should be reported as routing/cost evidence rather than value-allocation evidence.
- Task value is a proxy. The current cold-start direction is model success rarity / solve rarity: tasks solved by fewer capable models or policies receive higher value. The long-term system should learn value, difficulty, model success probability, progress quality, and cost online from verified outcomes.

The second claim should not be used as the only foundation of the paper. It has real downsides, including tier-switching overhead and possible KV / prefix-cache loss. If experiments show that the stage/progress formula does not beat simpler routing, BudgetFlow should still be framed as a value-aware shared budget governor that can plug in a better allocator or learned policy. If both claims hold, the paper becomes stronger: BudgetFlow improves value allocation at the portfolio level and cost efficiency inside individual workflows.

Paper objective:

```text
maximize resolved value per dollar under a hard budget
```

Product objective:

```text
maximize sum(value(task) * success(task)) under budget, quota, and latency constraints
```

Equivalently:

```text
maximize sum(value(task) * resolved(task) - cost(task) - latency_penalty(task))
```

The early controlled experiments may set `value(task)=1` to isolate harness trust, budget enforcement, and routing mechanics. That is a simplifying assumption, not the long-term claim. The stronger paper direction is value-cost efficiency: how much verified task value the system creates per dollar under a shared hard budget.

For product use, value can come from priority, deadline, repo importance, customer tier, expected labor saved, strategic direction, or user-provided business impact. If users do not provide explicit values, BudgetFlow should estimate them from task features and history.

For paper writing, SWE-bench must be defended as a proxy rather than the product itself. Generality matters more than overfitting a single benchmark. The benchmark supplies reproducible tasks and verifiers; the system abstraction is a pluggable `TaskContext`, `BudgetContext`, `HistoryContext`, runtime adapter, and verifier. Enterprise deployments can replace the value source and verifier without replacing the budget-governance layer.

## Value Model

Task value is hard to measure across organizations. BudgetFlow should support two operating modes.

| Mode | Source of Value | Role |
|---|---|---|
| Cold start | User-provided priority, SLA, customer tier, project direction, heuristic difficulty/value proxies | Start making reasonable allocation decisions without a trained model. |
| Warm up | Verified outcomes, observed cost, model success, cap sufficiency, human feedback, realized business signals | Learn task value, difficulty, success probability, and marginal model benefit over time. |

Cold start should be easy for enterprises. They should be able to submit a batch of tasks and optional value hints through a small API rather than maintain a precise value table for every task. Hints can be ordinal or directional: "this project is strategically favored this quarter", "customer-tier tasks matter more", "deadline-critical tasks should receive higher willingness to spend".

Warm up should make the system smarter without hard-coding every task. BudgetFlow should learn:

- expected value by task type, project, customer tier, and deadline;
- task difficulty and likely cost distribution;
- model success probability by task family and stage;
- cap sufficiency and underbudget risk;
- whether escalation or rescue changed the verified outcome;
- which high-cost tasks were worth their spend and which were not.

The policy should optimize expected marginal value:

```text
route_score = expected_value_gain(task, action) / expected_marginal_cost(action)
```

This makes BudgetMemory a value-learning component, not only a cost memory. Its job is to estimate cost, success, cap sufficiency, and value signals from verified outcomes so BudgetFlow can maximize value per dollar.

## Budget Account Model

BudgetFlow should support budget windows rather than only static batches.

| Budget Window | Meaning |
|---|---|
| Task budget | Maximum spend for one workflow. |
| User budget | Personal or seat-level allowance. |
| Team budget | Shared team pool across many users. |
| Project budget | Budget tied to repo, product area, or research thread. |
| Organization budget | Global quota and cost control. |
| Time window | Daily, weekly, monthly, or campaign-level budget. |

A batch experiment is just a compressed version of a time-window budget: instead of tasks arriving across a week, they arrive together in a reproducible benchmark run.

Batching is central to the product shape. In an organization, service demand over a time window is often stable enough to evaluate as a pool: many people and teams submit work, the system sees the batch or stream, and a shared governor allocates budget dynamically. Teams can be added or removed without re-cutting fixed quotas. Strategic priorities steer the allocation, but individual task value and expected payoff decide the spend.

## Routing Model

BudgetFlow is a router with memory and budget state.

| Input | Purpose |
|---|---|
| Task features | Estimate difficulty and likely cost. |
| Stage | Localization, repair, validation, or finalization. |
| Budget remaining | Decide how aggressive the next step can be. |
| Task value | Decide whether expensive escalation is justified. |
| Progress signal | Detect whether the agent is learning, editing, testing, or stuck. |
| Historical memory | Reuse prior cost and success evidence. |
| Backend availability | Handle provider outage, rate limit, or degraded model tiers. |

Core actions:

| Action | Meaning |
|---|---|
| Start cheap | Try a lower-cost model when historical evidence says it is likely enough. |
| Start strong | Use a strong model immediately for high-value or historically hard tasks. |
| Escalate | Move to a stronger model when progress stalls or task value justifies it. |
| De-escalate | Return to cheaper models for mechanical steps after strong-model insight. |
| Stop | Avoid wasting budget when evidence suggests low success probability. |
| Resume | Continue safely after crashes, interruptions, or external kills. |

Stage-aware routing is one mechanism, not the whole contribution. Localization, repair, and validation can provide useful progress signals, but the larger claim is value-driven budget allocation under a shared hard budget. If a better runtime or learned policy replaces hand-coded stages, the BudgetFlow account, value model, memory, and verifier interfaces should still apply.

## Continuous Learning Path

Rules are the cold-start policy. Memory is the warm-start policy. A learned router is the long-term direction.

| Version | Mechanism | Role |
|---|---|---|
| v1 Rule-based | Stage weights, pressure, cap, rescue, stop-loss | Explainable baseline and paper-friendly control. |
| v2 Continuous memory | Learn cost, value, difficulty, cap, success, failure axis from verified runs | Improve automatic budgeting, value estimates, and escalation thresholds. |
| v3 Learned router | Supervised model or contextual bandit | Predict value, start tier, cap, escalate/stop from task and history. |

Training signal should come from verified outcomes, not self-reported agent success.

Useful logged fields:

- task id, repo, patch size, failing tests, pass-to-pass tests;
- task value hint, priority source, deadline, project/team context;
- model tier sequence;
- prompt/completion tokens and real USD cost;
- stage sequence and progress markers;
- patch source and edited files;
- harness result and failure axis;
- whether cap was sufficient;
- whether escalation helped.

Possible reward:

```text
reward = value(task) * resolved - lambda_cost * spend - lambda_time * latency
```

The strongest learning signal remains verified outcome. User value hints are inputs, not truth. The system should calibrate them against accepted work, downstream feedback, repeated task patterns, and observed difficulty.

## Evaluation Strategy

The evaluation must separate mechanism, cost, and correctness.

| Layer | Question |
|---|---|
| Harness trust | Is PASS a real PASS and FAIL a real FAIL? |
| Ceiling control | What can the strongest model solve uncapped? |
| Budget-only baseline | What happens with cheap models under cap but no progress-aware routing? |
| Value-only allocator | What happens if task value changes caps but routing is static? |
| BudgetFlow full | Does value-aware allocation and routing improve resolved-value-per-dollar under fixed budget? |
| Stability audit | Are results stable across repeats? |
| Official audit | Do local-harness conclusions hold under official SWE-bench harness? |

Current local harness is the inner loop. Official SWE-bench Docker harness should be used later as an outer audit on a Docker-capable machine.

## System Modules

| Module | Responsibility |
|---|---|
| Budget Governor | Enforce hard cap, soft cap, reservation, settlement, and shared budget accounting. |
| Value Estimator | Estimate task value from injected hints, heuristics, and learned historical evidence. |
| Automatic Budgeting | Estimate task cap from value, history, task features, model costs, and prior outcomes. |
| Adaptive Routing | Select model tier per stage and escalate/de-escalate from progress and pressure. |
| Observability | Persist JSONL, turn traces, cost, backend mix, patch source, and failure axis. |
| Harness Adapter | Verify patches with fail-before, fail-after, and pass-to-pass evidence. |
| Memory Store | Learn task value, cost, difficulty, cap sufficiency, success rate, and routing outcomes over time. |

## Enterprise Value

BudgetFlow should remove rigid per-person quota management.

Instead of assigning fixed model budgets by role, the system allocates spend by task value and expected payoff. A low-value task can be constrained even if submitted by a senior user. A high-value task can receive stronger models even if submitted by someone whose personal quota would otherwise be exhausted.

This gives the organization:

- shared budget control;
- value-driven allocation instead of identity-driven quota;
- fewer manual quota exceptions;
- model spend tied to business value;
- automatic escalation only when justified;
- auditable cost and outcome records;
- continuous improvement from prior tasks.

The product promise is not that a more senior or more technical user receives better models. The promise is that higher-value work receives the model budget it deserves, regardless of who submitted it. This avoids awkward quota lending between teammates and avoids blaming individuals for token spend when the real question is whether the task deserved the spend.

## Parallel Execution Model

BudgetFlow distinguishes policy-level parallelism from task-level sequencing.

| Level | Execution Rule | Reason |
|---|---|---|
| Inside one policy | Sequential by default | A policy shares budget state, memory updates, and batch/window accounting. |
| Across policies | Parallel when resources allow | Policies use isolated worktrees and independent budget governors. |
| Across unrelated budget accounts | Parallel when resources allow | Separate accounts do not share budget state. |
| Across retries of the same task | Controlled parallelism only | Multiple attempts can pollute cost accounting unless explicitly modeled. |

Current experiment meaning:

```text
5 policies x 5 tasks with --jobs 5
= policies progress concurrently
= each policy walks its task list sequentially
```

A future runner should make this explicit:

```python
run_experiment(
    tasks=task_pool,
    policies=[all_pro, budget_only, budgetflow_full],
    policy_parallelism=3,
    task_parallelism_per_policy=1,
    budget_scope="per_policy_window",
)
```

## Infrastructure Strategy

On the current HPC container, `/Lishun` is persistent NFS and `/tmp` is faster local scratch. The best strategy is controlled parallelism, not maximum parallelism.

| Resource | Preferred Use |
|---|---|
| `/tmp` | temporary build files, pytest temp, scratch, short-lived work. |
| `/Lishun` | JSONL, checkpoints, reports, final audit artifacts. |
| NFS worktrees | limited parallelism with strong cleanup and checkpointing. |
| API providers | bounded concurrency to avoid rate-limit noise. |
| Harness eval | parallel only after worktree cleanup is stable. |

Practical rule:

```text
policy_parallelism = 3 to 5 for compare runs
stability audit parallelism = 2 to 3 unless the runner has resume and per-task checkpointing
large matrix = staged batches with consistency checks between batches
```

For the current environment, more parallelism helps only when it does not amplify NFS worktree churn, pip editable installs, API latency, or checkpoint inconsistency. A slow serial audit should be rewritten with explicit worker-level checkpointing before being scaled.

## Near-Term Engineering Direction

1. Stabilize all_pro repeat audits before calling tasks ceiling failures.
2. Fix budget-only T3 reachability so baselines are semantically valid.
3. Clean exit reasons so successful worktree patch evaluation is not called stop-loss failure.
4. Keep turn traces on by default and keep summary logs compact.
5. Use 5x5 or 7x3 repeat runs for diagnosis before scaling to 10x5 or larger.
6. Expand task pool only with gold-PASS tasks and clear harness evidence.
7. Treat official SWE-bench harness as final audit, not current inner-loop blocker.

## Paper Positioning

BudgetFlow's contribution is budget governance for agent workflows:

- hard budget control across multi-step tasks;
- shared budget pools across users, teams, projects, and time windows;
- value-aware allocation under hard budget constraints;
- progress-aware model routing;
- automatic cap estimation from history;
- cold-start value injection and warm-start value learning;
- verified outcome learning;
- failure attribution for cost, model, routing, and harness errors.

The strongest paper claim should be about clean resolved-value-per-dollar under budget, with transparent controls against all-pro, budget-only, and value-agnostic baselines.

# BudgetFlow North Star

## Vision

BudgetFlow is a budget-aware online router for multi-step agent workflows.

It manages model choice, task budget, escalation, and stop decisions under a shared budget account. The target is to complete more valuable verified tasks per dollar, not simply to minimize tokens for a single request.

## Generality Beyond SWE-bench

The current implementation uses SWE-bench because it gives reproducible tasks, executable verification, and clean pass/fail evidence. The framework is designed around pluggable task context, budget context, history, and verifier interfaces, so the same router can be applied to other enterprise agent workflows.

BudgetFlow's generic unit is not a SWE-bench issue. The generic unit is a `TaskContext`: a piece of work with value, difficulty signals, budget constraints, runtime state, and a verifier.

Different organizations should be able to inject their own context:

| Enterprise Input | BudgetFlow Use |
|---|---|
| Task priority | Convert business value into budget willingness. |
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
    escalation_priors: dict[str, float]

class BudgetFlowPolicy:
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

- what budget cap the task deserves;
- which model tier to start with;
- when to escalate to a stronger model;
- when to continue, stop, or retry;
- how to learn from the verified outcome.

The product interface should be task-oriented rather than role-oriented. A programmer, analyst, researcher, or operations user can all submit work. The system allocates budget based on task value, difficulty, progress, and historical evidence.

## Core Claim

BudgetFlow studies online budget-aware routing for multi-step agent tasks.

SWE-bench is the controlled evaluation proxy: it gives repeatable tasks, clear pass/fail signals, and clean cost accounting. The real product setting is continuous enterprise agent work under shared budgets, quota limits, and model cost constraints.

Paper objective:

```text
maximize resolved tasks per dollar under a hard budget
```

Product objective:

```text
maximize sum(value(task) * success(task)) under budget, quota, and latency constraints
```

For the paper, `value(task)=1` is acceptable. For product use, value can come from priority, deadline, repo importance, customer tier, expected labor saved, or user-provided business impact.

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

## Continuous Learning Path

Rules are the cold-start policy. Memory is the warm-start policy. A learned router is the long-term direction.

| Version | Mechanism | Role |
|---|---|---|
| v1 Rule-based | Stage weights, pressure, cap, rescue, stop-loss | Explainable baseline and paper-friendly control. |
| v2 Continuous memory | Learn cost, cap, success, failure axis from verified runs | Improve automatic budgeting and escalation thresholds. |
| v3 Learned router | Supervised model or contextual bandit | Predict start tier, cap, escalate/stop from task and history. |

Training signal should come from verified outcomes, not self-reported agent success.

Useful logged fields:

- task id, repo, patch size, failing tests, pass-to-pass tests;
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

## Evaluation Strategy

The evaluation must separate mechanism, cost, and correctness.

| Layer | Question |
|---|---|
| Harness trust | Is PASS a real PASS and FAIL a real FAIL? |
| Ceiling control | What can the strongest model solve uncapped? |
| Budget-only baseline | What happens with cheap models under cap but no progress-aware routing? |
| BudgetFlow full | Does routing improve resolved-per-dollar under fixed budget? |
| Stability audit | Are results stable across repeats? |
| Official audit | Do local-harness conclusions hold under official SWE-bench harness? |

Current local harness is the inner loop. Official SWE-bench Docker harness should be used later as an outer audit on a Docker-capable machine.

## System Modules

| Module | Responsibility |
|---|---|
| Budget Governor | Enforce hard cap, soft cap, reservation, settlement, and shared budget accounting. |
| Automatic Budgeting | Estimate task cap from history, task features, model costs, and prior outcomes. |
| Adaptive Routing | Select model tier per stage and escalate/de-escalate from progress and pressure. |
| Observability | Persist JSONL, turn traces, cost, backend mix, patch source, and failure axis. |
| Harness Adapter | Verify patches with fail-before, fail-after, and pass-to-pass evidence. |
| Memory Store | Learn task cost, cap sufficiency, success rate, and routing outcomes over time. |

## Enterprise Value

BudgetFlow should remove rigid per-person quota management.

Instead of assigning fixed model budgets by role, the system allocates spend by task value and expected payoff. A low-value task can be constrained even if submitted by a senior user. A high-value task can receive stronger models even if submitted by someone whose personal quota would otherwise be exhausted.

This gives the organization:

- shared budget control;
- fewer manual quota exceptions;
- model spend tied to business value;
- automatic escalation only when justified;
- auditable cost and outcome records;
- continuous improvement from prior tasks.

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
| `/Lishun` | JSONL, checkpoints, reports, final traces, persistent repo cache. |
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
- progress-aware model routing;
- automatic cap estimation from history;
- verified outcome learning;
- failure attribution for cost, model, routing, and harness errors.

The strongest paper claim should be about clean resolved-per-dollar under budget, with transparent ablations against all-pro and budget-only baselines.

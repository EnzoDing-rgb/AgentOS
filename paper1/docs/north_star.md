# BudgetFlow North Star

## Terminology

This section is the project vocabulary source. New docs, prompts, handoffs, code
comments, and reports should use these names.

| Term | Meaning |
|---|---|
| BudgetFlow | Value-aware budget governance for multi-step agent workflows under shared hard budgets. |
| Tier 1 / T1 | Primary claim: maximize Yield under the same shared hard budget. |
| Yield | Total resolved task value within a shared budget window. It is not raw task count. |
| Yield per Dollar | Total resolved task value divided by model spend. It is the main efficiency diagnostic. |
| Tier 2 / T2 | Mechanism claim: compare policy and routing efficiency against task-level, static, and budget-only controls. |
| Value-Driven Budget Allocation | Allocation of task caps and spend from task value, history, expected payoff, cost, and budget pressure. |
| ValueSource | Versioned input that defines or estimates task value for one run or deployment. |
| CostSource | Versioned input that defines or estimates model cost for one run or deployment. |
| ValueAdapter | Adapter that turns task descriptions, organization hints, accepted outcomes, human overrides, or business systems into a standard task-value signal. |
| CostAdapter | Adapter that turns public price catalogs, provider estimates, invoices, enterprise rate cards, or manual overrides into a standard cost signal. |
| Confidence | A short record of where a value or cost estimate came from and how trustworthy it is. |
| Policy Backend | Pluggable strategy that recommends cap, model tier, escalation, de-escalation, stop, and continue decisions. |
| Bootstrap Policy | Default explainable policy that runs without customer history or machine learning. It uses general budget, cost, progress, value, escalation, and stop-loss rules. |
| Learn Policy | Policy backend that uses Cost Memory, Routing Memory, Escalation Memory, statistical learning, or customer-owned machine learning to improve future decisions. |
| Fixed Baseline Policy | Experimental control policy such as static routing or budget-only routing. It is for evaluation, not the customer-facing policy family. |
| Task Set | A named group of tasks used for evaluation, such as Familiar Tasks or Unseen Tasks. |
| Workflow Segment | Coarse work state used as a policy signal. Default segments are Context, Action, and Verification. |
| Segment-Aware Routing | Routing that can use workflow segment as a feature. It does not force model switching. |
| Task-Level Policy | Control policy that chooses a backend at task/request level and preserves cache/context continuity. |
| Cost Memory | Memory for cost, cap sufficiency, task value, and Yield per Dollar evidence. |
| Routing Memory | Memory for backend choices, segment outcomes, failure axes, and route effectiveness. |
| Escalation Memory | Memory for whether expensive model-tier turns were productive. |
| Value-Triggered Escalation | Bounded use of a stronger model tier for high-value tasks when the expected marginal value justifies it. |
| Strongest Model | The strongest configured model tier. It is one model-tier option, not the center of the system claim. |
| Infra | Runtime, provider, parser, harness, filesystem, worktree, and environment health. |

Use the terms in this table for current prose. Do not preserve retired names,
unclear research jargon, or old metric abbreviations in active code, docs,
tests, prompts, or handoffs.

## What BudgetFlow Is

BudgetFlow is a governance layer above agent runtimes such as Codex, Claude
Code, mini-SWE-agent, or internal enterprise workflows. It owns shared budget
accounts, task value, policy decisions, verified outcomes, memory, and audit.

The product goal is simple: every dollar of model spend should create more
verified task value. BudgetFlow allocates spend by task value, expected payoff,
difficulty, progress, and budget pressure instead of by fixed per-person quotas.

The paper studies online, value-aware budget governance for multi-step agent
tasks. SWE-bench is the current controlled evaluation adapter because it
provides repeatable tasks and verifiers. The system boundary is broader:
enterprise deployments can replace the task adapter, ValueSource, CostSource, runtime, and
verifier while keeping the BudgetFlow core.

## Core Architecture

BudgetFlow separates core mechanisms, domain adapters, policy backends, memory,
and observability. The core must not depend on SWE-bench, a specific verifier,
or a specific learning method.

| Layer | Responsibility |
|---|---|
| Core Mechanism | Hard budget ledger, reservation, settlement, verifier-grounded outcome, trace/audit/replay, stop-loss primitives, and same-budget policy comparison. |
| Domain Adapters | Task, segment, verifier, value, cost, model-tier, progress-signal, and runtime mappings for one benchmark or enterprise workflow. |
| Policy Backend | Cap recommendations, backend routing, escalation, de-escalation, stop/continue, and learned or heuristic priors. |
| Memory | Cost Memory, Routing Memory, and Escalation Memory. These are optional inputs for Learn Policy and audit, not hidden core behavior. |
| Observability | Minimal decision records, JSONL schema, turn traces, checker, compact audit, failure attribution, and reports. |

SWE-bench-specific concepts such as localization, repair, validation,
fail-to-pass tests, pass-to-pass tests, patch extraction, and worktree diffs
belong behind adapters. They can power benchmark experiments; they do not define
BudgetFlow core or the default Bootstrap Policy.

## Conceptual Interfaces

```python
@dataclass
class TaskContext:
    task_id: str
    task_type: str
    description: str
    features: dict[str, float | str | bool]
    verifier: Verifier
    runtime: AgentRuntime

@dataclass
class ValueContext:
    task: TaskContext
    hints: dict[str, float | str | bool]
    history: HistoryContext
    confidence: dict[str, float | str | bool]

class ValueAdapter:
    def estimate(self, value_context: ValueContext) -> ValueEstimate: ...
    def learn(self, value_context: ValueContext, outcome: VerifiedOutcome) -> None: ...

class CostAdapter:
    def estimate(self, backend: str, state: WorkflowState, budget: BudgetContext) -> CostEstimate: ...
    def settle(self, estimate: CostEstimate, actual: CostActual | None) -> CostRecord: ...

@dataclass
class BudgetContext:
    account_id: str
    window: str  # task, day, week, project, organization
    remaining_usd: float
    hard_cap_usd: float
    soft_cap_usd: float | None
    allowed_backends: list[str]

@dataclass
class HistoryContext:
    similar_tasks: list[OutcomeRecord]
    cost_priors: dict[str, float]
    value_priors: dict[str, float]
    routing_priors: dict[str, float]
    escalation_priors: dict[str, float]

@dataclass
class WorkflowSegment:
    name: str  # Context, Action, Verification, or adapter-defined equivalent
    signals: dict[str, float | str | bool]

class PolicyBackend:
    def estimate_cap(self, task: TaskContext, value: ValueEstimate, budget: BudgetContext, history: HistoryContext) -> float: ...
    def choose_backend(
        self,
        task: TaskContext,
        segment: WorkflowSegment,
        state: WorkflowState,
        budget: BudgetContext,
    ) -> str: ...
    def should_escalate(self, task: TaskContext, state: WorkflowState, history: HistoryContext) -> bool: ...
    def should_stop(self, task: TaskContext, state: WorkflowState, budget: BudgetContext) -> bool: ...
    def learn(self, task: TaskContext, outcome: VerifiedOutcome) -> None: ...
```

The default policy backend is the Bootstrap Policy. Enterprises can use it
as-is or replace it with a Learn Policy. Customers do not need a learned policy
to get value from BudgetFlow, but Learn Policy is the main place for Memory or
customer-owned machine learning.

## Workflow Segments

BudgetFlow uses three default workflow segments.

| Segment | Meaning |
|---|---|
| Context | Gather information, inspect state, retrieve evidence, and form a working hypothesis. |
| Action | Make an intervention: edit, write, call a tool, draft, execute, or otherwise change the task state. |
| Verification | Check whether the intervention worked and decide whether to stop, retry, escalate, or de-escalate. |

This absorbs the useful loop intuition from ReAct-style systems while staying
coarse enough for budget decisions. Reasoning, observation, and tool actions
are runtime behaviors. Context, Action, and Verification are policy signals.

Segment-aware routing means the policy can use segment as a feature. It does
not mean the system must switch models between segments. A policy may keep one
model for the whole task to preserve KV cache, prefix reuse, context continuity,
and low coordination overhead. Switching models or using subagents is justified
when expected value gain exceeds marginal cost, including cache loss, prompt
drift, and handoff risk.

Enterprise adapters can map their own phases onto these segments. Examples:
triage/action/review, retrieval/drafting/checking, or analysis/execution/QA.

## Claims And Metrics

BudgetFlow has a two-level claim ladder.

| Claim | Meaning | Main Evidence |
|---|---|---|
| T1: Value-Driven Budget Allocation | Under one shared hard budget, BudgetFlow resolves the highest total task value. | Yield at fixed budget, plus Yield per Dollar. |
| T2: Policy/routing mechanism | Policy backends use budget, progress, segment, value, cost, and model-tier signals productively. | Verified resolution-cost frontier, model-tier use diagnostics, and segment-aware vs task-level deltas. |

T1 is the compass. T2 explains mechanisms inside T1. Routing savings are useful
when they preserve or improve value-weighted outcomes.

Primary T1 metric:

```text
Yield = total resolved task value
```

Secondary T1 diagnostic:

```text
Yield per Dollar = total resolved task value / total model spend
```

Resolved task count may be reported as a supporting diagnostic, but it is not
the BudgetFlow objective. Task count per dollar is not a core metric because
tasks differ in value, difficulty, and model solvability.

T2 diagnostics:

- verified resolved count and cost at a fixed budget;
- pass/value delta against task-level, static, and budget-only controls;
- model-tier productive rate;
- model-tier no-progress spend;
- model-tier source breakdown: starter memory, evidence-triggered, value-triggered, or regular routing;
- no-patch rate;
- segment-aware versus task-level delta.

## Policy Families

| Policy | Role |
|---|---|
| Bootstrap Policy | Customer-facing default policy. It should contain general, explainable budget-control rules, not benchmark-tuned experience. |
| Learn Policy | Customer-facing learned policy. It can use built-in Memory or a customer-owned machine learning system behind the same Policy Backend interface. |
| Fixed Baseline Policy | Evaluation-only control policy such as static routing, all-cheap, all-strong, task-level routing, or budget-only routing. |

The task-level control is mandatory when evaluating segment-aware routing. It
tests whether segment features help, or whether they add switching noise,
prompt drift, cache loss, and coordination cost.

Bootstrap Policy is the default customer-facing policy. It uses general,
explainable budget-control rules. Learn Policy uses current trusted Memory
views, adapter configuration, or customer-owned learning systems behind the
same Policy Backend interface.

## Value Model

Task value is a proxy. BudgetFlow does not hard-code what value means. A
ValueAdapter can use a default heuristic, a human-authored value matrix, natural
language policy translated by an adapter, benchmark metadata, or an enterprise
data import. A Learn Policy can improve future value and budget decisions from
outcomes, accepted work, repeated priority patterns, human correction, or
external systems when those signals are available.

`ValueContext` is a standard input wrapper, not a fixed enterprise schema.
Fields such as project, customer, SLA, risk, revenue impact, research priority,
or content priority may be useful in an enterprise adapter, but BudgetFlow core
only consumes a normalized task-value estimate plus confidence.

Cost follows the same rule. Default experiments should anchor cost to a
versioned public price catalog. Enterprise deployments can replace or calibrate
that with provider estimates, invoices, internal rate cards, or manual
overrides. BudgetFlow core consumes a normalized cost estimate plus confidence.

The policy should optimize expected marginal value:

```text
route_score = expected_value_gain(task, action) / expected_marginal_cost(action)
```

Verified outcome is the strongest correctness signal. It should improve
difficulty, success-probability, cap-sufficiency, and marginal-model-benefit
estimates. It may also help calibrate task value when value feedback is
available, but the system must not treat "easy to solve" as the same thing as
"high value."

Learning belongs behind Policy Backend and Memory interfaces. Bootstrap Policy
may use configuration and simple priors, but Cost Memory, Routing Memory, and
Escalation Memory are primarily inputs for Learn Policy or audit. Customers may
use BudgetFlow's built-in Learn Policy or replace it with their own machine
learning system if it produces the same policy decisions and audit fields.

## Evaluation Discipline

Every compared policy uses the same Task Set, resolver, budget, value source,
model-tier catalog, and run shape. Paid runs use decision-time value estimates
and pre-registered command lines. Small paid runs are diagnostics, not
paper-level evidence.

The main experiment should report both Familiar Tasks and Unseen Tasks. Familiar
Tasks protect against harness contamination and environment failures. Unseen
Tasks test whether the policy generalizes beyond the tasks used during
development. The same policies, budget rules, cost source, value source, and
resolver apply to both Task Sets.

Policy observability should be minimal and stable. Each decision record should
make it possible to answer: what went in, what the policy decided, what it cost,
whether the task resolved, what value was resolved, and what failed if it did
not. This is required for debugging, learning, and paper evidence.

After every experiment, inspect artifacts before drawing conclusions:

- T1 Yield and Yield per Dollar;
- T2 resolution-cost frontier;
- model-tier productive rate;
- model-tier no-progress spend;
- model-tier source breakdown;
- no-patch rate;
- segment-aware versus task-level delta;
- checker output and harness trust;
- Cost Memory, Routing Memory, and Escalation Memory confidence;
- infra health: provider, parser, runtime root, worktrees, NFS, checker, budget mode, ValueSource, and CostSource.

Runtime, docs, prompts, and reports should use the terminology in this file.

## Engineering Direction

The codebase should make the architecture visible:

- BudgetFlow core owns budget accounting, memory contracts, verified outcomes,
  trace/audit/replay, and policy comparison.
- Policy backends own routing and stop/continue recommendations.
- Domain adapters own SWE-bench or enterprise-specific task, segment, verifier,
  value, cost, progress, and runtime mapping.
- Memory belongs behind Learn Policy or audit interfaces. BudgetFlow core should
  not hide learning behavior.
- Observability should converge on a compact policy decision record rather than
  scattered benchmark-specific trace fields.
- Entry points such as `run_mini_swe_compare.py` and
  `check_run_observability.py` stay thin.
- Tests protect current evidence quality and architecture boundaries. Tests
  that only preserve stale terminology, retired paths, or old aliases should be
  deleted or rewritten.

The next implementation direction is to finish decoupling Bootstrap Policy,
Learn Policy, Memory, adapters, and minimal decision records. Experiment reports
should then compute Yield and Yield per Dollar by Task Set before any larger
paid run.

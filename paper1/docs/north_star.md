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
| Tier 2 / T2 | Mechanism claim: compare policy and routing efficiency after Tier 1 is credible. |
| Value-Driven Budget Allocation | Allocation of task caps and spend from task value, history, expected payoff, cost, and budget pressure. |
| ValueSource | Versioned input that defines or estimates task value for one run or deployment. |
| CostSource | Versioned input that defines or estimates model cost for one run or deployment. |
| TaskAdapter | Adapter that turns external work into standard BudgetFlow task inputs, including task identity, description, features, difficulty/value hints, and value-source metadata. |
| BudgetAdapter | Adapter that turns customer or experiment budget input into a standard budget input: budget window, hard/soft cap, shared scope, allowed model pool, source, and confidence. |
| ProgressAdapter | Adapter that turns process evidence and final acceptance into standard progress/outcome signals. Intermediate progress can be unknown; final acceptance defines resolved. |
| CostAdapter | Adapter that turns public price catalogs, provider estimates, invoices, enterprise rate cards, or manual overrides into a standard cost signal. |
| Confidence | A short record of where a value or cost estimate came from and how trustworthy it is. |
| Policy Backend | Pluggable strategy that recommends cap, model tier, escalation, de-escalation, stop, and continue decisions. |
| Bootstrap Policy | Default explainable policy that runs without customer history or machine learning. It uses general budget, cost, progress, value, escalation, and stop-loss rules. |
| Learn Policy | Policy backend that uses Cost Memory, Routing Memory, Escalation Memory, statistical learning, or customer-owned machine learning to improve future decisions. |
| Learn Policy Inputs | The three optional input views for Learn Policy: Cost Memory, Routing Memory, and Escalation Memory. |
| Fixed Baseline Policy | Experimental control policy such as static routing or budget-only routing. It is for evaluation, not the customer-facing policy family. |
| Task Set | A named group of tasks used for evaluation, such as Familiar Tasks or Unseen Tasks. |
| Workflow Segment | Coarse work state used as a policy signal. Default segments are Context, Action, and Verification. |
| Segment-Aware Routing | Routing that can use workflow segment as a feature. It does not force model switching. |
| Task-Level Policy | Control policy that chooses a backend at task/request level and preserves cache/context continuity. |
| Frozen Enterprise Router | Pre-registered task/workflow-level router baseline. It uses metadata and value/difficulty buckets once before execution; it does not use runtime progress, shared-budget reallocation, or learning. |
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
enterprise deployments can replace TaskAdapter, BudgetAdapter,
CostAdapter, and ProgressAdapter while keeping the BudgetFlow Mechanism.

## BudgetFlow Mechanism

BudgetFlow separates the mechanism layer, domain adapters, policy backends,
Learn Policy Inputs, and observability. The BudgetFlow Mechanism must not
depend on SWE-bench, a specific verifier, or a specific learning method.

| Layer | Responsibility |
|---|---|
| BudgetFlow Mechanism | Hard budget ledger, reservation, settlement, verifier-grounded outcome, trace/audit/replay, stop-loss primitives, and same-budget policy comparison. |
| Domain Adapters | Task, workflow segment, progress/outcome, and cost mappings for one benchmark or enterprise workflow. |
| Policy Backend | Cap recommendations, backend routing, escalation, de-escalation, stop/continue, and learned or heuristic priors. |
| Learn Policy Inputs | Cost Memory, Routing Memory, and Escalation Memory. These are optional inputs for Learn Policy and audit, not hidden mechanism behavior. |
| Observability | Minimal decision records, JSONL schema, turn traces, checker, compact audit, failure attribution, and reports. |

SWE-bench-specific concepts such as localization, repair, validation,
fail-to-pass tests, pass-to-pass tests, patch extraction, and worktree diffs
belong behind adapters. They can power benchmark experiments; they do not define
BudgetFlow Mechanism or the default Bootstrap Policy.

Adapter boundaries should be useful even when the user provides very little.
TaskAdapter and BudgetAdapter are the mandatory deployment inputs: BudgetFlow
must know what work is being attempted and what budget window constrains it.
CostAdapter and ProgressAdapter may start with conservative defaults or unknown signals, as long as those defaults are
auditable. More customer metadata improves routing quality, but missing metadata
should not make the system unusable.

SWE-bench is the pressure test for this design. If an interface makes SWE-bench
adaptation awkward, it is probably over-abstracted or placed at the wrong
boundary. If an interface only works for SWE-bench, benchmark detail has leaked
into the mechanism.

## Conceptual Interfaces

```python
@dataclass
class TaskContext:
    task_id: str
    task_type: str
    description: str
    features: dict[str, float | str | bool]
    value: ValueEstimate
    value_source: ValueSourceInfo

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

@dataclass
class ProgressSignal:
    segment: WorkflowSegment
    has_progress: bool | None  # None means unknown/no reliable signal
    reason: str
    confidence: str

class CostAdapter:
    def estimate(self, backend: str, state: WorkflowState, budget: dict) -> CostEstimate: ...
    def settle(self, estimate: CostEstimate, actual: CostActual | None) -> CostRecord: ...

class PolicyBackend:
    def estimate_cap(self, task: TaskContext, value: ValueEstimate, budget_input: dict, history: HistoryContext) -> float: ...
    def choose_backend(
        self,
        task: TaskContext,
        segment: WorkflowSegment,
        state: WorkflowState,
        budget_input: dict,
    ) -> str: ...
    def should_escalate(self, task: TaskContext, state: WorkflowState, history: HistoryContext) -> bool: ...
    def should_stop(self, task: TaskContext, state: WorkflowState, budget_input: dict) -> bool: ...
    def learn(self, task: TaskContext, outcome: VerifiedOutcome) -> None: ...
```

The default policy backend is the Bootstrap Policy. Enterprises can use it
as-is. As current-schema trusted records accumulate, the same interface can feed
Learn Policy Inputs without asking the user to manually switch modes. Customers
do not need a learned policy to get value from BudgetFlow, but the system should
naturally become more accurate when Memory or customer-owned machine learning is
available.

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

Progress is not a demand for human step-by-step scoring. For SWE-bench, command
patterns, touched files, patch extraction, and verifier output provide useful
progress/outcome evidence. For enterprise tasks without reliable intermediate
signals, ProgressAdapter should record unknown or no-signal and rely on final
acceptance for resolved outcome. Unknown progress must not be converted into
fake no-progress evidence that pollutes learning.

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
the BudgetFlow objective. Task count per dollar is not a primary metric because
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

The main mechanism experiment isolates BudgetFlow Mechanism from policy quality.
It uses the same task set, same value matrix, same hard budget, and same
SWE-agent harness across three roles:

| Experiment Role | CLI Strategy | Meaning |
|---|---|---|
| Bare Strong Model | `bare_strong_model` | Bare SWE-agent harness with a hard budget kill adapter and the strongest configured model. It represents the expensive "use the strongest model" default. |
| Frozen Enterprise Router | `enterprise_router_baseline` | Bare SWE-agent harness with a pre-registered task/workflow-level router and hard budget kill. It represents a realistic enterprise router without BudgetFlow's shared-budget mechanism. |
| BudgetFlow Mechanism + Same Router | `budgetflow_same_router` | The same frozen router inside BudgetFlow Mechanism: shared ledger, value/cost/progress inputs, stop/escalation primitives, trace/audit, and same-budget accounting. This is the primary mechanism isolation comparison. |

`Bootstrap Policy` is a separate product-default experiment role, not the sole
mechanism proof. It should be evaluated as `budgetflow_bootstrap_policy` after
the mechanism comparison is credible: customer has no history, no ML, and no
enterprise router, but still gets a useful cold-start policy.

Task-level and segment-aware controls remain Tier 2 follow-up experiments. They
answer whether turn/segment-level routing beats one-shot task/workflow routing;
they should not be mixed into the first mechanism proof.

Bootstrap Policy is the cold-start behavior: no customer history and no machine
learning required. As current trusted records accumulate, Learn Policy Inputs
can be consumed behind the same Policy Backend interface. The user-facing story
is continuous improvement, not a manual policy switch.

## Value Model

Task value is a proxy. BudgetFlow does not hard-code what value means.
TaskAdapter can use a default heuristic, a human-authored value matrix, natural
language policy translated by an adapter, benchmark metadata, or an enterprise
data import. A Learn Policy can improve future value and budget decisions from
outcomes, accepted work, repeated priority patterns, human correction, or
external systems when those signals are available.

TaskAdapter output is a standard input wrapper, not a fixed enterprise schema.
Fields such as project, customer, SLA, risk, revenue impact, research priority,
or content priority may be useful in an enterprise adapter, but the BudgetFlow
Mechanism only consumes a normalized task-value estimate plus confidence.

Cost follows the same rule. Default experiments should anchor cost to a
versioned public price catalog. Enterprise deployments can replace or calibrate
that with provider estimates, invoices, internal rate cards, or manual
overrides. The BudgetFlow Mechanism consumes a normalized cost estimate plus confidence.

Observability follows the same boundary. Each adapter should emit enough
current-schema evidence to explain its inputs, defaults, confidence, unknowns,
and final outcome. Do not add a pluggable observability framework until a real
runtime needs it; first keep the active JSONL and compact audit aligned with
TaskAdapter, BudgetAdapter, CostAdapter, ProgressAdapter, Policy Backend, and
Learn Policy Inputs.

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

- BudgetFlow Mechanism owns budget accounting, memory contracts, resolved outcomes,
  trace/audit/replay, and policy comparison.
- Policy backends own routing and stop/continue recommendations.
- Domain adapters own SWE-bench or enterprise-specific task, workflow segment,
  progress/outcome, and cost mapping.
- Memory belongs behind Learn Policy or audit interfaces. BudgetFlow Mechanism should
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

# BudgetFlow: Budget-Governed Runtime Scheduling for LLM Agent Workflows

> **One-liner**: BudgetFlow is a runtime layer for concurrent LLM-agent workflows that enforces hard spend caps, provider RPM limits, and concurrency slots while using workflow-stage signals to schedule scarce high-capability model calls.

---

## 0. What problem does this paper solve?

Today's LLM agents are usually composed of many model calls. Take SWE-bench as an example: a coding agent reads an issue, searches files, reads code, writes a patch, runs tests, and then iterates using failure logs. Each step consumes shared runtime resources: spend budget, model slots, provider RPM quota, and queue capacity. At the same time, steps differ in how much they affect the final trajectory: a wrong directory listing is often recoverable, while a wrong root-cause judgment after a test failure can ruin the repair.

We formalize this as **budget-governed agent execution**:

> **Given many concurrent LLM-agent workflows sharing a global spend cap, model pool, provider quotas, and concurrency slots, how should a runtime admit, queue, downgrade, upgrade, switch, or cancel calls while preserving hard limits and completing more verifiable tasks?**

This problem has three key ingredients:

1. **Hard runtime limits**: the total spend cap, provider RPM limits, and concurrency slots are given up front, and the runtime must enforce them during execution.
2. **Workflow-stage heterogeneity**: directory browsing, code understanding, traceback analysis, patch generation, and validation place different demands on high-capability model calls.
3. **Shared execution state**: many workflows run concurrently, sharing a global quota pool, backend model pool, queues, reservations, and failure-recovery mechanisms.

Therefore, the core systems object of this paper is the full agent workflow and its step sequence under shared runtime constraints. Model choice for a single LLM call still matters, but BudgetFlow also tracks where that call sits in the workflow, how much budget has been reserved and settled, how tight backend quotas are, how long queues are, and whether stalled workflows should release resources.

We propose **BudgetFlow**: a training-free, workflow-aware runtime governor for LLM-agent execution. It sits at the LLM-call layer, maintains per-workflow ledgers, reserves and settles spend, enforces backend quotas, schedules calls across concurrent workflows, and tracks workflow-stage signals. It integrates into existing agent loops via proxy, adapter, or SDK modes for LangChain / SWE-agent / AutoGen.

The core contributions of BudgetFlow are:

1. **Budget-governed agent execution**: we define a systems problem in which concurrent agent workflows share a spend cap, provider quotas, concurrency slots, and a backend model pool.
2. **Workflow-state-aware scheduling**: BudgetFlow uses stage signals, online progress proxies, per-workflow ledger state, and global quota pressure to prioritize scarce high-capability model calls.
3. **Auditable hard-limit enforcement**: BudgetFlow separates `expected_cost`, `reserved_cost`, and `actual_cost`, uses atomic reservation to prevent overspend, and settles realized usage after each call.
4. **Multi-workflow runtime governance**: BudgetFlow admits, queues, downgrades, switches backends, rejects calls, and reclaims reservations and slots from stalled workflows under shared runtime constraints.

---

## 1. Core insight: schedule by workflow state

At the start of a workflow, we only know the issue and initial context. The truly critical information often appears later: search results, code snippets, test failures, tracebacks, patch apply errors. Choosing a model only once at workflow start misses these mid-trajectory signals.

The basic judgment of BudgetFlow is:

> **The same model slot has different scheduling priority at different workflow stages.**

For example:

| Current LLM input | Runtime intuition | Default stage weight |
|---|---|---|
| Directory listings, file trees | low-risk navigation; mistakes are easy to recover from | low |
| Search results, code snippets | requires code understanding; affects later edits | medium |
| Test failures, tracebacks | directly affects root-cause judgment | high |
| Simple verification after a patch is generated | mostly wrap-up or checking | low–medium |

BudgetFlow uses these weights as coarse scheduling signals. The paper tests whether adding workflow-stage state to a hard-limit runtime resolves more tasks and wastes fewer resources than using quota state and reservation size alone.

---

## 2. Where does BudgetFlow sit?

BudgetFlow sits between the agent framework and the LLM backend.

```text
+----------------------------------+       +-----------------------------+
| LangChain / SWE-agent / AutoGen  |       | Self-built agent platform   |
+----------------------------------+       +-----------------------------+
      |                    |                         |
      | Proxy mode:        | Callback mode:          | SDK mode:
      | LLM request msgs   | tool events + metadata  | stage + state
      v                    v                         v
+------------------+ +------------------+      +------------------+
| BudgetFlow Proxy | | BudgetFlow Adapter|     | BudgetFlow SDK   |
+------------------+ +------------------+      +------------------+
         \                  |                         /
          \                 |                        /
           +----------------+-----------------------+
                            |
                            v
                   +--------------------+
                   | BudgetFlow Runtime |
                   +--------------------+
                            |
                            v
         +-------------------------------------+
         | Governor: budget + backend quotas  |
         +-------------------------------------+
                            |
                            v
      +------------------------------------------+
      | ModelSelector: priority + quota state    |
      +------------------------------------------+
                            |
                            v
         +-----------------------------+
         | Multi-workflow Scheduler    |
         +-----------------------------+
                            |
                            v
         +-----------------------------+
         | LLM Backend Pool            |
         +-----------------------------+
```

It can integrate in three ways:

- **Proxy mode**: the agent points an OpenAI-compatible `base_url` to BudgetFlow. BudgetFlow infers the current step type from `messages`, ToolMessages, and observation text.
- **Callback / adapter mode**: LangChain, SWE-agent, or AutoGen supplies structured signals such as tool name, tool output, and step index via hooks.
- **SDK mode**: a self-built platform explicitly passes workflow stage, workflow state, and `workflow_id`.

The paper scope of BudgetFlow is LLM-call runtime governance: choose models, enforce spend caps, rate limit, queue, account for reservations, and reclaim stuck workflows. As a runtime layer between the agent framework and the LLM backend, it can attach to existing LangChain / SWE-agent / AutoGen stacks, or serve as an SDK layer for a custom agent platform.

Here, **workflow-aware** means routing and admission decisions use workflow-level state: how much remains in the global quota pool, how much this workflow has reserved and settled, how tight each backend's RPM / concurrency slots are, whether the current call sits in a critical stage, and whether the workflow is making progress. By contrast, a **workflow-blind** router mainly relies on local information for a single request—prompt text, token counts, model tier, latency—and can be an excellent one-shot request router, yet without a ledger and cross-workflow scheduling state it is hard to enforce hard limits across a batch of agents.

---

## 3. Runtime decision: scheduling priority for each call

For each LLM call, BudgetFlow first checks hard feasibility: remaining budget reservation, backend RPM, concurrency slots, and queue limits. If the call is feasible on more than one backend or model tier, the scheduler assigns an upgrade priority.

Plain-language rule:

```text
If: workflow-stage priority clears the current quota threshold
Then: admit or upgrade the call
Else: stay on the cheaper model, queue, downgrade, or reject
```

Mathematical form:

$$
\text{priority}_i =
\frac{
  w_{\text{stage}(i)}
  \cdot s_i
  \cdot q_t
}{
  \text{reserved\_cost}_i
}
\ge \theta_t
$$

Meaning of each quantity:

| Quantity | Meaning |
|---|---|
| $w_{\text{stage}(i)}$ | coarse weight for the current workflow stage; e.g., traceback analysis ranks above directory browsing |
| $s_i$ | online progress / urgency signal visible at runtime |
| $q_t$ | global quota-headroom multiplier from remaining budget, RPM headroom, queue pressure, and concurrency slots |
| `reserved_cost_i` | budget reservation required before issuing the call |
| $\theta_t$ | current scheduling threshold |

The scheduler does not require oracle knowledge of the final answer. It uses online signals and closed-loop feedback:

| Observed state | Adjustment |
|---|---|
| budget reservations or queues grow too quickly | raise the threshold; fewer upgrades |
| workflows progress while quota remains available | lower the threshold; critical stages upgrade more easily |
| backend RPM / concurrency slots are tight | raise the threshold, queue, or switch backends |
| a workflow stalls or loops | cancel and reclaim budget and slots |

The online signal $s_i$ is computed only from information available during execution: stage type, tool name, observation type, test failure text, patch-apply status, retry count, repeated actions, recent queue wait, and stall indicators. Gold patches and final benchmark labels are never used by the runtime scheduler.

Note: before a call completes, BudgetFlow does not know the true output token count and can only estimate. It uses estimated costs for ranking, reserved costs for hard-limit safety, and realized usage for experimental reporting.

A simple example: after a test failure, the workflow enters a debugging stage with high stage weight. If queue pressure is low and budget headroom is available, the call can clear the priority threshold and use a stronger model. During directory browsing, the same workflow receives a lower stage weight, so the scheduler keeps the call on a cheaper model or queues it behind more urgent debugging calls. This illustrates the core principle of BudgetFlow: scarce high-capability model calls are scheduled toward workflow stages where runtime evidence suggests they are most likely to affect the final repair.

---

## 4. How do we enforce spend caps?

There are three spend-accounting notions; do not mix them.

### 4.1 `expected_cost`: pre-call estimate

Before a call, input token counts are known exactly, but output token counts are unknown, so output length is estimated from historical means or rolling averages.

$$
\text{expected\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \widehat{\text{output\_tokens}} \cdot p_{\text{out}}
$$

This is used for scheduling priority and model-tier comparison.

### 4.2 `reserved_cost`: pre-call reservation

To enforce a hard spend cap, the runtime cannot rely on average output length alone. Before issuing a call, BudgetFlow reserves budget using a controllable upper bound:

$$
\text{reserved\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \text{max\_output\_tokens} \cdot p_{\text{out}}
$$

If the remaining budget cannot cover the reserved cost, the system must downgrade the model, lower the output cap, queue, or reject the call.

### 4.3 `actual_cost`: post-call settlement

After a call completes, settle using the true token counts returned by the provider or local serving logs:

$$
\text{actual\_cost}
= \text{actual\_input\_tokens} \cdot p_{\text{in}}
+ \text{actual\_output\_tokens} \cdot p_{\text{out}}
$$

If `actual_cost < reserved_cost`, the difference is returned to the global quota pool. Under concurrency, reservation and settlement must be atomic so that 50 workflows reading the same remaining budget cannot overspend together.

---

## 5. How do we measure quality?

### 5.1 What is SWE-bench Verified?

SWE-bench is a coding-agent benchmark: it selects real bugs from open-source Python projects such as Django, scikit-learn, and sympy that humans have already fixed. Each task gives the agent a GitHub issue description plus a snapshot of the repository, and asks the agent to localize the bug, modify code, and produce a patch.

**SWE-bench Verified** is a human-curated subset released by OpenAI in 2024 with 500 tasks. It removes samples from the original SWE-bench where the issue description is ambiguous or tests are unreliable, and it is the most common primary metric source in coding-agent papers today.

Each task ships with ground-truth information:

- **gold patch**: the human developer's true fix diff from that time;
- **`FAIL_TO_PASS` tests**: tests that fail before the bug is fixed and must pass after the fix—this is the hard signal for whether "the bug is really fixed";
- **`PASS_TO_PASS` tests**: tests that should pass both before and after the fix, used to check that the agent did not break unrelated functionality.

### 5.2 Task outcome metric: `resolved`

This paper does not invent any subjective quality score. The task outcome metric is the boolean `resolved` produced by the official SWE-bench Verified harness.

A task is judged resolved only if all of the following hold:

1. the agent produces a non-empty patch;
2. the patch applies successfully with `git apply` on the original repo;
3. after apply, all `FAIL_TO_PASS` tests pass;
4. after apply, all `PASS_TO_PASS` tests still pass.

Concrete example: for `django__django-11099`, the issue is that `UsernameValidator` allows usernames to end with a newline. The agent must:

- find `django/contrib/auth/validators.py`;
- change the regex from `$` to `\Z` so a trailing newline cannot be treated as end-of-match;
- submit the patch.

The harness runs the task's `FAIL_TO_PASS` test (a test that specifically checks "usernames containing a newline must be rejected"). Passing yields resolved=True; otherwise resolved=False. Note: the harness ignores which model the agent used, how many steps it took, and how much budget it consumed; it only evaluates the final patch behavior.

The paper-level success criterion is one sentence:

> Under the same hard spend cap and backend quotas, how many more SWE-bench Verified tasks does BudgetFlow resolve compared to baselines, while avoiding budget and quota violations?

### 5.3 Online scheduling signals vs offline analysis signals

Section 3's scheduling priority uses only runtime-visible signals. These signals need not prove that the task is solved; they only help the scheduler decide whether a call is urgent enough to use scarce high-capability model capacity.

Runtime-visible signals:

| Signal | How to compute it | Use |
|---|---|---|
| Workflow stage | classify from tool name, adapter metadata, or message / observation text | coarse scheduling priority |
| Observation type | detect code snippets, search results, tracebacks, test failures, patch errors | stage-specific urgency |
| Patch apply status | dry-run the current patch in a sandbox | repair / generation stages |
| Test failure text | parse failing test names, traceback length, repeated failures | validation / debugging stages |
| Retry / loop signal | count repeated actions, repeated file opens, unchanged patches, or repeated test failures | downgrade, queue, or cancel stalled workflows |
| Ledger and queue state | read reserved budget, actual usage, queue wait, RPM headroom, concurrency slots | quota-aware admission and priority |

Offline analysis signals are used only for calibration, ablation, and case studies:

| Signal | How to compute it | Use |
|---|---|---|
| Whether files touched by the gold patch were opened | compare visited paths in the agent trajectory against changed files in the gold patch | post-hoc localization analysis |
| Whether failing-test count decreases on the official tests | run the benchmark harness after the trajectory | evaluation and case studies |
| thought/action/observation in `.traj` | SWE-agent writes each step's reasoning, tool calls, and tool returns into `<task_id>.traj` JSON | post-hoc alignment of scheduling decisions and outcomes |

Gold patches and final benchmark labels must not enter the online scheduler. They are allowed only after the run, when explaining why a scheduling decision helped or failed. The main results table reports task outcomes and systems metrics, not a learned or subjective step-quality score.

### 5.4 Why do we need a held-out calibration split?

Here we must avoid a subtle circularity.

Section 1 includes a stage-weight table (traceback ranks above directory browsing, and so on). These weights may need light tuning from data—for example: whether traceback stages should receive a higher scheduling priority than search stages under the same quota pressure.

The problem is: **if we tune stage weights on all 500 SWE-bench Verified tasks and then report resolved rate on the same 500 tasks, that is like studying with the answer key and then taking the same exam.** Any apparent gain may be overfitting.

The fix is to split data:

- **Calibration split**: used to tune stage weights and scheduling thresholds. This can be data outside SWE-bench Verified, for example samples from the original SWE-bench that never entered Verified, or the non-overlapping portion of SWE-bench Lite relative to Verified.
- **Evaluation split**: the full SWE-bench Verified 500 tasks, **never touched during tuning**. Final paper numbers for resolved rate, budget violations, quota violations, queue latency, and recovery metrics are reported only on this half.

"Held-out" means "set aside and untouched"—lock the evaluation split until all design decisions are finalized, then open the box.

If a BudgetFlow variant truly needs no tuning (for example, stage weights always follow a fixed default table end-to-end), then strictly speaking no calibration split is required. For honesty, this paper assumes some tuning is likely and declares this split protocol up front.

---

## 6. Three primary system comparisons

### 6.1 Workflow-Level Router

At workflow start, pick one model or routing profile based on the initial issue / prompt / repository context, and keep that choice for the entire workflow.

It answers:

> Is choosing a model only once at task start enough?

This is the most important comparison because many routing systems in practice are request-level or task-level.

### 6.2 Quota-Only Step Scheduler

It also decides per step and enforces hard limits, but ignores workflow stage and observation types.

It only looks at:

- `reserved_budget / total_budget`
- `settled_budget / total_budget`
- `completed_tasks / total_tasks` or batch progress
- the current call's `expected_cost` / `reserved_cost`

This is equivalent to removing stage weights and observation-aware signals from the BudgetFlow scheduler:

```text
Only quota level and reservation size; ignore workflow stage and runtime observation type.
```

It answers:

> Does the gain come only from quota pacing, or do we need workflow-stage state for scheduling?

### 6.3 BudgetFlow Full

The full system includes:

- per-step routing;
- scheduling threshold;
- stage weights;
- observation-aware signals;
- a workflow ledger;
- hard-budget reservation;
- backend admission control;
- zombie recovery.

It answers:

> Under the same hard spend cap and backend quotas, does workflow-state-aware scheduling resolve more SWE-bench tasks than workflow-level routing and quota-only step scheduling?

---

## 7. Multi-workflow runtime

The main scenario of this paper is batched SWE-bench evaluation:

> 50 SWE-agent instances run SWE-bench Verified concurrently, sharing a spend cap such as \$50, while respecting provider RPM limits and concurrency slots.

The target users are people who build agents and teams who operate agent platforms: maintainers of open-source agent frameworks, in-house agent product teams, internal LLM gateway operators for a single team, and researchers who need reproducible evaluation harnesses. This paper focuses on a single budget owner plus many concurrent workflows; multi-team, multi-SLA, multi-budget-pool quota arbitration is future work.

Under this setting, BudgetFlow handles five runtime questions on each LLM call:

1. Can the global quota pool reserve this call?
2. What priority does this call receive under its workflow stage and current quota state?
3. Does the target backend still have RPM / concurrency headroom?
4. If there is no slot, should we queue, downgrade, switch backends, or reject?
5. If a workflow is stuck, how do we release reserved budget and concurrency slots?

This runtime governance places per-call model selection inside an executable system environment: reservations must be atomic, completed calls must settle and return unused budget, backend quotas must be honored, and stuck workflows must release resources. This keeps the main thread anchored on agent workflow runtime governance.

Key BudgetFlow components:

| Component | Role |
|---|---|
| Ledger | records per-workflow reservation, realized spend, and state |
| Governor | atomic budget reservation, settlement, and backend rate limiting |
| ModelSelector | chooses models using stage weight, online signal, and quota state |
| Scheduler | admits, queues, downgrades, or switches backends under RPM / concurrency limits |
| ZombieDetector | cancels no-progress workflows and reclaims budget and slots |

---

## 8. Experimental design

### 8.1 Workload

- Benchmark: SWE-bench Verified;
- Agent scaffold: SWE-agent or mini-SWE-agent; keep one choice for the whole paper;
- Concurrency: `J = 1 / 10 / 50 / 100`;
- Spend cap: e.g., `B_total = $50`, and report curves across caps;
- Backend pool: may include API models and local models, but the claim should not hinge on specific model names.

### 8.2 Research questions

| RQ | Question | Metrics |
|---|---|---|
| RQ1 | Can BudgetFlow enforce hard spend caps and backend RPM / concurrency limits? | budget violations, 429 rate, queue latency |
| RQ2 | Does workflow-state-aware scheduling beat workflow-level routing? | resolved rate under fixed cap, admission latency |
| RQ3 | Does workflow-stage state beat quota level alone? | BudgetFlow Full vs Quota-Only Step Scheduler |
| RQ4 | Under many concurrent workflows, do ledger / admission / zombie recovery reduce wasted resources? | recovered budget, cancelled zombies, p99 latency |

### 8.3 Primary metrics

| Metric | Meaning |
|---|---|
| Resolved rate @ fixed cap | how many SWE-bench tasks are resolved under the same spend cap |
| Budget violation rate | whether the hard spend cap is exceeded |
| 429 rate | whether provider RPM limits are hit |
| p50/p99 queue latency | queuing delay |
| Admission throughput | admitted calls per minute under shared quotas |
| Recovered budget | budget returned from stuck workflows |
| Wasted reservation ratio | reserved budget that never becomes useful completed work |
| Efficiency metric | spend per resolved task, reported as secondary context |

---

## 9. Related Work

### Request and workflow-level model routing

RouteLLM, CARROT, OmniRouter, LiteLLM auto-router, and related work choose models for a single request or for a task-level routing profile. They can be strong engineering tools, but they typically do not maintain per-workflow ledgers, coordinate a global quota pool across many concurrent agents, or use mid-trajectory observations as scheduling state.

The comparison question of this paper is:

> For multi-step agent workflows like SWE-bench, is request- or workflow-level routing enough without runtime quota orchestration?

### LLM serving and workflow orchestration

ATHENA-Serve, Parrot, Aragog, Murakkab, Autellix, and Helium are all helpful to BudgetFlow because they show that agentic LLM workloads are a real serving / orchestration problem: requests differ in length, workflows differ by stage, backends have KV cache, batching, concurrency, RPM, SLOs, and tail-latency pressure.

These systems mainly give BudgetFlow two classes of insight:

1. **Serving layer can be smarter**: ATHENA-Serve maps generation horizons into KV / compute budgets and uses hierarchical RL for admission, batching, and concurrency control. Autellix and Helium likewise argue that workflow-aware serving reduces head-of-line blocking and improves throughput and tail latency.
2. **Runtime layer should expose structure**: Parrot's semantic variables, Aragog's just-in-time routing, and Murakkab's workflow orchestration all show that structural workflow information can enter runtime decisions, so each prompt carries step context and workflow state into the system layer.

BudgetFlow uses these conclusions as systems context: agent runtimes should understand workflows, and backend scheduling affects latency, throughput, and quota pressure. BudgetFlow sits above the serving engine as an agent workflow governor: it reserves budget, assigns priority, performs admission control, and selects model / backend candidates; ATHENA / Autellix / Helium-style serving systems then execute admitted requests more efficiently.

### Agent runtime / resource governance

AgentRM, AgentCgroup, AIOS, and related work focus on resource management, isolation, or stability for agent systems. BudgetFlow is narrower in scope and deeper at the LLM-call boundary: it governs spend reservations, backend quotas, workflow-stage scheduling, and recovery for concurrent agent workflows.

### Learned agent routing policies

BoPO establishes that step-level model routing for long-horizon agents is a real research problem. It trains a learned router with reinforcement learning and studies success under constrained model budgets on ALFWorld, SciWorld, and AppWorld.

BudgetFlow treats learned selection as a policy module that can sit inside the ModelSelector. The paper's main systems question is the runtime contract around that policy: ledger state, hard reservation, backend admission, scheduling, settlement, and recovery when many workflows execute concurrently.

---

## 10. Threats to Validity

### SWE-bench scope

This paper only claims applicability to coding-agent workflows with verifiable intermediate signals. Customer support, creative writing, and scientific reasoning lack gold patches and deterministic tests, and need new progress signals or evaluators.

### Coarseness of stage weights

Stage weight is only a coarse scheduling signal. The Quota-Only Step Scheduler ablation is required: after removing stage and observation state, does performance drop?

### Estimated cost is not realized cost

Before a call, output token counts are unknown, so BudgetFlow can only rank with `expected_cost`, enforce budgets with `reserved_cost`, and report experiments with `actual_cost`.

### KV / prompt caching

Cloud APIs often do not expose raw KV cache. Staying on one model may benefit from provider-side prompt caching or prefix caching, while frequent model switching may lose those benefits. Cross-model KV / cache costs are hard to quantify cleanly because tokenizers, architectures, output lengths, and billing rules differ. We treat this as a threat / future work and do not inject a synthetic switching penalty into the main experiments.

---

## 11. Future Work

### Multi-tenant resource allocation

This paper handles a single budget owner: one researcher or one team holds the total budget and runs many workflows. Multi-team, multi-SLA, multi-priority quota arbitration is the next step.

This mirrors a common evolution in systems work: first make the core mechanism crisp under a single-tenant setting, then add a multi-tenant policy layer. BudgetFlow's first step is to show whether a workflow ledger, budget reservation, backend admission, and scheduling improve agent execution under hard shared limits; multi-tenant agent compute allocation can build on top.

### SLA-aware scheduling

Interactive agent workloads introduce deadlines, SLA tiers, latency SLOs, and throughput goals. BudgetFlow can extend its scheduler to combine spend caps with latency classes, deadline-aware admission, and priority isolation across workflow groups.

### Workflow-stage auto-classification

The current design can receive stage metadata from adapters or infer it from messages and tool events. A future runtime can make this classifier more robust across agent frameworks, repositories, and non-coding workflows.

### Agent-native loop

This paper places BudgetFlow between existing agent frameworks and the LLM backend to first prove the value of budget-governed workflow scheduling. Later, a BudgetFlow-native agent loop can unify tool execution, observations, ledger, ModelSelector, and scheduler into one runtime to reduce integration cost.

### Cache-aware routing

If a provider or local serving stack exposes cached-token / prefix-cache signals, BudgetFlow can incorporate cache locality into `actual_cost` or a future selector. This paper does not assume direct control over KV cache.

### Learned selector as a plug-in

A learned selector, for example borrowing BoPO-style boundary-guided training, can replace or refine the heuristic ModelSelector. The ledger, reservation, admission, scheduling, settlement, and recovery mechanisms remain the runtime substrate around that learned policy.

### Non-coding workflows

Customer support, RAG, and scientific reasoning can reuse ledger, reservation, and scheduler machinery, but need new workflow-stage signals and evaluators. Without a reliable evaluator, do not reuse the SWE-bench stage table verbatim.

The main experiments in this paper focus on batched SWE-bench-style workloads: maximize final resolved rate under a fixed spend cap while enforcing quotas and concurrency limits. Interactive / SLA constraints are natural extensions and should not be silently mixed into the paper-1 objective.

---

## 12. Quick glossary

| Concept | One sentence |
|---|---|
| Turn / Step | one LLM call |
| Workflow | a sequence of LLM calls from task start to finish |
| Stage weight | coarse scheduling weight for the current workflow stage |
| Online signal | runtime-visible signal such as observation type, patch status, retry count, queue state, or stall indicator |
| Quota state | remaining spend cap, RPM headroom, concurrency slots, and queue pressure |
| Scheduling threshold | current admission / upgrade threshold derived from quota state |
| `expected_cost` | pre-call estimated cost; used for ranking |
| `reserved_cost` | pre-call reserved cost; used for hard-budget safety |
| `actual_cost` | post-call realized cost; used for reporting experiments |
| Workflow-aware | routing that keeps a workflow ledger, quota state, backend quotas, and stage signals |
| Workflow-blind | routing that mostly uses local per-request information without cross-step budget state |
| Workflow-Level Router | pick a model or routing profile once at workflow start |
| Quota-Only Step Scheduler | decide per step using only quota state, ignoring workflow stage and observation type |
| BudgetFlow Full | per-step decisions + stage signals + quota state + runtime governance |

# Spend Tokens Where They Matter: Workflow-Aware Budgeting for LLM Agents

> **One-liner**: Under a fixed token / dollar budget, BudgetFlow reserves stronger models for the steps in an agent workflow that matter most, and enforces the global budget, provider RPM limits, and concurrency slots when many workflows run concurrently.

---

## 0. What problem does this paper solve?

Today's LLM agents are usually composed of many model calls. Take SWE-bench as an example: a coding agent reads an issue, searches files, reads code, writes a patch, runs tests, and then iterates using failure logs. Every step spends tokens, but steps differ in value: a wrong directory listing is often recoverable, while a wrong root-cause judgment after a test failure can ruin the whole trajectory.

We formalize this phenomenon as an **agent workflow hard-spend governance** problem:

> **Given a fixed token / dollar budget, how should we allocate stronger-model calls across the steps of an agent workflow so that a batch of concurrent workflows completes more verifiable tasks under the same budget?**

This problem has three key ingredients:

1. **A fixed economic budget**: the total token / dollar cap is given up front, and the runtime must enforce this hard cap.
2. **Heterogeneous step value across multi-step workflows**: one dollar spent on directory browsing, code understanding, traceback analysis, or patch repair has different marginal value.
3. **A shared runtime across many workflows**: many tasks run concurrently, sharing a budget pool, provider RPM limits, concurrency slots, and a backend model pool.

Therefore, the core optimization unit of this paper is the full agent workflow and its step sequence. Model choice for a single LLM call still matters, but BudgetFlow cares about the budget position of these calls along the full trajectory and across the whole batch: whether the current step is worth upgrading, how much this workflow has spent, how much global budget remains, how tight backend quotas are, and whether the decision increases the final number of `resolved` tasks under a fixed budget.

We propose **BudgetFlow**: a training-free, workflow-aware budgeting runtime. It sits at the LLM-call layer, maintains a budget ledger, enforces backend rate limits, and tracks step-importance signals. It integrates into existing agent loops via proxy, adapter, or SDK modes for LangChain / SWE-agent / AutoGen.

The core contributions of BudgetFlow are:

1. **A hard-spend formulation for agent workflows**: we define the agent quality–cost tradeoff as step-level spend allocation under a fixed budget, with verifiable task success as the primary outcome metric.
2. **Training-free hard-cap adaptation**: across different budget ceilings, the runtime adjusts the upgrade threshold using `budget_pressure`. When the budget is tight, upgrades are rarer; when the budget is ample, critical steps upgrade more easily.
3. **Auditable cost accounting**: we separate `expected_cost`, `reserved_cost`, and `actual_cost`, use reservation to enforce a hard budget, and use realized costs for reporting in experiments.
4. **Multi-workflow runtime governance**: when many workflows share one total budget, provider RPM limits, and concurrency slots, BudgetFlow admits, queues, downgrades, switches backends, or rejects each LLM call, and reclaims budget and slots from stuck workflows.

---

## 1. Core insight: spend budget by step

At the start of a workflow, we only know the issue and initial context. The truly critical information often appears later: search results, code snippets, test failures, tracebacks, patch apply errors. Choosing a model only once at workflow start misses these mid-trajectory signals.

The basic judgment of BudgetFlow is:

> **The same dollar has different value when spent on different steps.**

For example:

| Current LLM input | Intuition | Default importance |
|---|---|---|
| Directory listings, file trees | low-risk navigation; mistakes are easy to recover from | low |
| Search results, code snippets | requires code understanding; affects later edits | medium |
| Test failures, tracebacks | directly affects root-cause judgment | high |
| Simple verification after a patch is generated | mostly wrap-up or checking | low–medium |

BudgetFlow defines these weights as coarse budget-allocation signals, and uses controlled experiments to test whether using both budget level and step importance resolves more tasks than using budget level alone.

---

## 2. Where does BudgetFlow sit?

BudgetFlow sits between the agent framework and the LLM backend.

```text
+----------------------------------+       +-----------------------------+
| LangChain / SWE-agent / AutoGen  |       | Self-built agent platform   |
+----------------------------------+       +-----------------------------+
      |                    |                         |
      | Proxy mode:        | Callback mode:          | SDK mode:
      | LLM request msgs   | tool events + metadata  | task_type + w_i
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
      | ModelSelector: budget_pressure + w_i     |
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
- **SDK mode**: a self-built platform explicitly passes `task_type`, `w_i`, and `workflow_id`.

The paper scope of BudgetFlow is LLM-call governance: choose models, enforce budgets, rate limit, queue, account for spend, and reclaim stuck workflows. As a budgeting runtime between the agent framework and the LLM backend, it can attach to existing LangChain / SWE-agent / AutoGen stacks, or serve as an SDK layer for a custom agent platform.

Here, **workflow-aware** means routing decisions use workflow-level state: how much remains in the global budget pool, how much this workflow has spent and reserved, how high `budget_pressure` is, how tight each backend's RPM / concurrency slots are, and whether the current call sits in a critical context. By contrast, a **workflow-blind** router mainly relies on local information for a single request—prompt text, token counts, model cost, latency—and can be an excellent one-shot request router, yet without a ledger and cross-workflow scheduling state it is hard to pace spend across steps.

---

## 3. Runtime decision: is this step worth upgrading?

For each LLM call, BudgetFlow starts from a cheaper model and walks upward, deciding whether each upgrade is worthwhile.

Plain-language rule:

```text
If: step importance × estimated progress gain ÷ extra cost >= current budget threshold
Then: upgrade to a stronger model
Else: stay on the current model
```

Mathematical form:

$$
w_i \cdot
\frac{\Delta \widehat{\text{progress}}_i}
     {\Delta \widehat{\text{cost}}_i}
\ge \text{budget\_pressure}_t
$$

Meaning of each quantity:

| Quantity | Meaning |
|---|---|
| $w_i$ | how critical the current step is; e.g., traceback analysis ranks above directory browsing |
| $\Delta \widehat{\text{progress}}_i$ | estimated extra verifiable progress from upgrading the model at this step |
| $\Delta \widehat{\text{cost}}_i$ | estimated extra dollars from upgrading the model at this step |
| `budget_pressure` | the current budget threshold; it rises when the budget is tight and falls when the budget is loose |

`budget_pressure` does not require predicting the future. It only performs closed-loop feedback:

| Observed state | Adjustment |
|---|---|
| spend rate runs ahead of task progress | raise the threshold; fewer upgrades |
| spend rate lags task progress | lower the threshold; critical steps upgrade more easily |
| backend RPM / concurrency slots are tight | raise the threshold, or queue, or switch backends |
| a workflow stalls or loops | cancel and reclaim budget and slots |

Note: before a call completes, BudgetFlow does not know the true output token count and can only estimate. It uses estimated costs for ranking, reserved costs for budget safety, and realized bills for experimental evaluation.

A simple example: after a test failure, we are in a debugging step with default $w_i=3$. Upgrading from mini to Sonnet is estimated to add 0.12 step progress at an extra cost of \$0.04, so the upgrade score is $3 \times 0.12 / 0.04 = 9$. If `budget_pressure=4`, this step is worth upgrading. If the same progress gain appears during directory browsing with $w_i=1$, the score becomes 3 and the system stays on the cheaper model. This example illustrates the core principle of BudgetFlow: stronger-model budget flows first toward steps that are closer to the final repair decision.

---

## 4. How do we account for cost?

There are three cost notions; do not mix them.

### 4.1 `expected_cost`: pre-call estimate

Before a call, input token counts are known exactly, but output token counts are unknown, so output length is estimated from historical means or rolling averages.

$$
\text{expected\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \widehat{\text{output\_tokens}} \cdot p_{\text{out}}
$$

This is only used to compare whether "going up one tier" is worthwhile.

### 4.2 `reserved_cost`: pre-call reservation

To claim a hard budget, you cannot rely on average output length alone. Before issuing a call, BudgetFlow reserves budget using a controllable upper bound:

$$
\text{reserved\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \text{max\_output\_tokens} \cdot p_{\text{out}}
$$

If the remaining budget cannot cover the reserved cost, the system must downgrade the model, lower the output cap, queue, or reject.

### 4.3 `actual_cost`: post-call settlement

After a call completes, settle using the true token counts returned by the provider or local serving logs:

$$
\text{actual\_cost}
= \text{actual\_input\_tokens} \cdot p_{\text{in}}
+ \text{actual\_output\_tokens} \cdot p_{\text{out}}
$$

If `actual_cost < reserved_cost`, the difference is refunded to the global budget pool. Under concurrency, reservation and refund must be atomic so that 50 workflows reading the same remaining budget cannot overspend together.

---

## 5. How do we measure quality?

### 5.1 What is SWE-bench Verified?

SWE-bench is a coding-agent benchmark: it selects real bugs from open-source Python projects such as Django, scikit-learn, and sympy that humans have already fixed. Each task gives the agent a GitHub issue description plus a snapshot of the repository, and asks the agent to localize the bug, modify code, and produce a patch.

**SWE-bench Verified** is a human-curated subset released by OpenAI in 2024 with 500 tasks. It removes samples from the original SWE-bench where the issue description is ambiguous or tests are unreliable, and it is the most common primary metric source in coding-agent papers today.

Each task ships with ground-truth information:

- **gold patch**: the human developer's true fix diff from that time;
- **`FAIL_TO_PASS` tests**: tests that fail before the bug is fixed and must pass after the fix—this is the hard signal for whether "the bug is really fixed";
- **`PASS_TO_PASS` tests**: tests that should pass both before and after the fix, used to check that the agent did not break unrelated functionality.

### 5.2 Primary metric: `resolved`

This paper does not invent any subjective quality score. The primary metric is the boolean `resolved` produced by the official SWE-bench Verified harness.

A task is judged resolved only if all of the following hold:

1. the agent produces a non-empty patch;
2. the patch applies successfully with `git apply` on the original repo;
3. after apply, all `FAIL_TO_PASS` tests pass;
4. after apply, all `PASS_TO_PASS` tests still pass.

Concrete example: for `django__django-11099`, the issue is that `UsernameValidator` allows usernames to end with a newline. The agent must:

- find `django/contrib/auth/validators.py`;
- change the regex from `$` to `\Z` so a trailing newline cannot be treated as end-of-match;
- submit the patch.

The harness runs the task's `FAIL_TO_PASS` test (a test that specifically checks "usernames containing a newline must be rejected"). Passing yields resolved=True; otherwise resolved=False. Note: the harness ignores which model the agent used, how many steps it took, and how much money it spent—it only evaluates the final patch behavior.

The paper-level success criterion is one sentence:

> Under the same total budget, how many more SWE-bench Verified tasks does BudgetFlow resolve compared to baselines?

### 5.3 Step-level progress: runtime-only, not the headline metric

Section 3's $\Delta \widehat{\text{progress}}_i$ needs a proxy signal for "did this step move the task forward?"

| Signal | How to compute it | Use |
|---|---|---|
| Whether files touched by the gold patch were opened | compare visited paths in the agent trajectory against changed files in the gold patch | localization / search stages |
| Whether the patch can `git apply` | dry-run in a sandbox | repair / generation stages |
| Whether failing-test count decreases | run a lightweight subset (e.g., only `FAIL_TO_PASS`) and track pass-count changes | validation / debugging stages |
| thought/action/observation in `.traj` | SWE-agent writes each step's reasoning, tool calls, and tool returns into `<task_id>.traj` JSON for post-hoc alignment of cost, decisions, and outcomes | debugging and analysis |

These signals are only used for: (a) runtime decisions to estimate whether an upgrade is worthwhile; (b) case studies explaining where BudgetFlow spends more money at certain step types. **They do not enter the main results table**; the main table only reports `resolved`.

### 5.4 Why do we need a held-out calibration split?

Here we must avoid a subtle circularity.

Section 1 includes a "step importance" table (traceback ranks above directory browsing, and so on). These weights $w_i$ are not given by fiat; they may need light tuning from data—for example: "how many extra tasks do we resolve if we upgrade on traceback steps with GPT-4 versus Haiku?" If the answer is 8, raise the weight a bit; if it is only 1, lower it.

The problem is: **if we tune $w_i$ on all 500 SWE-bench Verified tasks and then report resolved rate on the same 500 tasks, that is like studying with the answer key and then taking the same exam.** Any apparent gain may be overfitting.

The fix is to split data:

- **Calibration split**: used to tune weights. This can be data outside SWE-bench Verified, for example samples from the original SWE-bench that never entered Verified, or the non-overlapping portion of SWE-bench Lite relative to Verified. On this half, iterate on $w_i$ and progress-signal thresholds until you find a reasonable setting.
- **Evaluation split**: the full SWE-bench Verified 500 tasks, **never touched during tuning**. Final paper numbers for resolved rate and cost per resolved are reported only on this half.

"Held-out" means "set aside and untouched"—lock the evaluation split until all design decisions are finalized, then open the box.

If a BudgetFlow variant truly needs no tuning (for example, $w_i$ always follows a fixed default table end-to-end), then strictly speaking no calibration split is required. For honesty, this paper assumes some tuning is likely and declares this split protocol up front.

---

## 6. Three primary system comparisons

### 6.1 Workflow-Level Router

At workflow start, pick one model or routing profile based on the initial issue / prompt / repository context, and keep that choice for the entire workflow.

It answers:

> Is choosing a model only once at task start enough?

This is the most important comparison because many routing systems in practice are request-level or task-level.

### 6.2 Budget-Only Step Router

It also decides per step and enforces a budget, but ignores step importance and observation types.

It only looks at:

- `spent_budget / total_budget`
- `completed_tasks / total_tasks` or batch progress
- the current call's `expected_cost` / `reserved_cost`

This is equivalent to removing $w_i$ and observation-aware signals from the BudgetFlow formula:

```text
Only budget level and the cost of this call; ignore whether this step is critical.
```

It answers:

> Does the gain come only from budget pacing, or do we truly need to know which steps are worth spending on?

### 6.3 BudgetFlow Full

The full system includes:

- per-step routing;
- `budget_pressure`;
- step importance $w_i$;
- observation-aware signals;
- a workflow ledger;
- hard-budget reservation;
- backend admission control;
- zombie recovery.

It answers:

> Under the same total budget, does workflow-aware step-level budgeting resolve more SWE-bench tasks than workflow-level routing and budget-only step routing?

---

## 7. Multi-workflow runtime

The main scenario of this paper is batched SWE-bench evaluation:

> 50 SWE-agent instances run SWE-bench Verified concurrently, sharing a total budget such as \$50, while respecting provider RPM limits and concurrency slots.

The target users are people who build agents and teams who operate agent platforms: maintainers of open-source agent frameworks, in-house agent product teams, internal LLM gateway operators for a single team, and researchers who need reproducible evaluation harnesses. This paper focuses on a single budget owner plus many concurrent workflows; multi-team, multi-SLA, multi-budget-pool quota arbitration is future work.

Under this setting, BudgetFlow handles five runtime questions on each LLM call:

1. Can the global budget still cover this call?
2. Is the current step worth upgrading?
3. Does the target backend still have RPM / concurrency headroom?
4. If there is no slot, should we queue, downgrade, switch backends, or reject?
5. If a workflow is stuck, how do we release reserved budget and concurrency slots?

This runtime governance places step-level spend decisions inside an executable system environment: reservations must be atomic, completed calls must settle and refund, backend quotas must be honored, and stuck workflows must release resources. It supports the hard-spend formulation of this paper and keeps the main thread anchored on agent workflow budget governance.

Key BudgetFlow components:

| Component | Role |
|---|---|
| Ledger | records per-workflow reservation, realized spend, and state |
| Governor | atomic budget reservation, settlement, and backend rate limiting |
| ModelSelector | chooses models using step importance, estimated benefit, and budget pressure |
| Scheduler | admits, queues, downgrades, or switches backends under RPM / concurrency limits |
| ZombieDetector | cancels no-progress workflows and reclaims budget and slots |

---

## 8. Experimental design

### 8.1 Workload

- Benchmark: SWE-bench Verified;
- Agent scaffold: SWE-agent or mini-SWE-agent; keep one choice for the whole paper;
- Concurrency: `J = 1 / 10 / 50 / 100`;
- Total budget: e.g., `B_total = $50`, and report curves across budgets;
- Backend pool: may include API models and local models, but the claim should not hinge on specific model names.

### 8.2 Research questions

| RQ | Question | Metrics |
|---|---|---|
| RQ1 | Can BudgetFlow enforce a hard budget and backend RPM / concurrency limits? | budget violations, 429 rate, queue latency |
| RQ2 | Does step-level routing beat workflow-level routing? | resolved rate, cost per resolved |
| RQ3 | Does step importance beat budget level alone? | BudgetFlow Full vs Budget-Only Step Router |
| RQ4 | Under many concurrent workflows, do ledger / admission / zombie recovery reduce wasted resources? | recovered budget, cancelled zombies, p99 latency |

### 8.3 Primary metrics

| Metric | Meaning |
|---|---|
| Resolved rate @ fixed budget | how many SWE-bench tasks are resolved under the same budget |
| Cost per resolved | dollars spent per resolved task |
| Budget violation rate | whether the hard budget is exceeded |
| 429 rate | whether provider RPM limits are hit |
| p50/p99 queue latency | queuing delay |
| Recovered budget | budget returned from stuck workflows |

---

## 9. Related Work

### Per-query / task-level routing

RouteLLM, CARROT, OmniRouter, LiteLLM auto-router, and related work mainly optimize model choice for a single request or at task start. They can be strong engineering tools, but they typically do not maintain a workflow ledger and do not use mid-trajectory observations to judge whether the current step is critical.

The comparison question of this paper is:

> For multi-step agent workflows like SWE-bench, is workflow-level routing alone enough?

### Budget-Aware Agentic Routing / BoPO

BoPO establishes an important fact: step-level model routing for long-horizon agents is a real research problem. It trains a learned router with reinforcement learning and studies cost–success tradeoffs on ALFWorld, SciWorld, and AppWorld.

We treat BoPO as closely related work and as a future learned-selector direction. Because benchmarks, model pools, agent scaffolds, and training pipelines differ substantially, the SWE-bench main experiments prioritize reproducible workflow-level, budget-only, and BudgetFlow-full comparisons. This paper studies a different line:

> Build a training-free budgeting runtime on SWE-bench-style coding workflows, and study system behavior when many workflows share a budget and backend resources.

In one sentence, BoPO learns an implicit routing policy; BudgetFlow exposes an auditable runtime decision rule. In the future, a BoPO-style learned selector can plug into the ModelSelector slot and replace the heuristic rule, while still reusing the ledger, hard-budget reservation, backend governor, and multi-workflow scheduler.

### LLM serving and workflow orchestration

ATHENA-Serve, Parrot, Aragog, Murakkab, Autellix, and Helium are all helpful to BudgetFlow because they show that agentic LLM workloads are a real serving / orchestration problem: requests differ in length, workflows differ by stage, backends have KV cache, batching, concurrency, RPM, SLOs, and tail-latency pressure.

These systems mainly give BudgetFlow two classes of insight:

1. **Serving layer can be smarter**: ATHENA-Serve maps generation horizons into KV / compute budgets and uses hierarchical RL for admission, batching, and concurrency control. Autellix and Helium likewise argue that workflow-aware serving reduces head-of-line blocking and improves throughput and tail latency.
2. **Runtime layer should expose structure**: Parrot's semantic variables, Aragog's just-in-time routing, and Murakkab's workflow orchestration all show that structural workflow information can enter runtime decisions, so each prompt carries step context and workflow state into the system layer.

BudgetFlow uses these conclusions as systems context: agent runtimes should understand workflows, and backend scheduling also affects final cost and latency. This paper places its research question on another layer: given a fixed economic budget, how should stronger-model calls be allocated across workflow steps to improve final task success? A practical deployment can place BudgetFlow between the agent framework and a serving engine: BudgetFlow decides how much this step is worth spending and which model or backend to use; ATHENA / Autellix / Helium-style serving systems then execute admitted requests more efficiently.

### Agent runtime / resource governance

AgentRM, AgentCgroup, AIOS, and related work focus on resource management, isolation, or stability for agent systems. BudgetFlow is narrower in scope: it only governs LLM-call budgets, but it places quality goals, budget ledgers, and backend quotas inside one experimental runtime.

---

## 10. Threats to Validity

### SWE-bench scope

This paper only claims applicability to coding-agent workflows with verifiable intermediate signals. Customer support, creative writing, and scientific reasoning lack gold patches and deterministic tests, and need new progress signals or evaluators.

### Coarseness of step importance

$w_i$ is only a coarse budget signal, not true human utility. The Budget-Only Step Router ablation is required: after removing $w_i$, does performance drop?

### Estimated cost is not realized cost

Before a call, output token counts are unknown, so BudgetFlow can only rank with `expected_cost`, enforce budgets with `reserved_cost`, and report experiments with `actual_cost`.

### KV / prompt caching

Cloud APIs often do not expose raw KV cache. Staying on one model may benefit from provider-side prompt caching or prefix caching, while frequent model switching may lose those benefits. Cross-model KV / cache costs are hard to quantify cleanly because tokenizers, architectures, output lengths, and billing rules differ. We treat this as a threat / future work and do not inject a synthetic switching penalty into the main experiments.

---

## 11. Future Work

### Learned selector

A natural extension replaces BudgetFlow's heuristic ModelSelector with a learned selector, for example borrowing BoPO-style boundary-guided training. This paper first establishes the runtime question itself: whether a workflow ledger, hard-budget reservation, backend admission, and zombie recovery change SWE-bench outcomes under a fixed budget.

### Multi-tenant resource allocation

This paper handles a single budget owner: one researcher or one team holds the total budget and runs many workflows. Multi-team, multi-SLA, multi-priority quota arbitration is the next step.

This mirrors a common evolution in systems work: first make the core mechanism crisp under a single-tenant setting, then add a multi-tenant policy layer. BudgetFlow's first step is to show whether a workflow ledger, budget reservation, and backend scheduling change quality under a fixed budget; multi-tenant agent compute allocation can build on top.

### Agent-native loop

This paper places BudgetFlow between existing agent frameworks and the LLM backend to first prove the value of hard-spend workflow governance. Later, a BudgetFlow-native agent loop can unify tool execution, observations, ledger, ModelSelector, and scheduler into one runtime to reduce integration cost; paper 1 still centers on the budget formulation and runtime contract.

### Cache-aware routing

If a provider or local serving stack exposes cached-token / prefix-cache signals, BudgetFlow can incorporate cache locality into `actual_cost` or a future selector. This paper does not assume direct control over KV cache.

### Non-coding workflows

Customer support, RAG, and scientific reasoning can reuse ledger, reservation, and scheduler machinery, but need new step progress signals. Without a reliable evaluator, do not reuse the SWE-bench progress table verbatim.

Interactive workloads also introduce deadlines, SLA tiers, latency, and throughput goals. The main experiments in this paper focus on batched SWE-bench-style workloads: maximize final resolved rate under a fixed budget; interactive / SLA constraints are natural extensions and should not be silently mixed into the paper-1 objective.

---

## 12. Quick glossary

| Concept | One sentence |
|---|---|
| Turn / Step | one LLM call |
| Workflow | a sequence of LLM calls from task start to finish |
| $w_i$ | a signal for how important the current step is |
| `budget_pressure` | how tight the budget is right now; sets the upgrade threshold |
| `expected_cost` | pre-call estimated cost; used for ranking |
| `reserved_cost` | pre-call reserved cost; used for hard-budget safety |
| `actual_cost` | post-call realized cost; used for reporting experiments |
| Workflow-aware | routing that keeps a workflow ledger, budget level, backend quotas, and step importance |
| Workflow-blind | routing that mostly uses local per-request information without cross-step budget state |
| Workflow-Level Router | pick a model or routing profile once at workflow start |
| Budget-Only Step Router | decide per step using only budget level, ignoring step importance |
| BudgetFlow Full | per-step decisions + budget pressure + step importance + runtime governance |

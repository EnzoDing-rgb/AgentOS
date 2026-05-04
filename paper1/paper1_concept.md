# Spend Tokens Where They Matter: Workflow-Aware Budgeting for LLM Agents

> **One-liner**: BudgetFlow is a runtime layer for concurrent LLM-agent workflows that enforces a hard budget, provider RPM limits, and concurrency slots while using workflow-stage signals to schedule scarce high-capability model calls.

---

## 0. What problem does this paper solve?

Today's LLM agents are usually composed of many model calls. Take SWE-bench as an example: a coding agent reads an issue, searches files, reads code, writes a patch, runs tests, and then iterates using failure logs. Each step consumes shared runtime resources: budget, model slots, provider RPM limits, and queue capacity. At the same time, steps differ in how much they affect the final trajectory: a wrong directory listing is often recoverable, while a wrong root-cause judgment after a test failure can ruin the repair.

Many existing auto-routing systems, such as RouteLLM, CARROT, GPT-5 Auto, and LiteLLM-style routers, mainly answer: "Which model should serve this request?" BudgetFlow asks a different question: when many workflows share one budget and the same backend limits, how should money be allocated across workflow steps and across workflows? This shifts the unit of decision from an isolated request to a stateful batch of agent workflows.

We formalize this as **budget-governed agent execution**:

> **Given many concurrent LLM-agent workflows sharing a global budget, model pool, provider RPM limits, and concurrency slots, how should a runtime admit, queue, downgrade, upgrade, switch, or cancel calls while preserving hard limits and completing more verifiable tasks?**

This problem has three key ingredients:

1. **Hard runtime limits**: the total budget, provider RPM limits, and concurrency slots are given up front, and the runtime must enforce them during execution.
2. **Workflow-stage heterogeneity**: directory browsing, code understanding, traceback analysis, patch generation, and validation place different demands on high-capability model calls.
3. **Shared execution state**: many workflows run concurrently, sharing a global budget, backend model pool, queues, reservations, and failure-recovery mechanisms.

We propose **BudgetFlow**: a training-free, workflow-aware runtime governor for LLM-agent execution. The core systems object of this paper is the full agent workflow and its step sequence under shared runtime constraints, rather than isolated single-call model selection. BudgetFlow tracks where each call sits in the workflow, how budget is reserved and settled, and how backend pressure affects scheduling decisions. It sits at the LLM-call layer, maintains per-workflow ledgers, reserves and settles spend, enforces backend limits, schedules calls across concurrent workflows, and tracks workflow-stage signals. It integrates into existing agent loops via proxy, adapter, or SDK modes for LangChain / SWE-agent / AutoGen.

The core contributions of BudgetFlow are:

1. **Workflow-state-aware upgrade decisions**: BudgetFlow upgrades model tiers when the weighted `expected_progress_gain` per extra dollar is high enough under the current `budget_pressure`, while using workflow-stage signals to estimate which steps matter more.

2. **Hard-budget governance with stop-loss control**: BudgetFlow enforces non-negotiable spend and backend limits through auditable reserve-and-settle accounting, workflow-level admission/scheduling control, and no-progress recovery.

Motivating scenario: a researcher runs 50 SWE-agent instances on SWE-bench Verified with a fixed $50 budget. If each workflow averages 6-12 LLM turns, the batch can create roughly 300-600 LLM calls and a peak near 400 RPM. Without a runtime governor, the batch can hit provider 429s, spend the strong-model budget on early workflows, starve later workflows, or let stuck workflows hold slots.

| BudgetFlow mechanism | What it does in this scenario |
|---|---|
| Governor | Handles the 400 RPM peak with per-backend rate limits and admission control, queues instead of collapsing into 429s, and atomically reserves `reserved_cost` before each call so the $50 hard budget is not exceeded. |
| ModelSelector | Uses `budget_pressure`, `expected_progress_gain`, and explicit or inferred $w_i$ to decide whether to upgrade. High-risk contexts such as test-failure diagnosis are more likely to use stronger models; low-risk directory browsing or search steps are more likely to stay cheap. It chooses from the cost gradient across the backend pool. |
| Scheduler | Shares backend RPM and concurrency slots across 50 agents so healthy workflows can keep making progress under pressure. |
| ZombieDetector | Detects stuck agents, releases their concurrency slots and unused reserved budget, and returns those resources to healthy workflows. |

---

## 1. Core insight: schedule by workflow state

A coding agent on SWE-bench does not call the model once. It reads the issue, searches files, reads code, writes a patch, runs tests, and then iterates on failures. Every step spends tokens, and every step can change whether the final patch passes the harness.

Under a fixed budget, the right question is:

> Which steps are worth spending more money on, and which steps should stay cheap?

Three quantities matter:

| Quantity | Meaning in this paper | Where the signal comes from |
|---|---|---|
| $c_i$ | the realized dollar cost of turn $i$ | provider token bills, or amortized GPU cost per token for local backends |
| $q_i$ | verifiable step progress for turn $i$; this is not a subjective "quality score" | SWE-bench test outcomes, patch apply status, and machine-checkable trajectory signals from agent logs |
| $w_i$ | how important this step is for spending budget well | explicit SDK fields, callback tool metadata, or proxy inference from ToolMessage / Observation text; validated by ablations |

The basic judgment of BudgetFlow is:

> **The same model upgrade can be worth it at one workflow stage and not worth it at another.**

For example:

| Current LLM input | Runtime intuition | Default stage weight |
|---|---|---|
| Directory listings, file trees | low-risk navigation; mistakes are easy to recover from | low |
| Search results, code snippets | requires code understanding; affects later edits | medium |
| Test failures, tracebacks | directly affects root-cause judgment | high |
| Simple verification after a patch is generated | mostly wrap-up or checking | low–medium |

BudgetFlow uses these weights as coarse scheduling signals. The paper tests whether adding workflow-stage state to a hard-limit runtime resolves more tasks and wastes fewer resources than using budget state and reservation size alone.

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
         | Governor: budget + backend limits  |
         +-------------------------------------+
                            |
                            v
      +------------------------------------------+
      | ModelSelector: upgrade score + budget state |
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

The paper scope of BudgetFlow is LLM-call runtime governance: choose models, enforce hard budgets, rate limit, queue, account for reservations, and reclaim stuck workflows. As a runtime layer between the agent framework and the LLM backend, it can attach to existing LangChain / SWE-agent / AutoGen stacks, or serve as an SDK layer for a custom agent platform.

Here, **workflow-aware** means routing and admission decisions use workflow-level state: how much budget remains, how tight each backend's RPM / concurrency slots are, whether the current call sits in a critical stage, and whether the workflow is making progress. By contrast, a **workflow-blind** router mainly relies on local information for a single request—prompt text, token counts, model tier, latency—and can be an excellent one-shot request router, yet without a ledger and cross-workflow scheduling state it is hard to enforce hard limits across a batch of agents.

---

## 3. Runtime decision: buy the most progress per dollar

BudgetFlow's decision intuition is simple: when the budget is limited, first buy the model upgrades that give the largest expected progress per extra dollar.

Imagine many workflows are running at the same time. Before each LLM call, BudgetFlow sees several possible model upgrades: mini to Sonnet, Sonnet to Thinking, or another ordered backend tier. Each upgrade costs extra money and may bring extra useful progress. The right question is not "Is this step important, so should we use the most expensive model?" The right question is:

> For each extra dollar spent on this upgrade, how much more useful progress toward solving the task do we expect to buy?

This is the same intuition as the classic fractional knapsack problem (Dantzig 1957): when capacity is limited, choose items by value per weight. Here, the value is `expected_progress_gain`, and the weight is `extra_cost`. Because workflow steps have different importance, BudgetFlow multiplies the progress gain by a step weight $w_i$. A traceback debugging step usually deserves more weight than a directory browsing step.

BudgetFlow also compares the upgrade score against the current budget state. When the budget is tight, the upgrade must clear a higher bar. When the budget is loose, the bar is lower. This paper calls that bar `budget_pressure`. It has the same unit as the upgrade score: weighted progress per dollar.

This upgrade rule is not the stop condition for a failing workflow. `expected_progress_gain` answers an average question: for this type of step, is moving from one model tier to the next usually worth the extra cost? A separate no-progress signal answers a local question: is this particular workflow looping, repeating failed actions, or spending budget without making observable progress? If so, BudgetFlow should downgrade, queue, cap, or cancel that workflow through the Scheduler / ZombieDetector instead of pretending that the global progress table suddenly became bad.

### 3.1 Upgrade formula

Let the backend pool $A$ contain $N$ backend tiers sorted by expected cost:

$$
a_1 \prec a_2 \prec \cdots \prec a_N
$$

BudgetFlow starts from the cheapest tier $a_1$ and asks one tier at a time: is it worth upgrading from $a_k$ to $a_{k+1}$?

For turn $i$, the estimated progress gain from upgrading one tier is:

$$
\Delta \widehat{\text{progress}}_i^{(k)}
=
\widehat{\text{Progress}}[\text{task\_type}_i, a_{k+1}]
-
\widehat{\text{Progress}}[\text{task\_type}_i, a_k]
$$

The estimated extra cost is:

$$
\Delta \widehat{\text{cost}}_i^{(k)}
=
\widehat{\text{cost}}_i(a_{k+1})
-
\widehat{\text{cost}}_i(a_k)
$$

Plain-language rule:

```text
If: step importance * expected_progress_gain / extra_cost >= budget_pressure
Then: upgrade from the current tier to the next tier
Else: stop at the current tier
```

Mathematical form:

$$
\frac{
  w_i \cdot \Delta \widehat{\text{progress}}_i^{(k)}
}{
  \Delta \widehat{\text{cost}}_i^{(k)}
}
\ge
\text{budget\_pressure}_t
$$

BudgetFlow chooses the highest tier that passes this test. If no upgrade passes the test, the call stays on $a_1$, the cheapest tier.

After ModelSelector chooses a candidate backend, Governor still performs the hard safety check. If the remaining budget cannot cover the `reserved_cost` of the candidate call, BudgetFlow must downgrade, lower the output cap, queue, or reject the call. In short: ModelSelector answers "is this upgrade worth it?" Governor answers "can we safely issue this call?"

| Quantity | Simple meaning | How it is obtained |
|---|---|---|
| $w_i$ | how critical this step is | explicitly passed by SDK, inferred from callbacks, or inferred from ToolMessage / Observation text |
| `expected_progress_gain` / $\Delta \widehat{\text{progress}}_i^{(k)}$ | how much extra useful step progress we expect from upgrading one tier | estimated from historical SWE-bench runs, a calibration split, and sliding updates that give recent samples more weight |
| `extra_cost` / $\Delta \widehat{\text{cost}}_i^{(k)}$ | how much more money the next tier is expected to cost | use `expected_cost` difference for ranking; use `reserved_cost` later for safety; use `actual_cost` for reporting |
| `budget_pressure` | how high the upgrade bar is under the current budget state | initialized from the median or quantiles of the upgrade-score distribution on a calibration split, then updated online: spending too fast raises it, spending too slowly lowers it |

### 3.2 Concrete example

Suppose the current step is a debugging step after a test failure. Historical runs suggest that, for this type of step, Sonnet gives 0.12 more expected progress than mini, and Thinking gives another 0.05 more expected progress than Sonnet. The current `budget_pressure` is 4, meaning: each extra dollar must buy at least 4 weighted progress units to be worth the upgrade.

| Upgrade | Step weight $w_i$ | `expected_progress_gain` | `extra_cost` | Score | Decision |
|---|---:|---:|---:|---:|---|
| mini -> Sonnet | 3 | 0.12 | \$0.04 | $3 \times 0.12 / 0.04 = 9.0$ | upgrade, because $9.0 \ge 4$ |
| Sonnet -> Thinking | 3 | 0.05 | \$0.20 | $3 \times 0.05 / 0.20 = 0.75$ | stop, because $0.75 < 4$ |

Result: this step uses Sonnet, not Thinking.

If the same expected progress gain happened during a low-importance directory browsing step, the step weight might be $w_i = 1$. Then mini to Sonnet scores:

$$
1 \times 0.12 / 0.04 = 3
$$

Because $3 < 4$, BudgetFlow would not upgrade. This is the core behavior: a model upgrade must be both useful and worth its extra cost under the current budget.

The exact numbers are uncertain because no runtime router knows the true future result before making the call. The formula does not require `expected_progress_gain` to perfectly predict the future. It only requires the estimate to be more informative than a random table or a table where every step gets the same value. Section 8 should test this with ablations.

This creates a two-layer control loop. The progress table controls **which upgrades are worth buying on average**. The no-progress / loop signal controls **when to stop spending on this specific workflow**. A stuck workflow can still become a small negative sample for later sliding updates, but it should not immediately rewrite the global `expected_progress_gain` table.

### 3.3 How does BudgetFlow get $w_i$?

$w_i$ is the step-importance weight. It is not a claim that BudgetFlow knows true human utility. It is a coarse runtime signal used to decide where scarce model upgrades are more likely to matter.

BudgetFlow supports five signal levels:

| Level | Integration | Source of $w_i$ | Typical setting |
|---|---|---|---|
| L4 explicit numeric | SDK / self-built platform | `agentos.chat(..., w_i=3.0)` | the platform knows this step is critical planning, debugging, or validation |
| L3 explicit type | SDK / self-built platform | task-type lookup table | planning -> 3, generation -> 2, validation / retrieval -> 1 |
| L2 callback inference | framework adapter | tool event plus observation metadata | LangChain middleware, SWE-agent hook, AutoGen tool event |
| L1 proxy inference | HTTP sidecar | ToolMessage / Observation text in the LLM request | only `base_url` changes; the agent loop does not change |
| L0 budget-only | no usable step signal | $w_i \equiv 1$ | fallback baseline that still uses `budget_pressure` |

Observation-based importance follows one rule: BudgetFlow does not predict what the agent will do next. It only looks at information already present in the current LLM input. Information closer to the final repair decision receives a higher weight; navigation and retrieval receive a lower weight.

| Current LLM input contains | BudgetFlow's interpretation | Default $w_i$ |
|---|---|---:|
| directory or file list | low-risk navigation, usually recoverable | 1.0 |
| search result or source-code snippet | requires code understanding, may affect later edits | 1.5-2.0 |
| test failure or traceback | directly affects root-cause judgment and repair direction | 3.0 |
| test passed or edit complete | usually validation or wrap-up | 1.0-1.5 |

These defaults are only a cold-start prior. The paper must show that they help on held-out tasks, and it must report ablations where the signal becomes weaker: L4 explicit, L2 callback, L1 proxy, and L0 budget-only.

How does BudgetFlow know which tool or observation type the agent used? In proxy mode, it can only see the final content sent to the LLM. If standard tool messages include `name` or `tool_call_id`, BudgetFlow parses them. If the request only contains plain text such as `Observation: ...`, BudgetFlow classifies the observation type with rules or a small classifier. In callback mode, the framework exposes stronger structure: LangChain middleware can read tool-call metadata, SWE-agent hooks can read actions and steps, and AutoGen events can include function names. BudgetFlow turns all of these sources into the same internal record:

```text
TurnInfo(task_type, w_i, workflow_id, step_index, ...)
```

### 3.4 Where does `expected_progress_gain` come from?

`expected_progress_gain` is not calculated from the SWE-bench gold patch or final resolved label during the run. When routing step 2 or step 3, BudgetFlow does not know whether the issue will eventually be solved. It can only ask: in past similar steps, how much more machine-checkable step progress did model tier B bring compared with model tier A?

At runtime, BudgetFlow uses a table estimated before evaluation:

```text
Progress[task_type, model_tier]
```

For each `task_type x model_tier` pair, this table stores the mean observed step-progress outcome from data that is not part of the main test set:

$$
\widehat{\text{Progress}}[\text{task\_type}, a]
=
\text{mean step-progress outcome}
$$

Then the expected gain from upgrading one tier is:

$$
\Delta \widehat{\text{progress}}^{(k)}
=
\widehat{\text{Progress}}[\text{task\_type}, a_{k+1}]
-
\widehat{\text{Progress}}[\text{task\_type}, a_k]
$$

The table can come from three sources:

1. **Held-out calibration split**: use SWE-bench Lite, a disjoint split of SWE-bench Verified, or another calibration set to estimate the table before main evaluation.
2. **Public run logs**: replay existing SWE-bench-style trajectories when they include actions, observations, patch status, and test outcomes.
3. **Online sliding update**: after a step finishes, update the table with the observed step progress, using a small update rate so recent samples matter without letting the current benchmark become the answer key.

```text
Progress <- (1 - alpha) * Progress + alpha * observed_progress
```

Cold start uses a conservative default table: more expensive models are assumed to be no worse than cheaper models, but only slightly better. This prevents the system from upgrading aggressively when it has no evidence. A `zero_calibration` setting should use only this weak default table, so the paper can separate gains from workflow-aware budget pacing and gains from calibrated progress estimates.

---

## 4. How do we enforce hard budgets?

There are three spend-accounting notions; do not mix them.

### 4.1 `expected_cost`: pre-call estimate

Before a call, input token counts are known exactly because the prompt / messages have already been built. Output token counts are unknown, so output length is estimated from historical means or rolling averages for the current task type and model.

$$
\text{expected\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \widehat{\text{output\_tokens}} \cdot p_{\text{out}}
$$

This is used only to estimate `extra_cost` when comparing model tiers. After the call, actual token usage can update the rolling averages, but `expected_cost` is not the safety mechanism for hard budgets.

### 4.2 `reserved_cost`: pre-call reservation

To enforce a hard budget, the runtime cannot rely on average output length alone. Before issuing a call, BudgetFlow reserves budget using a controllable upper bound:

$$
\text{reserved\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \text{max\_output\_tokens} \cdot p_{\text{out}}
$$

Here, `max_output_tokens` must be enforced by the provider or local serving engine. If the remaining budget cannot cover the reserved cost, the system must downgrade the model, lower the output cap, queue, or reject the call. This is what makes the budget guarantee hard rather than predictive.

### 4.3 `actual_cost`: post-call settlement

After a call completes, settle using the true token counts returned by the provider or local serving logs:

$$
\text{actual\_cost}
= \text{actual\_input\_tokens} \cdot p_{\text{in}}
+ \text{actual\_output\_tokens} \cdot p_{\text{out}}
$$

If `actual_cost < reserved_cost`, the difference is returned to the global budget. Under concurrency, reservation and settlement must be atomic: dispatch moves budget from `available_budget` to `reserved_budget`; completion moves true usage to `spent_budget` and returns the unused remainder. This prevents 50 workflows from overspending by reading the same remaining budget at the same time.

In short: `expected_cost` is for routing order, `reserved_cost` is for budget safety, and `actual_cost` is for accounting and experimental reporting.

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

> Under the same hard budget and backend limits, how many more SWE-bench Verified tasks does BudgetFlow resolve compared to baselines, while avoiding budget and rate-limit violations?

### 5.3 Online scheduling signals vs offline analysis signals

Section 3's upgrade decision uses only runtime-visible signals and predeclared calibration tables. These signals need not prove that the task is solved; they only help the scheduler estimate `expected_progress_gain`, $w_i$, and whether an upgrade is worth its extra cost.

Runtime-visible signals:

| Signal | How to compute it | Use |
|---|---|---|
| Workflow stage | classify from tool name, adapter metadata, or message / observation text | estimate $w_i$ |
| Observation type | detect code snippets, search results, tracebacks, test failures, patch errors | estimate task type and expected progress gain |
| Patch apply status | dry-run the current patch in a sandbox | repair / generation stages |
| Test failure text | parse failing test names, traceback length, repeated failures | validation / debugging stages |
| Retry / loop signal | count repeated actions, repeated file opens, unchanged patches, or repeated test failures | downgrade, queue, or cancel stalled workflows |
| Ledger and queue state | read reserved budget, actual usage, queue wait, remaining RPM space, concurrency slots | update `budget_pressure` and enforce admission |

Offline analysis signals are used only for calibration, ablation, and case studies:

| Signal | How to compute it | Use |
|---|---|---|
| Whether files touched by the gold patch were opened | compare visited paths in the agent trajectory against changed files in the gold patch | post-hoc localization analysis |
| Whether failing-test count decreases on the official tests | run the benchmark harness after the trajectory | evaluation and case studies |
| thought/action/observation in `.traj` | SWE-agent writes each step's reasoning, tool calls, and tool returns into `<task_id>.traj` JSON | post-hoc alignment of scheduling decisions and outcomes |

Gold patches and final benchmark labels must not enter the online scheduler. They are allowed only after the run, when explaining why a scheduling decision helped or failed. The main results table reports task outcomes and systems metrics, not a learned or subjective step-quality score.

### 5.4 Why do we need a held-out calibration split?

Here we must avoid a subtle circularity.

Section 1 includes a stage-weight table (traceback ranks above directory browsing, and so on). These weights may need light tuning from data. The `expected_progress_gain` table and initial `budget_pressure` also need a calibration scale.

The problem is: **if we tune stage weights on all 500 SWE-bench Verified tasks and then report resolved rate on the same 500 tasks, that is like studying with the answer key and then taking the same exam.** Any apparent gain may be overfitting.

The fix is to split data:

- **Calibration split**: used to tune stage weights, estimate `expected_progress_gain`, and initialize `budget_pressure`. This can be data outside SWE-bench Verified, for example samples from the original SWE-bench that never entered Verified, or the non-overlapping portion of SWE-bench Lite relative to Verified.
- **Evaluation split**: the full SWE-bench Verified 500 tasks, **never touched during tuning**. Final paper numbers for resolved rate, budget violations, quota violations, queue latency, and recovery metrics are reported only on this half.

"Held-out" means "set aside and untouched"—lock the evaluation split until all design decisions are finalized, then open the box.

If a BudgetFlow variant truly needs no tuning (for example, stage weights always follow a fixed default table end-to-end), then strictly speaking no calibration split is required. For honesty, this paper assumes some tuning is likely and declares this split protocol up front.

---

## 6. System comparisons and variants

### 6.1 Workflow-Level Router

At workflow start, pick one model or routing profile based on the initial issue / prompt / repository context, and keep that choice for the entire workflow.

It answers:

> Is choosing a model only once at task start enough?

This is the most important comparison because many routing systems in practice are request-level or task-level.

### 6.2 Budget-Only Step Scheduler

It also decides per step and enforces hard limits, but ignores workflow stage and observation types.

It only looks at:

- `reserved_budget / total_budget`
- `settled_budget / total_budget`
- `completed_tasks / total_tasks` or batch progress
- the current call's `expected_cost` / `reserved_cost`

This is equivalent to removing stage weights and the `expected_progress_gain` table from the BudgetFlow scheduler:

```text
Only budget level and reservation size; ignore workflow stage and expected progress gain.
```

It answers:

> Does the gain come only from budget pacing, or do we need workflow-stage state for scheduling?

### 6.3 BudgetFlow Full

The full system includes:

- per-step routing;
- `budget_pressure`;
- stage weights;
- `expected_progress_gain`;
- a workflow ledger;
- hard-budget reservation;
- backend admission control;
- zombie recovery.

It answers:

> Under the same hard budget and backend limits, does workflow-state-aware scheduling resolve more SWE-bench tasks than workflow-level routing and budget-only step scheduling?

### 6.4 BudgetFlow Cache-Sticky

This variant keeps BudgetFlow's workflow-stage scheduling, but adds one cache-aware rule:

```text
Switch models only if upgrade_score - switch_penalty >= budget_pressure.
```

The `switch_penalty` is the expected cost of losing prefix-cache locality. In local A800 experiments, it can come from measured prefill overhead or cached-token loss when vLLM / SGLang / TensorRT-LLM exposes those signals. If the backend hides cache details, the paper can sweep several synthetic penalty values and show when switching still helps.

It answers:

> Even when switching models reduces prefix-cache locality, can workflow-stage scheduling still bring a net gain?

---

## 7. Multi-workflow runtime

The main scenario of this paper is batched SWE-bench evaluation:

> 50 SWE-agent instances run SWE-bench Verified concurrently, sharing a budget such as \$50, while respecting provider RPM limits and concurrency slots.

The target users are people who build agents and teams who operate agent platforms: maintainers of open-source agent frameworks, in-house agent product teams, internal LLM gateway operators for a single team, and researchers who need reproducible evaluation harnesses. This paper focuses on a single budget owner plus many concurrent workflows; multi-team, multi-SLA, multi-budget-pool quota arbitration is future work.

Under this setting, BudgetFlow handles five runtime questions on each LLM call:

1. Can the global budget reserve this call?
2. Is the weighted `expected_progress_gain` per extra dollar high enough under the current `budget_pressure`?
3. Does the target backend still have RPM / concurrency capacity?
4. If there is no slot, should we queue, downgrade, switch backends, or reject?
5. If a workflow is stuck, how do we release reserved budget and concurrency slots?

This runtime governance places per-call model selection inside an executable system environment: reservations must be atomic, completed calls must settle and return unused budget, backend limits must be honored, and stuck workflows must release resources. This keeps the main thread anchored on agent workflow runtime governance.

Key BudgetFlow components:

| Component | Role |
|---|---|
| Ledger | records per-workflow reservation, realized spend, and state |
| Governor | atomic budget reservation, settlement, and backend rate limiting |
| ModelSelector | chooses model tiers using $w_i$, `expected_progress_gain`, `extra_cost`, and `budget_pressure` |
| Scheduler | admits, queues, downgrades, or switches backends under RPM / concurrency limits |
| ZombieDetector | cancels no-progress workflows and reclaims budget and slots |

---

## 8. Experimental design

### 8.1 Workload

- Benchmark: SWE-bench Verified;
- Agent scaffold: SWE-agent or mini-SWE-agent; keep one choice for the whole paper;
- Concurrency: `J = 1 / 10 / 50 / 100`;
- Budget: e.g., `B_total = $50`, and report curves across budget levels;
- Backend pool: may include API models and local models, but the claim should not hinge on specific model names.

### 8.2 Research questions

| RQ | Question | Metrics |
|---|---|---|
| RQ1 | When many agent workflows run under one fixed budget and shared backend limits, where is budget wasted and which runtime limits are hit? | budget violations, 429 rate, queue latency, recovered budget, cancelled zombies |
| RQ2 | Under the same budget, does using workflow-stage state to choose model tiers resolve more SWE-bench tasks than workflow-level or budget-only scheduling? | resolved rate @ fixed budget, BudgetFlow Full vs Workflow-Level Router vs Budget-Only Step Scheduler |
| RQ3 | Even when model switching reduces prefix-cache locality, can workflow-stage scheduling still bring a net gain? | model-switch rate, prefill latency, cached-token ratio, BudgetFlow Full vs BudgetFlow Cache-Sticky |

### 8.3 Primary metrics

| Metric | Meaning |
|---|---|
| Resolved rate @ fixed budget | how many SWE-bench tasks are resolved under the same budget |
| Budget violation rate | whether the hard budget is exceeded |
| 429 rate | whether provider RPM limits are hit |
| p50/p99 queue latency | queuing delay |
| Admission throughput | admitted calls per minute under shared backend limits |
| Recovered budget | budget returned from stuck workflows |
| Wasted reservation ratio | reserved budget that never becomes useful completed work |
| Model-switch rate | how often a workflow changes model tier or backend |
| Prefill / cache overhead | extra prefill latency or lower cached-token ratio after switching models |
| Efficiency metric | spend per resolved task, reported as secondary context |

### 8.4 Ablations

The ablations should stay focused on where the gain comes from:

1. **Step importance**: compare budget-only routing with $w_i \equiv 1$, random weights, simple task-type weights, and BudgetFlow Full.
2. **Progress table**: compare uniform `expected_progress_gain`, random progress gain, `zero_calibration` with only a conservative default table, and calibrated progress gain.
3. **Stop-loss control**: compare BudgetFlow Full with and without no-progress / ZombieDetector logic, reporting wasted budget, recovered budget, queue latency, and resolved rate.
4. **Signal robustness and transfer**: compare SDK / explicit signals, callback inference, proxy inference, and budget-only fallback; calibrate on one split or benchmark and test on a disjoint domain such as SWE-bench Verified or RepoBench.

If calibrated progress gain beats uniform and random tables under the same fixed budget, the result supports the claim that historical step progress is useful for runtime budget allocation. If `zero_calibration` is close to calibrated performance, the gain mainly comes from workflow-aware budget pacing rather than the progress table.

---

## 9. Related Work

### Request and workflow-level model routing

RouteLLM, CARROT, OmniRouter, LiteLLM auto-router, and related work choose models for a single request or for a task-level routing profile. They can be strong engineering tools, but they typically do not maintain per-workflow ledgers, coordinate a shared budget across many concurrent agents, or use mid-trajectory observations as scheduling state.

The comparison question of this paper is:

> For multi-step agent workflows like SWE-bench, is request- or workflow-level routing enough without runtime budget governance?

### LLM serving and workflow orchestration

ATHENA-Serve, Parrot, Aragog, Murakkab, Autellix, and Helium are all helpful to BudgetFlow because they show that agentic LLM workloads are a real serving / orchestration problem: requests differ in length, workflows differ by stage, backends have KV cache, batching, concurrency, RPM, SLOs, and tail-latency pressure.

These systems mainly give BudgetFlow two classes of insight:

1. **Serving layer can be smarter**: ATHENA-Serve maps generation horizons into KV / compute budgets and uses hierarchical RL for admission, batching, and concurrency control. Autellix and Helium likewise argue that workflow-aware serving reduces head-of-line blocking and improves throughput and tail latency.
2. **Runtime layer should expose structure**: Parrot's semantic variables, Aragog's just-in-time routing, and Murakkab's workflow orchestration all show that structural workflow information can enter runtime decisions, so each prompt carries step context and workflow state into the system layer.

BudgetFlow uses these conclusions as systems context: agent runtimes should understand workflows, and backend scheduling affects latency, throughput, and budget pressure. Its boundary is different. Workflow-aware serving systems mainly decide how to execute admitted requests efficiently: batch them, reuse KV cache, reduce head-of-line blocking, or meet SLOs. Workflow orchestration systems mainly decide how to configure and run a program or workflow. BudgetFlow sits one layer above the serving engine: before each LLM call is sent, it checks the shared budget, the workflow ledger, backend limits, and the current workflow stage; after the call, it settles actual usage and returns unused budget. ATHENA / Autellix / Helium-style systems can still execute the admitted requests below BudgetFlow.

### Agent runtime / resource governance

AgentRM, AgentCgroup, AIOS, and related work focus on resource management, isolation, or stability for agent systems. BudgetFlow is narrower in scope and deeper at the LLM-call boundary: it keeps a budget ledger for each workflow, reserves budget before a call, settles actual usage after the call, chooses model tiers using $w_i$, `expected_progress_gain`, `extra_cost`, and `budget_pressure`, and releases budget and slots from stalled workflows. The paper evaluates whether these runtime decisions improve verified task completion under the same budget.

### Learned agent routing policies

BoPO establishes that step-level model routing for long-horizon agents is a real research problem. It trains a learned router with reinforcement learning and studies success under constrained model budgets on ALFWorld, SciWorld, and AppWorld.

BudgetFlow treats learned selection as a policy module that can sit inside the ModelSelector. The paper's main systems question is the runtime around that policy: keep ledger state, reserve budget, admit calls under backend limits, schedule model tiers, settle actual usage, and recover resources when many workflows execute concurrently.

---

## 10. Threats to Validity

### SWE-bench scope

This paper only claims applicability to coding-agent workflows with verifiable intermediate signals. Customer support, creative writing, and scientific reasoning lack gold patches and deterministic tests, and need new runtime step scores or evaluators.

### Coarseness of stage weights

Stage weight is only a coarse scheduling signal. The Budget-Only Step Scheduler ablation is required: after removing stage and observation state, does performance drop?

### Estimated cost is not realized cost

Before a call, output token counts are unknown, so BudgetFlow can only rank with `expected_cost`, enforce budgets with `reserved_cost`, and report experiments with `actual_cost`.

### KV / prompt caching

Frequent model upgrades or downgrades can reduce prefix-cache reuse. For coding agents, prompts often carry long issue descriptions, file snippets, and previous observations, so extra prefill latency or lower cached-token reuse can offset the benefit of better model placement. BudgetFlow should therefore measure this effect rather than only list it as a threat.

The main SWE-bench experiments can run on API models or another stable backend, but the cache study should use controlled local serving on an A800-class GPU when possible. With vLLM, SGLang, or TensorRT-LLM, the experiment can enable prefix caching and report model-switch rate, cross-model transition counts, TTFT / prefill-like latency, GPU memory pressure, and cached-token ratio when the backend exposes it. It should compare BudgetFlow Full with **BudgetFlow Cache-Sticky**, which stays on the current model unless the scheduling gain is large enough to pay for the expected switching penalty. If exact cache signals are unavailable, the paper should report TTFT / latency and include a sensitivity curve that adds synthetic switching penalties.

---

## 11. Future Work

### Multi-tenant resource allocation

This paper handles a single budget owner: one researcher or one team holds the total budget and runs many workflows. Multi-team, multi-SLA, multi-priority quota arbitration is the next step.

This mirrors a common evolution in systems work: first make the core mechanism crisp under a single-tenant setting, then add a multi-tenant policy layer. BudgetFlow's first step is to show whether a workflow ledger, budget reservation, backend admission, and scheduling improve agent execution under hard shared limits; multi-tenant agent compute allocation can build on top.

### SLA-aware scheduling

Interactive agent workloads introduce deadlines, SLA tiers, latency SLOs, and throughput goals. BudgetFlow can extend its scheduler to combine budget caps with latency classes, deadline-aware admission, and priority isolation across workflow groups.

### Learned selector as a plug-in

A learned selector, for example borrowing BoPO-style boundary-guided training, can replace or refine the heuristic ModelSelector. The ledger, reservation, admission, scheduling, settlement, and recovery mechanisms remain the runtime substrate around that learned policy.

### Non-coding workflows

Customer support, RAG, and scientific reasoning can reuse ledger, reservation, and scheduler machinery, but need new workflow-stage signals and evaluators. Without a reliable evaluator, do not reuse the SWE-bench stage table verbatim.

The main experiments in this paper focus on batched SWE-bench-style workloads: maximize final resolved rate under a fixed budget while enforcing provider and concurrency limits. Interactive / SLA constraints are natural extensions and should not be silently mixed into the paper-1 objective.

---

## 12. Quick glossary

| Concept | One sentence |
|---|---|
| Turn / Step | one LLM call |
| Workflow | a sequence of LLM calls from task start to finish |
| Stage weight | coarse scheduling weight for the current workflow stage |
| `expected_progress_gain` | estimated extra useful progress from upgrading one model tier |
| Runtime state | remaining budget, remaining RPM space, concurrency slots, and queue pressure |
| `budget_pressure` | current upgrade bar; higher when the budget is tight and lower when budget is available |
| `expected_cost` | pre-call estimated cost; used for ranking |
| `reserved_cost` | pre-call reserved cost; used for hard-budget safety |
| `actual_cost` | post-call realized cost; used for reporting experiments |
| Workflow-aware | routing that keeps a workflow ledger, budget state, backend limits, stage weights, and expected progress estimates |
| Workflow-blind | routing that mostly uses local per-request information without cross-step budget state |
| Workflow-Level Router | pick a model or routing profile once at workflow start |
| Budget-Only Step Scheduler | decide per step using only budget state, ignoring workflow stage and observation type |
| BudgetFlow Full | per-step upgrade decisions + stage weights + `expected_progress_gain` + `budget_pressure` + runtime governance |

# BudgetFlow: Related Work and Positioning Memo (updated 2026-05-04)

This memo follows `paper1_concept.md`. The core of the current paper is to propose and validate a **budget-governed agent execution** problem:

> Given many concurrent LLM-agent workflows sharing a global budget, model pool, provider RPM limits, and concurrency slots, how should a runtime admit, queue, downgrade, upgrade, switch, or cancel calls while preserving hard limits and completing more verifiable tasks?

The headline metrics should center on **SWE-bench Verified `resolved @ fixed budget`**, budget violations, 429 rate, queue latency, admission throughput, and recovered budget. The systems contributions should center on **workflow-state-aware scheduling + hard reservation / settlement + multi-workflow runtime governance**.

## 0. Bottom line first

The safest, most contribution-forward statement is:

> BudgetFlow formulates and implements workflow-aware budgeting for multi-step LLM agent workflows: a runtime uses workflow-stage signals and shared budget state to schedule model calls across concurrent tasks, while a ledger enforces hard budget, RPM, and concurrency limits.

This formulation is stronger than framing the paper as only a "training-free router." `training-free` is a method property and should not be the sole contribution. The real contribution is putting budget, workflow-stage state, a concurrent runtime ledger, backend limits, and verifiable task success into one systems problem statement.

## 1. A positive problem definition for this paper

| Dimension | BudgetFlow's choice |
|---|---|
| Resources | token / dollar spend, plus provider RPM limits and concurrency slots |
| Unit | one LLM step inside a workflow |
| State | workflow ledger, global budget level, workflow stage, backend limits |
| Decision | for the current step: cheap model, strong model, downgrade, queue, switch backend, or reject |
| Method | training-free scheduling priority using stage weight, online signal, runtime headroom, and reserved cost |
| Hard-budget mechanism | `expected_cost` for ranking, `reserved_cost` for admission, `actual_cost` for settlement |
| Headline metrics | SWE-bench Verified `resolved @ fixed budget`, budget violations, 429 rate, queue latency, recovered budget |

One-sentence version:

> BudgetFlow spends stronger model calls where workflow-stage evidence suggests they matter most, while a shared ledger keeps the whole batch inside a hard budget and backend limits.

## 2. Which papers are real threats, and which are actually helpful?

| Category | Representative papers | Threat to BudgetFlow | Help to BudgetFlow |
|---|---|---:|---|
| RL agentic routing | Budget-Aware Agentic Routing / BoPO, xRouter | high | establishes step-level agent routing as a real problem; can be a future learned selector |
| Per-query / task router | RouteLLM, CARROT, OmniRouter | medium | provides request-level router baselines; can plug into BudgetFlow's ModelSelector |
| Serving scheduler | ATHENA-Serve | medium | reminds us not to claim "a scheduler" as the sole novelty; good backend serving-layer contrast |
| Workflow-aware serving | Aragog, Helium, Autellix | low–medium | shows workflow-aware runtimes matter; can stack under / alongside BudgetFlow |
| Workflow orchestration | Murakkab | low–medium | shows cloud workflow orchestration is a systems problem; helps position BudgetFlow as a narrow integration layer |
| Programming / semantic serving | Parrot | low | shows LLM apps have structure and program semantics; helps justify richer step context |
| Infrastructure measurement | The Cost of Dynamic Reasoning | low | motivation: agent test-time scaling makes cost governance a first-class systems issue |
| Agent OS / resource isolation | AgentRM, AgentCgroup, AIOS, pMVX | low | background that agent runtimes need resource governance |

## 2.1 Boundary against workflow-aware systems

BudgetFlow should not sell itself as the first system to use workflow structure. The stronger claim is more specific: it uses workflow state to decide **whether a call can run under a shared budget, which model tier it should use, and how budget is reserved, settled, and recovered across many concurrent workflows**.

| System line | What it mainly provides | BudgetFlow's different role |
|---|---|---|
| ATHENA / Helium / Autellix-style serving | batching, KV/cache reuse, tail latency, throughput, HoL reduction | BudgetFlow decides which calls are admitted and which model/backend candidates to send down |
| Parrot / Murakkab / Aragog-style workflow systems | application structure, workflow configuration, just-in-time routing or orchestration | BudgetFlow keeps a per-workflow budget ledger and ties model choices to a hard shared budget |
| AgentRM / AgentCgroup / AIOS-style managers | resource isolation, stability, broad agent runtime control | BudgetFlow focuses on the LLM-call boundary: reservation, settlement, backend limits, and stalled-workflow recovery |

Simple positioning sentence:

> BudgetFlow is the layer that checks budget and workflow state before each LLM call is sent; workflow-aware serving systems can still execute the admitted calls below it.

## 3. Closest competitors

### 3.1 Budget-Aware Agentic Routing / BoPO

This is the closest research neighbor because it also studies model routing across multi-step agent trajectories under constrained budgets.

| Dimension | BoPO-style work | BudgetFlow |
|---|---|---|
| Approach | learned routing policy / RL | training-free runtime rule |
| Decision object | model choice along an agent trajectory | workflow-stage scheduling + runtime admission |
| Budget | budget-aware reward / constraints in training and inference | runtime hard budget with reservation |
| Interpretability | policy comes from training | stage weight, online signal, runtime headroom, and reserved cost are auditable |
| System state | focuses on routing policy | workflow ledger, global budget, backend RPM, concurrency slots |
| How this paper uses it | related work + future learned selector | paper-1 mainline |

Concrete adjustments for this paper:

- Write the contribution as **problem formulation + concrete runtime behavior**, not only as a "heuristic router."
- Keep `Workflow-Level Router`, `Budget-Only Step Scheduler`, and `BudgetFlow Full` in experiments; use ablations to show gains come from workflow-stage state and runtime budget governance.
- Future work: a BoPO-style learned selector can replace `ModelSelector`, while ledger, reservation, settlement, and governor remain the runtime core.

### 3.2 xRouter

xRouter is an RL / tool-calling router line. The threat is mostly methodological, not at the full-system layer. BudgetFlow's line of defense is hard-budget enforcement, SWE-bench verified outcomes, a multi-workflow ledger, and training-free deployability.

## 4. ATHENA-Serve: important related work, but belongs in Related Work

ATHENA-Serve deserves careful writing, and it fits naturally in related work.

| Dimension | ATHENA-Serve | BudgetFlow |
|---|---|---|
| Core problem | LLM serving under bursty traffic | budget-governed agent execution |
| Meaning of "budget" | KV-cache / compute / concurrency resource envelope | hard token / dollar budget |
| Objective | tail latency, SLO violations, HoL blocking | verified task success under fixed budget |
| Method | horizon-cost prediction + hierarchical RL scheduling | training-free priority rule + workflow ledger |
| Workload | ShareGPT-like online serving traces (confirm in the paper) | SWE-bench Verified coding workflows |
| Role in this paper | serving-layer related work / reviewer warning | paper-1 mainline |

Key reminders from ATHENA for this paper:

- Runtime schedulers, admission control, and concurrency governance are active systems directions.
- Write Governor / Scheduler as necessary support for a hard-budget runtime, and put the primary novelty on workflow-state-aware budget governance.
- ATHENA-style reviews show that if you introduce RL, reviewers will ask whether RL is necessary; BudgetFlow's training-free choice can be turned into a crisp advantage.

A sentence that can go into related work:

> ATHENA-Serve maps predicted generation horizons to KV/compute budgets and schedules requests for tail-latency control. BudgetFlow uses a hard budget over agent workflows; it decides which workflow stages should receive stronger model calls to improve verified task success under that budget. These layers are complementary: an ATHENA-like scheduler can execute admitted requests below a BudgetFlow-style runtime governor.

## 5. The seven papers in Scratch.md: what they solve, how they connect to BudgetFlow (with links)

Aligned with `paper1/scratch.md` lines 417–479. Each row states the problem the paper targets on its own terms, then how BudgetFlow should use it in motivation or related work.

| Paper | Link | Problem it targets | Connection to BudgetFlow |
|---|---|---|---|
| The Cost of Dynamic Reasoning | [arXiv:2506.04301](https://arxiv.org/abs/2506.04301) | system-level characterization of multi-turn agent reasoning and test-time scaling across resource use, latency, energy, and datacenter power, plus design tradeoffs in accuracy vs cost | motivation for BudgetFlow: agent workflow budget use deserves systems study; BudgetFlow supplies runtime budget governance with SWE-bench `resolved` evidence |
| Parrot | [arXiv:2405.19888](https://arxiv.org/abs/2405.19888) | expose application-level structure (Semantic Variables) to public LLM services and optimize end-to-end performance via cross-request dataflow analysis | supports BudgetFlow's input-signal design: structured step / tool / observation context can enter budget decisions; BudgetFlow still centers on a hard-budget ledger and `resolved @ fixed budget` |
| Aragog | [arXiv:2511.20975v1](https://arxiv.org/abs/2511.20975v1) | agentic workflows are expensive at scale; adapt configuration across execution using fresh system observations to raise throughput and cut latency while matching the accuracy of the most expensive configuration | closest serving-side neighbor: shared intuition of "runtime re-decision inside workflows"; BudgetFlow's spine is **fixed budget**, workflow-stage scheduling, and verified task success—treat Aragog as a backend routing-layer contrast |
| Murakkab | [arXiv:2508.18298](https://arxiv.org/abs/2508.18298) | declaratively decouple workflow specs from execution configs and co-optimize accuracy, latency, energy, and cost under SLOs across the stack | supports the trend that workflow structure belongs in the system layer; BudgetFlow takes a narrower interface—budget governance at the LLM-call layer—while full-stack orchestration stays with Murakkab-like systems |
| Autellix | [arXiv:2502.13965](https://arxiv.org/abs/2502.13965) | treat agent programs as first-class and exploit program/call dependencies to reduce HoL and end-to-end program latency | supports a stacking story: Autellix optimizes program-level execution efficiency; BudgetFlow optimizes **program success under a fixed budget**; a plausible stack is BudgetFlow → Autellix → vLLM-class backends |
| ATHENA-Serve | [OpenReview](https://openreview.net/forum?id=GULnhNbvb9) | map predicted horizons to KV/compute budgets and schedule admission/batching/concurrency with hierarchical RL to control tail latency and HoL under bursty load | serving-scheduler related work; reminds us the headline contribution should be budget-governed agent execution, with Governor/Scheduler as supporting machinery |
| Helium (arXiv title: Efficient LLM Serving for Agentic Workflows) | [arXiv:2603.16104v1](https://arxiv.org/abs/2603.16104v1) | model agentic workflows as query plans and schedule across calls with cache-aware reuse | supports the necessity of workflow-aware serving; BudgetFlow emphasizes **hard budget and workflow-stage state**, while cache/operator-level optimization can be future work or backend collaboration |

## 6. New papers: keep, downplay, and leverage (expanded notes)

### The Cost of Dynamic Reasoning

Role: helpful motivation paper.

It stresses that agent / test-time scaling creates real infrastructure costs. This paper can cite it to argue that budget governance for agent reasoning is already a systems problem. It typically does not ship a workflow-stage-aware hard-budget runtime, so threat level stays low.

### Parrot

Role: helpful programming / serving paper.

Parrot's semantic variables show LLM applications are not isolated prompts; they have program structure and variable dependencies. BudgetFlow can use this to justify putting workflow steps, tool observations, tracebacks, and patch state into budget decisions. Threat level is low because the primary objective is serving / application execution efficiency rather than verified task success under a fixed budget.

### Aragog

Role: helpful, but needs careful positioning.

Aragog's just-in-time model routing for agentic workflows shares the intuition of "runtime model choice inside workflows" and may be the closest new system to BudgetFlow.

How this paper should position itself:

- Aragog reads more like a serving/runtime-layer just-in-time router;
- BudgetFlow centers on a hard budget, workflow-stage state, ledger reservation, and `resolved @ fixed budget`;
- if Aragog uses rule-like or hard-coded policies, that also supports a training-free story: systems papers can ship interpretable runtime policies without putting RL in paper-1 mainline.

Facts to confirm: venue, benchmarks, headline gains, and whether it optimizes under a fixed budget.

### Murakkab

Role: helpful workflow orchestration paper.

Murakkab shows agentic workflow orchestration in cloud platforms can improve resource efficiency. It helps because it argues workflow structure belongs in the system layer, which top venues care about.

Avoid competing for the "workflow orchestration platform" headline. Paper 1 stays narrower: budget governance between the existing agent loop and the LLM backend.

Facts to confirm: venue, datasets, headline numbers, and whether it includes cost-under-SLO objectives.

### Autellix

Role: helpful serving-engine paper.

Autellix treats LLM agents as general programs and argues agent execution needs a program-aware serving engine. BudgetFlow can sit above it: BudgetFlow decides per-step budget reservation / model / admission; an Autellix-class engine executes programmatic agent requests efficiently.

Risk to address in related work: if Autellix also does workflow-aware routing, explain clearly that it optimizes engine efficiency / HoL / throughput, while BudgetFlow's headline metric is task success under a fixed budget.

### Helium

Role: helpful workflow-aware serving paper.

Helium supports the premise that workflow-aware serving is a sound direction. Use it to strengthen the "workflow state matters" premise. Threat level depends on whether it includes a hard budget and a task-success objective; if it mainly optimizes serving efficiency, treat it as a stackable backend layer.

### ATHENA-Serve

Role: important related work + reviewer-risk reminder.

ATHENA shows resource budgets, horizon prediction, and hierarchical RL schedulers are already serious research. Absorb its review lessons: report p99 / violations / overhead, include strong heuristic baselines, and explain the value of a training-free policy clearly.

It reinforces BudgetFlow's positive framing: BudgetFlow's question is workflow-aware budget governance for agent execution.

## 6.1 KV cache and model-switching risk

This is a serious systems risk, not a minor caveat. Coding-agent prompts can be long and repetitive. If BudgetFlow frequently switches between model tiers or providers, it may lose prefix-cache reuse, increase prefill latency, and waste memory. A reviewer can fairly ask whether the scheduling gain survives this backend cost.

Required experiments:

1. Report model-switch rate per workflow and a cross-model transition matrix.
2. Run a controlled local serving study on A800 with vLLM / SGLang / TensorRT-LLM when possible.
3. Measure TTFT / prefill-like latency, GPU memory pressure, and cached-token ratio when the backend exposes them.
4. Compare BudgetFlow Full with **BudgetFlow Cache-Sticky**: switch models only when `new_priority - current_priority >= switch_penalty`.
5. Add a sensitivity curve with synthetic switching penalties when the backend hides exact cache details.
6. Report resolved rate under fixed budget together with latency / cache overhead, not only task success.

Positioning sentence:

> BudgetFlow should treat cache locality as runtime state: staying on the current model can receive a small bonus, and switching models can require a higher scheduling threshold.

## 7. What to do with papers from the old comparison table

| Paper | Keep? | Where | Why |
|---|---|---|---|
| RouteLLM | yes | per-query router baseline | classic strong/weak routing background |
| CARROT | yes | per-query cost-aware router | cost-aware, but usually not a workflow ledger |
| OmniRouter | yes | constrained per-query / global routing | useful optimization-view baseline |
| Budget-Aware Agentic Routing / BoPO | strong yes | closest competitor | multi-step + cost/success + RL |
| xRouter | yes | RL routing related work | methodological neighbor |
| AgentRM | weak yes | runtime governance background | stability resources, not the spend-allocation spine |
| AgentCgroup | weak yes | OS / resource isolation background | OS isolation context |
| AIOS | weak yes | broad agent OS background | conceptual background; cite lightly |
| pMVX | weak yes | agent OS self-tuning background | parallel work; cite lightly |

## 8. RL / ML usage snapshot

| Paper bucket | Uses RL/ML? | This paper's stance |
|---|---|---|
| BoPO / xRouter | yes, core method | closest related work; future learned selector |
| ATHENA-Serve | yes, hierarchical RL + predictor | serving related work; absorb review lessons |
| RouteLLM / OmniRouter / CARROT | often uses learners or statistical predictors | per-query baselines or components |
| Aragog / Murakkab / Autellix / Helium | confirm per paper; may mix rules, optimization, or learning | systems-layer contrasts; do not hinge the story only on "ML vs no ML" |
| BudgetFlow paper 1 | training-free mainline | learned selector belongs in future work / pluggable extension |

A crisp sentence you can reuse:

> BudgetFlow's ModelSelector is a plug point. Paper 1 uses a training-free auditable rule to isolate the value of the runtime design. A learned selector can replace this rule later, while the ledger, reservation, settlement, and governor stay the same.

## 9. How to strengthen the paper for a top venue

A problem definition reviewers are more likely to accept:

> We identify budget-governed agent execution as a systems problem: model routing, budget accounting, and backend admission must be decided together when many agent workflows share a fixed budget.

Experiments to strengthen:

1. **RQ1: Budgeted execution problem**: under concurrent agent execution, report where budget is wasted and which limits are hit: budget violations, 429s, queue latency, recovered budget, cancelled zombies.
2. **RQ2: Workflow-stage scheduling value**: under the same budget, compare Workflow-Level Router, Budget-Only Step Scheduler, BudgetFlow Full, and BudgetFlow Cache-Sticky on `resolved @ fixed budget`.
3. **RQ3: Cache-aware model switching**: use local A800 serving to test whether workflow-stage model switching still brings net gain after prefix-cache / prefill costs.
4. **Heuristic strength**: tune Budget-Only and Workflow-Level baselines strongly to avoid strawman critiques.
5. **Overhead**: report BudgetFlow routing / accounting / scheduling overhead.
6. **Generalization note**: main results on SWE-bench; other domains need new progress signals; the reusable claim is ledger + hard reservation + workflow-stage-aware scheduling.

## 10. Final positioning

The niche statement should read:

> BudgetFlow is a training-free runtime for workflow-aware budgeting in multi-step LLM agent workflows. It schedules stronger model calls across workflow steps and concurrent tasks using auditable stage signals, while a shared ledger enforces reservation, settlement, and backend limits. The paper evaluates whether this formulation improves verified task success under a fixed budget.

This is stronger than the older "budget-aware multi-step routing" tagline because it foregrounds a distinct problem definition: **budget-governed agent execution**.

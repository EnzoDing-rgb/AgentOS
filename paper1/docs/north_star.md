# BudgetFlow North Star

This is the current reviewer-facing source of truth for the BudgetFlow paper.
The previous long-form project memo is archived at
`paper1/misc/archive/north_star_archive_20260706.md`.

## Main Claim

BudgetFlow is a batch-level budget governance framework for multi-step agent
tasks under a shared hard budget. It aims to improve the cost-value frontier by
allocating model budget according to Task Value, estimated token demand, model
fit, and remaining budget. Across multi-run SWE-bench mini evidence, BudgetFlow
improves or closely approaches the best observed frontier, while also revealing
when cheap-model-only, strong-model-only, or learned-router policies already
form strong boundaries.

Short version:

BudgetFlow studies how a batch of tasks should share one hard budget so model
spend creates more verified task value. The paper does not claim BudgetFlow
always beats the strong model. It reports when value-aware batch allocation
improves the frontier, when a strong model is already the best boundary, and
when a learned router is a strong competitor.

## Writing Rules

- Use **Main Claim** in the paper.
- Put finer-grained routing, stage-aware routing, escalation policy, and learned
  stop/continue behavior in **future work**.
- Write in direct positive claims.
- Use fixed-resource frontier analysis as the scientific style: define the
  resource constraint, show the curve, and explain the boundary conditions.
- Present per-query routing, per-task routing, and batch-level budget
  governance as different useful layers.

## Paper Draft Workflow

The paper draft uses a PDF-first LaTeX workflow.

- The canonical manuscript source lives under `paper1/paper/src/`.
- `paper1/paper/src/main-ICML.tex` is the main paper source.
- `paper1/paper/src/references.bib` stores bibliography entries.
- `paper1/paper/figures/` stores paper figures.
- Build intermediates go under `paper1/paper/build/`; the installed PDF is
  `paper1/paper/BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ICML.pdf`.
- Paper-facing artifacts should be written in English.
- A useful paper scaffold includes `src/`, `figures/`, `reference/`, `archive/`,
  and a one-command build path via `Makefile`. It is more than an empty directory.

HTML files are auxiliary visual documents. The active related-work visual is
`paper1/docs/related_work.html`, and its path stays fixed.

## Related Work Correction Order

`paper1/docs/related_work.html` is the source of truth for related-work
positioning. Corrections to years, venues, project names, scope boundaries, and
primary-source claims should land there first.

The paper's Related Work section should then be written from the corrected
`related_work.html`. Citation hygiene can use narrow checks, but the correction
target remains `related_work.html`, not a temporary draft paragraph.

Serving systems such as vLLM, SGLang, and NVIDIA Dynamo should be described
clearly rather than waved away. They are strong execution substrates for
batching, prefill/decode, KV/prefix cache, priority scheduling, and cache-aware
routing. BudgetFlow studies how Task Value, shared hard budget state, and
verified outcome history generate the priority, continuation, and strong-model
opportunity signals that such substrates can consume.

## Canonical Terms

| Term | Meaning |
|---|---|
| BudgetFlow | The proposed batch-level budget governance framework. |
| Main Claim | The paper's central claim about shared-budget value allocation. |
| Total Resolved Value, TRV | Sum of pre-registered Task Value over verified resolved tasks. |
| Task Value | Value assigned before execution to a verified resolved task. |
| estimated token demand | Run-before estimate of token/runway need. |
| shared hard budget | One hard spending cap shared by the whole task batch. |
| cheap model | The cheaper configured model tier in the paper experiments. |
| strong model | The stronger configured model tier in the paper experiments. |
| cheap-model-only baseline | Baseline that uses the cheap model for every task. |
| strong-model-only baseline | Baseline that uses the strong model for every task. |
| learned task-router baseline | Baseline that chooses cheap or strong model per task without Task Value. |
| budget-only baseline | Baseline that observes budget pressure but not Task Value. |
| BudgetFlow task-level | Main BudgetFlow policy for the current paper evidence. |
| operating condition | Budget/model/cost situation in which a policy is evaluated. |
| cost-value frontier | Boundary of policies where no other policy is both cheaper and higher-TRV. |
| budget sensitivity | No-paid replay under tighter or looser shared hard budgets. |
| Task Value sensitivity | Re-scoring the same outcomes under alternate Task Value profiles. |
| KV Cache Cost-Discount sensitivity | Re-costing repeated input tokens under KV-cache discount assumptions. |
| task-level model advantage analysis | Analysis of where cheap or strong model is cheaper, stronger, or both fail. |

Internal code and historical artifacts may still use model-tier slot names.
Reviewer-facing writing should use cheap model and strong model unless a catalog
field or JSON schema is being discussed.

## Terms To Explain Once

**Total Resolved Value.** TRV is the sum of pre-registered Task Value over
verified resolved tasks. It is a paper-defined objective, not an official
SWE-bench metric.

**Cost-value frontier.** A policy is on the cost-value frontier if no other
policy achieves both higher TRV and lower spend under the same task set,
budget protocol, and verifier.

**Operating condition.** An operating condition describes the situation under
which a policy is tested: budget tightness, strong-model turn efficiency,
learned-router strength, Task Value placement, and KV-cache pricing.

**Batch-level budget governance.** BudgetFlow allocates one shared budget across
many tasks, rather than routing one query or one task in isolation.

## Evidence We Use

Use the four main paid artifacts below as the Main Claim evidence matrix. Do
not hide boundary cases. They make the paper more credible.

| Reviewer-facing role | Internal artifact stem | Completed at, Beijing time | Paper use |
|---|---|---:|---|
| 4x30 value-aware allocation case | `mainline_4x30_lhm_cycle_4policy_cleanresume_20260627` | 2026-06-27 23:15:21 | BudgetFlow wins TRV and TRV/$ while losing one raw resolved task to the strong-model-only baseline. |
| 5x30 strong-model boundary case | `mainline_5x30_claim1_retryfix_clean_20260629` | 2026-06-29 18:54:11 | Strong-model-only wins; report as a real boundary where the strong model is turn-efficient and cost-effective. |
| 5x30 learned-router stress case | `mainline_5x30_claim1_learnedprior_final_20260630` | 2026-06-30 03:28:17 | Strong-model-only narrowly wins; BudgetFlow is close to a strong learned/prior frontier. |
| latest audited 5x30 positive case | `mainline_5x30_claim1_frontierfix_20260630` | 2026-07-01 00:32:07 | BudgetFlow wins resolved count, TRV, and TRV/$ against the five-policy table. |

Internal interruption/continuation details are forensic reproducibility notes.
Reviewer-facing text should describe the latest artifact as a completed audited
5x30 run over the fixed task set and fixed budget protocol.

## Main Result Metrics

Every main table should report:

- Resolved Count
- Resolved Rate
- Total Spend
- Cost per Resolved Task
- Total Resolved Value
- Total Resolved Value per Dollar

Resolved Count and Resolved Rate keep the paper anchored to standard SWE-bench
metrics. TRV is the paper's value objective. TRV/$ is a cost-efficiency
diagnostic, not the only headline.

## Sensitivity Analyses

The paper should report three sensitivity families:

1. **Task Value sensitivity.** Re-score the same outcomes under equal value,
   compressed criticality, expanded criticality, and value permutation. This
   tests whether the result depends on one value scale or one lucky value
   placement.
2. **Budget sensitivity.** Replay the same completed rows under tighter and
   looser shared hard budget caps. This creates the main cost-value curve and
   shows which policy is strongest at different budget levels.
3. **KV Cache Cost-Discount sensitivity.** Re-cost repeated input tokens under
   explicit KV-cache discount assumptions. This tests how long multi-turn agent
   workflows change value per dollar when cached context is cheaper.

The task-level model advantage analysis is not a sensitivity table. It explains
why the curves look the way they do: which tasks favor the cheap model, which
favor the strong model, and which are ceiling tasks for both.

## Frontier Curve

The main visual should be a cost-value curve:

- x-axis: spend or shared budget cap
- y-axis: Total Resolved Value
- one line or point series per policy

This figure carries the "three-dimensional" conclusion. It shows more than one
leaderboard point: it shows where BudgetFlow improves the cost-value frontier,
where the strong-model-only baseline is already a strong boundary, and where
the learned task-router baseline is close.

Use terms such as cost-value curve, cost-value frontier, budget sensitivity,
and Pareto frontier.

## Baselines

The current main comparison has five policies:

| Policy | Role |
|---|---|
| cheap-model-only baseline | Tests whether the cheaper model is enough under the shared hard budget. |
| strong-model-only baseline | Tests whether using the strong model everywhere is already the best boundary. |
| learned task-router baseline | Tests whether a learned per-task router is enough without Task Value or batch-level budget governance. |
| budget-only baseline | Tests whether budget pressure alone explains the result. |
| BudgetFlow task-level | Tests whether Task Value plus shared-budget governance improves TRV under the same budget. |

The learned task-router baseline can be inspired by RouteLLM, but the paper
should name it as a learned task-router baseline. Original RouteLLM routes
single queries; our baseline routes whole SWE-bench tasks under the same shared
cap.

## Related Work Boundary

Per-query routers are useful for deciding which model should answer one prompt.
Per-task routers are useful for deciding which model should attempt one
multi-step task. BudgetFlow addresses a different layer: a batch of tasks shares
one hard budget, so the system must decide which tasks deserve scarce model
opportunities when the budget is limited.

Use this distinction without attacking prior work:

- per-query routing: one request -> choose model -> one answer
- per-task routing: one task -> many turns -> one task outcome
- batch-level budget governance: many tasks -> one shared hard budget -> decide
  who gets budget, who gets the strong model, and who should stop

OpenSquilla and Claw-SWE-Bench should be treated as serious related work, not
as work to dismiss. OpenSquilla strengthens the claim that harness, routing,
cost, cache behavior, replay, and diagnostics matter in real agent systems.
Claw-SWE-Bench strengthens the evaluation lesson that pass rate should be
reported with cost under controlled harness conditions. BudgetFlow's boundary
is narrower and different: it studies batch-level allocation of one shared hard
budget across pre-valued tasks, measured by verified TRV.

## Generalization

SWE-bench mini is the testbed, not the source of generality. The portable
problem structure is:

- many tasks share one hard budget;
- tasks have different values;
- model tiers have different costs and capabilities;
- outcomes can be accepted or rejected by a verifier or trusted signal.

Writing, marketing, spreadsheet work, customer support, and coding can all fit
this structure. The acceptance signal changes by domain: tests, human
acceptance, business KPIs, spreadsheet checks, editorial rubrics, or SLAs.

The paper should claim mechanism-level portability, not result-level dominance
across every domain.

## Future Work

Future work has four natural extensions.

First, BudgetFlow can study finer-grained allocation policy. This combines
stage-aware routing, segment-level routing, and escalation into one question:
when should scarce strong-model opportunities be spent inside a task?

Second, BudgetFlow can study continual policy learning. This combines learned
stop/continue decisions and memory into one question: how should completed
runs improve future allocation without weakening auditability?

Third, BudgetFlow can become serving-aware by connecting its value and budget
policy to serving substrates such as vLLM, SGLang, or NVIDIA Dynamo. These
systems expose batching, prefill cost, priority, and KV/prefix-cache locality.
A bounded follow-up can study how Task Value, remaining budget, and verified
outcome history should become serving hints such as priority, continuation, or
cache-sticky preference under the same shared hard budget.

Fourth, BudgetFlow can extend from one budget owner to multiple budget owners.
The current paper studies one entity allocating one shared hard budget across a
batch of tasks. A natural follow-up is multi-tenant agent budget governance:
multiple teams, users, or services share an agent execution substrate while
retaining separate budgets, priorities, and service objectives.

## Guardrails

- Freeze Task Value before execution.
- Keep Task Value separate from estimated token demand and historical spend.
- Keep the task set, task order, budget protocol, verifier, and model catalog
  fixed inside one comparison.
- Report boundary cases honestly.
- Keep strong baselines strong.
- Do not present local harness details as BudgetFlow mechanisms.
- Treat historical JSONL and reports as immutable evidence.
- Keep runtime/cache/checkpoint artifacts out of commits unless explicitly
  requested.

# BudgetFlow North Star

This file is the project vocabulary and paper-claim source. Use it for current
docs, prompts, handoffs, reports, and reviewer-facing prose.

## Draft-Critical Evidence Bar Memo

The current Claim 1 readout can support the initial draft. The final evidence
story still needs four evidence bars.

First, historical spend should not be used as Task Value. If a task costs many
turns or dollars, that is evidence that the task may be longer, harder, or needs
more runway. It belongs in Estimated Task Token Demand, Cost Memory, or
calibration evidence. Task Value still means "what is this verified resolution
worth if solved?" and should come from a pre-registered value source or business
priority, not from how much the model happened to spend.

Second, pure T2 and pure T3 are necessary boundary controls, not sufficient
strong baselines. They answer whether BudgetFlow beats uniform-tier frontiers
under the same shared cap. They do not answer whether BudgetFlow beats existing
routing ideas from related work.

Third, the draft-critical related-work baseline is a RouteLLM-inspired learned
task router. It learns offline which tasks look like they need T3 from
pre-execution task features, Estimated Task Token Demand, and frozen historical
outcomes. It does not use Task Value as an input, because Task Value is
BudgetFlow's value-aware signal. The trained router writes a FrozenRouterPlan
that chooses T2 or T3 at task start. At runtime it receives the same fixed task
set, same T2/T3 backend pool, same shared cap, same verifier, and same generic
per-task hard cap as BudgetFlow. This keeps the comparison honest: the learned
router may choose T2 or T3 per task, but it lives under the same budget controls
and does not receive BudgetFlow's value-aware allocation logic, stall guard, or
value-triggered escalation.

Do not call this "RouteLLM" without qualification. The original RouteLLM routes
single queries using preference data and a strong-model-call threshold; it does
not manage a shared budget. The paper baseline is "RouteLLM-inspired learned
task router" or "RouteLLM-inspired supervised task router." Its value is to test
whether BudgetFlow's value-aware shared-budget allocation beats a strong normal
model-router baseline, not merely pure-tier controls.

Fifth, the next Claim 1 paid comparison adds one budget-only control. The target
shape is five policies over the fixed 30-task set: pure T2, pure T3,
RouteLLM-inspired learned task router, budget-only baseline, and BudgetFlow
task-level. The budget-only baseline is value-blind: it sees shared budget
pressure and the same generic per-task hard cap as RouteLLM-inspired and
BudgetFlow, but it does not read Task Value and does not receive BudgetFlow's
value-aware routing or stall-guard logic. This control answers a narrow
question: does budget pressure alone explain the result, or does Task Value add
measurable allocation value?

The static allocation comparison is a separate no-paid upper-bound diagnostic,
not a sixth paid lane by default. After a five-policy run completes, the audit
can replay completed pure T2 and pure T3 outcomes to ask: if an offline planner
could choose the best T2/T3/skip combination under the same cap, how much value
was reachable? This "observed-tier oracle" is stronger than a deployable static
router because it sees outcomes after the fact. Use it to bound headroom and
reviewer objections before deciding whether a real sixth paid lane is needed.

Fourth, the paper must not hide custom metrics behind standard-sounding names.
SWE-bench's community-standard metric is Resolved Count and Resolved Rate.
Cost-aware coding-agent evaluation does not yet have a stable community
standard. BudgetFlow therefore reports both the standard SWE-bench view and the
paper-defined value view. The paper-defined Claim 1 objective is Total Resolved
Value:

`Total Resolved Value = sum(pre-registered task value for resolved tasks)`.

This is not an official SWE-bench metric and must be described as
paper-defined. The main table should report Resolved Count, Resolved Rate,
Total Spend, Cost per Resolved Task, Total Resolved Value, and Total Resolved
Value per Dollar. Equal-value sensitivity is required to show that the result
does not depend only on a favorable value profile.

## Core Terminology

Use **Claim 1** and **Claim 2** for paper claims. Reserve **T1/T2/T3** for model
tiers only.

## Current Draft Scope

For the initial paper draft, **Claim 1 is the active claim**. Claim 2 is parked
as follow-up mechanism analysis and should not block the near-term draft or the
current Claim 1 evidence readout. Mechanism observations still matter as
diagnostics and residual risks, but the draft headline is whether BudgetFlow
resolves more normalized verified value under the same compiled shared hard
budget.

| Term | Meaning |
|---|---|
| BudgetFlow | Value-aware budget governance for multi-step agent workflows under shared hard budgets. |
| Claim 1 | Under one shared hard budget, BudgetFlow maximizes Total Resolved Value, a paper-defined value-weighted objective over verified resolved tasks. |
| Claim 2 | BudgetFlow's budget-aware allocation policy explains how Claim 1 is achieved: it chooses when to spend, stop, continue, route, or escalate under the compiled budget, and must improve or preserve value/cost efficiency against strong diagnostic controls. The policy may be task-level, stage/segment-aware, learned from memory, or a hybrid; no single source is assumed correct by definition. |
| Resolved Count | Number of tasks whose generated patch satisfies the SWE-bench verifier. This is the standard SWE-bench count metric. |
| Resolved Rate | Resolved Count divided by total tasks. This is the standard SWE-bench rate metric. |
| Total Spend | Total model spend within the shared budget window. |
| Cost per Resolved Task | Total Spend divided by Resolved Count. It is an accessible cost diagnostic, not the Claim 1 objective. |
| Total Resolved Value | Paper-defined Claim 1 objective: sum of pre-registered Task Value over resolved tasks. It is not an official SWE-bench metric and should not be renamed as if it were community standard. |
| Total Resolved Value per Dollar | Total Resolved Value divided by Total Spend. It is a value-weighted cost-efficiency diagnostic, not the only headline. |
| Value-Driven Budget Allocation | Two-layer mechanism: first compile a shared hard-budget regime for a fixed task sequence; then allocate model opportunities, turns, continue/stop decisions, and spend within that regime. |
| Budget Regime Compiler | Pre-run mechanism that turns a fixed task set, fixed task order, ValueSource, Estimated Task Token Demand, reference cost scale, clean frozen calibration evidence when available, and target pressure into a pre-registered shared hard budget plan with confidence and audit fields. It is part of Claim 1, not a separate claim, and it must not assign model tiers to individual tasks. |
| BudgetFlow Runtime | Runtime policy that executes the same task order as every control and allocates scarce model opportunities within the compiled shared budget. It decides when to spend, continue, stop, or use a stronger tier; it does not reorder tasks to chase value. |
| Task Value | Estimated utility of a verified resolved outcome. It answers "what is this task worth if solved?" |
| Estimated Task Token Demand | Run-before estimate of token/runway demand for a task. It answers "how much budget should this task need?" The current code schema still carries this through `task_effort_multiplier` and `final_task_effort`; prose should use Estimated Task Token Demand. |
| Model Fit | Estimated suitability of each model tier for a task, repo, or workflow stage. It answers "which tier is likely to make verified progress here?" |
| AllocationContext | Standard decision input that carries Task Value, Estimated Task Token Demand, Model Fit, budget state, cost source, and confidence into policy decisions. |
| Tier Boundary Selection | Choosing whether a BudgetFlow policy should behave near the T2 boundary, near the T3 boundary, or use mixed model-tier routing for the current allocation context. |
| ValueSource | Versioned input that defines or estimates task value for one run or deployment. |
| Frozen Router Plan | Pre-registered static router prior for diagnostic controls. It may contain task IDs, preferred model tier, priority/order, and router rules. It must not contain or imply budget caps. |
| CostSource | Versioned input that defines or estimates model cost for one run or deployment. |
| KV Cache Sensitivity | Explicit CostSource sensitivity that discounts post-first-turn repeated input tokens while leaving base tier prices and physical model bindings fixed. KV sensitivity is allowed as a pre-registered analysis or catalog variant; it must not be hidden inside the main CostSource. |
| TaskAdapter | Adapter that turns external work into standard BudgetFlow task inputs: identity, description, features, difficulty/value hints, and value-source metadata. |
| BudgetAdapter | Adapter that turns customer or experiment budget input into a standard budget window, hard/soft cap, shared scope, allowed model pool, source, and confidence. |
| CostAdapter | Adapter that turns public price catalogs, provider estimates, invoices, enterprise rate cards, or manual overrides into a standard cost signal. |
| ProgressAdapter | Adapter that turns process evidence and final acceptance into standard progress/outcome signals. Intermediate progress can be unknown; final acceptance defines resolved. |
| Policy Backend | Pluggable strategy that recommends cap, model tier, escalation, de-escalation, stop, and continue decisions. |
| Cost Memory | Optional learning input for cost, cap sufficiency, task value, and Total Resolved Value per Dollar evidence. It is not a required Claim 1 input and should be enabled only in an explicit learning configuration. |
| Routing Memory | Optional learning input for backend choices, stage/segment outcomes, failure axes, and route effectiveness. It can inform a learned or hybrid Claim 2 policy, but it is not synonymous with Claim 2. |
| Escalation Memory | Optional learning input for whether Strongest Model turns were productive. It mainly applies to policies with escalation windows; task-level policies may not use it. |
| Value-Triggered Escalation | Bounded use of a stronger model tier for high-value tasks when expected marginal value justifies it. |
| Strongest Model | The strongest configured model tier. It is one model-tier option, not the system claim. |
| Model Tier Slot | T1/T2/T3 are normalized experimental roles with fixed tier semantics for one catalog revision family. A physical model/provider can be swapped into a tier by changing endpoint binding, but the paper interpretation remains the tier slot, not the vendor name. |
| Provider Binding | The physical model name, base URL, API key, and provider protocol attached to a Model Tier Slot. Provider binding is infra and catalog configuration; it should not create routing branches or new paper claims. |
| Frontier Dominance | A diagnostic state where a stronger tier is both more capable and cheaper in total because it uses fewer turns. In that state, pure Strongest Model is a strong boundary control, and BudgetFlow must diagnose whether any allocation problem remains under the compiled budget. |
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
verified task value. BudgetFlow should not be described as making models better
at coding. Verified resolution is primarily evidence of model capability under
a valid harness. BudgetFlow's contribution is to govern which tasks receive
scarce model opportunities, runway, retry chances, and stronger-tier access
under one shared budget.

The system has two decision layers.

- **Budget Regime Compiler:** establishes the budget regime before execution.
  It estimates how much shared budget a fixed workload deserves from Task
  Value, Estimated Task Token Demand, a reference cost scale, and clean calibration evidence.
  It does not solve the routing problem and must not pre-assign model tiers to
  specific tasks.
- **BudgetFlow Runtime:** executes the fixed task order under that compiled
  budget. It uses AllocationContext, remaining budget, progress evidence,
  Model Fit, and model costs to decide whether to continue spending, stop,
  retry, or use a stronger model tier. It may change how budget is spent inside
  a task, but not the task sequence being compared.

This boundary avoids circular reasoning. The compiler answers the budget-owner
question: "How tight should this shared budget be for this workload?" The
runtime answers the scheduler question: "Given that budget and the available
models, where should the next model opportunity go?"

For the current paper mainline, the Budget Regime Compiler does not assign
model tiers. It may publish a runtime-policy projection showing how many tasks
the current task-level router is expected to start on T2 or T3 under the frozen
budget, ValueSource, Estimated Task Token Demand, Model Fit, and CostSource. That projection is
a no-paid readiness diagnostic, not a route lock. Runtime makes the actual
task-start model choice through the same task-level routing formula and the
same effective task-cap calculation.

In staged runs, `stage_prefix_count` defines only the pressure reference used
to compile the shared hard cap. It must not shorten the runtime planned-budget
rebalance horizon. BudgetFlow task-level effective caps reserve runway across
the full frozen task order so a 10+10+10 run cannot spend the third stage's
planned demand during the first or second stage.

`planned_task_budget` is the compiler's per-task demand/cap weight. The sum of
these weights may exceed the shared hard cap. `effective_task_budget` is the
runtime value after clipping the current task against remaining shared budget
and remaining planned demand. For BudgetFlow task-level and the
RouteLLM-inspired learned task router, `effective_task_budget` is an execution
hard cap: provider calls are not reserved once the task has exhausted that live
cap. Pure T2 and pure T3 controls keep only the shared batch hard cap plus the
global turn cap.

For the next five-policy Claim 1 run, the budget-only baseline also receives
that same generic `effective_task_budget` hard cap. The cap is a fairness
control, not BudgetFlow logic. BudgetFlow may use the cap together with Task
Value, Estimated Task Token Demand, Model Fit, and budget pressure to choose T2
or T3 at task start. Budget-only uses the cap only to stop spending and uses
budget pressure only to choose between cheaper and stronger tiers.

## Claims And Metrics

| Claim | Main question | Primary evidence |
|---|---|---|
| Claim 1 | Under the same compiled shared hard-budget regime, does BudgetFlow resolve more pre-registered task value? | Total Resolved Value at fixed budget, with Resolved Count, Resolved Rate, Total Spend, Cost per Resolved Task, Total Resolved Value per Dollar, budget-plan confidence, and actual utilization reported as required diagnostics. |
| Claim 2 | Which budget-aware allocation policy explains the Claim 1 result, and is that policy reusable? | Parked for the initial draft. Later mechanism evidence can include resolution-cost frontier, Strongest Model productive use, Tier Boundary Selection, stop-loss behavior, task-level vs stage/segment-aware controls, optional memory effect when enabled, and failure attribution. |

SWE-bench's standard metric is Resolved Rate. BudgetFlow must always report
Resolved Count and Resolved Rate in the main result table. Because Claim 1 is
about heterogeneous task value under one shared hard budget, BudgetFlow also
defines Total Resolved Value as a paper-specific objective. Do not present
Total Resolved Value as a community-standard SWE-bench metric. Define the
formula in the paper body and show the pre-registered value source.

The main Claim 1 table should use these columns:

`Resolved`, `Rate`, `Spend`, `Cost per Resolved Task`, `Total Resolved Value`,
and `Total Resolved Value per Dollar`.

Equal-value sensitivity is mandatory. It shows whether the direction holds when
all task values are set to 1.0 and prevents the value-weighted objective from
looking post-hoc fitted.

Value sensitivity must be generated by code from the same completed JSONL and
frozen ValueSource, not hand-recomputed after the fact. The minimum report
includes the main criticality profile, equal value, compressed criticality,
expanded criticality, and a value-permutation diagnostic. These are robustness
diagnostics; the frozen pre-registered ValueSource remains the primary Claim 1
objective.

Claim 1 is the objective. The Budget Regime Compiler is the pre-run part of
Value-Driven Budget Allocation: it defines the shared budget regime before any
policy comparison. The Runtime is the execution part: it allocates model
opportunities within that regime while preserving the pre-registered task
order.

Claim 1 evidence must report whether the shared hard budget is binding. If a
pure Strongest Model control completes the fixed workload far below the cap,
the result is still a fixed-workload value readout, but it does not establish a
scarcity mechanism. The next paid-run candidate should therefore use a
pre-registered tighter cap or larger/harder workload that puts pure T3 under
real budget pressure.

The current Claim 1 task set remains 30 tasks. Expanding to 50 tasks is not the
next evidence move. The next evidence move is to keep the task set, task order,
ValueSource, CostSource, and budget regime fixed, then add the value-blind
budget-only baseline so the paper can separate "budget pressure helps" from
"value-aware budget allocation helps."

Claim 2 is mechanism analysis about the allocation policy that produced the
Claim 1 outcome. For the initial draft it is explicitly out of scope. Later,
that mechanism story can come from a task-level tier choice, a
stage/segment-aware router, a learned memory input, or a hybrid. BudgetFlow
Segment Routing is therefore a Claim 2 policy variant, not a requirement for
accepting a Claim 1 run. Memory-based continual learning is another possible
Claim 2 variant, not a requirement for every Claim 1 run.

For the active Claim 1 mainline, BudgetFlow task-level means the model tier is
chosen at task start and then held fixed for that task. Do not introduce
stage/segment-level tier switching, mid-task escalation, or repair-stage rescue
as an unannounced fix to a Claim 1 run. Stage-boundary changes to BudgetFlow are
allowed when they fix observability, value/cost accounting, or task-start
routing bugs, but they must remain auditable against the unchanged pure T2 and
pure T3 controls.

For the active Claim 1 task-level mainline, no-progress/stall signals are
BudgetFlow mechanism signals. BudgetFlow task-level may use them for its own
stop-loss behavior when the task has consumed meaningful planned cap.
RouteLLM-inspired and pure-tier controls do not receive this BudgetFlow-specific
stall guard. A task-level run stops on the shared hard cap, its live per-task
hard cap when that policy receives one, catalog/runtime turn limits, provider
failures, harness completion, or strategy-agnostic agent-loop guards. If a task
should use the Strongest Model, that decision belongs in the task-start router
through Task Value, Estimated Task Token Demand, ModelFit, CostSource, budget
pressure, and effective cap.

Routing savings, stage-aware routing, Tier Boundary Selection, stop-loss,
escalation, and learning inputs are useful only when they protect or improve
Claim 1. Do not optimize mechanism diagnostics in a way that reduces
value-weighted outcomes.

Average turns, no-patch rate, per-task cost, tasks skipped due to budget
exhaustion, and value-tier breakdowns are diagnostics for the initial draft.
They must not replace Total Resolved Value as the Claim 1 objective or Resolved
Rate as the standard SWE-bench metric.

Pure-tier controls can expose a real model frontier change. If the Strongest
Model is both more capable and cheaper in total for nearly every task under the
frozen catalog and compiled cap, then the current workload has little remaining
model-tier allocation problem. That is not something to hide by weakening the
baseline. Report it as Frontier Dominance, explain that fewer turns made the
stronger tier cheaper in total, and treat BudgetFlow's remaining value as
budget governance, stop/continue discipline, and detection of the frontier
posture. Claim 2 becomes stronger when BudgetFlow can distinguish task types:
easy tasks where the reference tier is sufficient, hard tasks where the
reference tier spins, high-value tasks where stronger-tier spend is justified,
and ceiling tasks where neither tier should consume the shared budget for long.
If every task is dominated by one tier, BudgetFlow should say so rather than
manufacture routing savings.

The current paid mainline uses four policies: pure T2, pure T3, a
RouteLLM-inspired learned task router, and BudgetFlow task-level. The learned
router is the strong non-BudgetFlow routing baseline: it is trained offline,
does not read Task Value, writes a FrozenRouterPlan, and runs under the same
shared hard cap. The headline question is whether BudgetFlow beats pure-tier
boundaries and a normal learned router while preserving or improving Total
Resolved Value per Dollar under the same shared hard budget.

## Value And Cost Discipline

Task Value is a proxy, so every paid run must make the proxy auditable.

- Freeze the ValueSource before execution. Do not change task values after
  seeing outcomes.
- Pre-registered criticality belongs to the ValueSource/value matrix, not to
  the frozen router plan. The current paper profile uses
  `criticality_level = normal | high | critical` with a fixed mapping
  `normal=1.0`, `high=1.5`, and `critical=2.5`. The RouteLLM-inspired learned
  router baseline must not read Task Value. Diagnostic frozen-router controls
  may carry pre-registered route priors, but no frozen router plan defines Task
  Value or budget caps.
- Manual overrides may change only `criticality_level` or Estimated Task Token
  Demand fields such as `task_effort_multiplier`, and each override must record
  from, to, source, and reason. Overrides must not directly write model_fit,
  expected uplift, route to a model tier, or budget cap.
- Report at least equal value and the chosen Task Value profile. Estimated Task
  Token Demand diagnostics can be reported separately, but they must not be
  presented as Claim 1 value.
- Explain whether the direction of the signal depends on the chosen value
  profile.
- Do not treat "easy to solve" or "expensive to run" as "high value."
  Estimated Task Token Demand can inform budget runway and cost estimates, but
  it is not Task Value.
- In enterprise deployments, value may be supplied by customer priority,
  revenue, SLA, risk, or an external system. In SWE-bench experiments, value is
  a pre-registered research proxy and must be treated as a threat to validity.

Estimated Task Token Demand and cost follow the same rule.

- Use a versioned model-tier catalog for paid runs.
- Record catalog path, revision, provider, and any price multipliers.
- Treat T1/T2/T3 as normalized Model Tier Slots for this paper's experiments.
  The tier catalog defines the experimental cost and capability priors. A
  provider-only swap inside the same catalog semantic revision changes the
  physical endpoint, base URL, and API token; it does not by itself change the
  tier's normalized cost, routing semantics, or paper interpretation.
- Do not recalibrate T1/T2/T3 from public provider prices or web search during
  a paid-run line. Real provider invoices can be a CostSource in deployment,
  but the paper experiments use the frozen normalized catalog unless the run is
  explicitly declared as a new cost-source study.
- If a provider swap materially changes observed behavior, handle it as a
  provider validation or catalog-semantic-revision risk. Do not add
  provider-name-specific routing rules, task exceptions, or ad hoc price
  corrections to preserve a result.
- Keep Estimated Task Token Demand separate from Task Value. Metadata
  heuristics, historical cost, turns, test counts, patch size, and repo priors
  estimate runway or expected cost; they do not define outcome utility.
- Active value matrices expose Estimated Task Token Demand through one
  normalized schema path:
  `base_task_effort`, `task_effort_multiplier`, and `final_task_effort`.
  Runtime, compiler, and Model Fit estimation consume the final estimated token
  demand value; retired fields must not re-enter active routing.
- Model Fit is physical-model evidence. Provider-swapped historical rows may be
  useful forensic evidence, but they cannot calibrate runtime Model Fit unless
  the recorded physical catalog hash or revision matches the active catalog.
- Mainline catalog costs should not include asymmetric KV-cache discounts. Cache
  discounts belong in explicit sensitivity catalogs or reports, not the primary
  evidence catalog.
- Treat pure T2 and pure T3 baselines as boundary diagnostics. If a pure tier is
  best for a task distribution and model catalog, BudgetFlow should diagnose
  and absorb the reusable principle through Tier Boundary Selection, not weaken
  the baseline.

The Budget Regime Compiler makes the fixed budget auditable rather than
hand-picked.

- Compile the shared hard budget from frozen task IDs, frozen task order,
  ValueSource, Estimated Task Token Demand, a reference service/cost scale, clean frozen
  calibration evidence when available, and a predeclared target pressure such
  as roughly 80%-90% expected utilization.
- The compiler may use a model catalog or invoice data to convert expected
  effort into dollars, but only as a reference cost scale. It must not decide
  that a particular task should use T2, T3, or any future model tier. That is a
  runtime allocation decision.
- Apply a Strongest Model runway floor: the compiled cap should let the pure
  Strongest Model baseline reach the final task before budget pressure
  dominates. A cap that starves the strongest baseline midway through the batch
  is too tight to diagnose value allocation.
- Keep the compiled cap tight enough that a pure Strongest Model baseline is
  budget-constrained or exhausts the cap. If the strongest baseline can solve the
  workload without pressure, the budget regime is too loose to test allocation.
- Use one small diagnostic calibration pass at most for a new workload/model
  catalog before freezing the budget plan for the evidence run. Repeated
  calibration on the same evaluation slice weakens the claim.
- Report budget-plan confidence, projected utilization, actual utilization, and
  whether pure T3 hit the cap. A strongest-tier baseline near 100% utilization
  can be a healthy sign that the budget is genuinely binding.
- Do not claim the compiler guarantees exact utilization. It targets a pressure
  regime and must expose projection error when actual spend is too loose or too
  tight.
- Frozen cost calibration for the compiler must consume only current-schema,
  same-catalog, scoreable rows. Budget-exhausted rows may enter only as censored
  spend floors and must include remaining-runway estimates before the next cap
  is compiled; they are never complete cost observations. Provider, parser,
  infra, old schema, or catalog-mismatched rows are forensic evidence, not
  calibration samples.
- Continual Cost Memory is optional and must be evaluated separately from
  frozen calibration. If enabled, the memory source, schema filter, and effect
  on the next cap must be explicit and auditable; otherwise it should be
  disabled for clean Claim 1 evidence runs.
- Frozen router plans are never a budget source. Retired frozen-cap fields such
  as per-task ``base_cap`` or meta ``hard_cap_usd`` must be regenerated out of
  active router-plan artifacts before paid runs.

The compiler handles the main "how small can the shared budget be?" question.
The runtime BudgetFlow policy should then win by allocating that already-tight
budget toward higher verified value, not by claiming savings from an overly
generous cap.

The Runtime must not win by changing task order. For policy comparisons, every
strategy executes the same pre-registered task sequence. Otherwise a high-value
first ordering could inflate Total Resolved Value under early budget exhaustion
and confound the allocation claim. Value awareness is allowed inside routing,
continue/stop, retry, and stronger-tier access decisions; it is not allowed to
reorder the batch unless task ordering itself is the declared experimental
intervention.

## Calibration Discipline

BudgetFlow is not claiming that one fixed set of constants is universally
optimal. Real deployments differ in task mix, customer value, model prices,
model access, and model-task fit. A customer usually does not know, before
running the system, how much budget a workload deserves or which model tier
will be productive on each task. Calibration is therefore a necessary part of
deployment: it maps local value, effort, cost, and model-fit evidence into a
shared hard-budget regime.

This calibration is generalizable when it calibrates the mechanism, not the
benchmark. The reusable object is the procedure: pre-register task value and
task features, compile a budget from ValueSource, Estimated Task Token Demand, model catalog,
and clean calibration evidence, run under the compiled cap, audit projection
error and verified value, then freeze the next configuration before evaluation.
The same procedure can be repeated for a different enterprise workload with
different tasks, prices, models, and priorities. What must not transfer is any
task identity, repo-specific exception, known patch, or post-hoc outcome label.

Small diagnostic runs can serve as a cold-start pass for a new workload/model
catalog. They are not paper-level evidence by themselves. Their role is to
estimate the scale that cannot be known a priori: whether the compiled budget
is too tight or too loose, whether Estimated Task Token Demand predicts runway, whether Model
Fit differentiates model tiers, and whether budget pressure reaches the
intended regime. A provider-only binding change within the same normalized tier
semantic revision is not, by itself, a new cost model. It still needs provider
preflight and may need diagnostic validation, but it should not trigger a new
round of real-world price calibration. After the calibration pass, the
compiler, model catalog, ValueSource, task list, task order, and policy
configuration must be frozen before the held-out evidence run.

Frozen calibration and continual learning are different experimental modes.
Frozen calibration is a pre-run procedure that produces a budget plan and
abstract inputs such as workload-level Model Fit; the evidence run consumes
those inputs without updating them. Continual learning consumes memory records
to alter a future cap, route, stop/continue decision, or escalation window. It
should be treated as an optional Claim 2 policy variant, not as a hidden
requirement for Claim 1.

That calibration is part of the enterprise mechanism, not a benchmark trick,
when it follows these rules:

- Calibrate only on diagnostic runs or production holdout data, then freeze the
  policy and ValueSource before the evidence run.
- Prefer one diagnostic calibration pass for each new workload/model catalog;
  one additional pass is acceptable when the first pass exposes an infra or
  scale defect that would make the evidence run uninterpretable. More passes
  should be reported as mechanism development, not as final evidence.
- Tune abstract mechanism inputs: task value scale, cost source, model-tier
  fit, budget slack or shadow price, progress urgency, rescue window, stop-loss
  patience, and escalation confidence.
- Do not tune on SWE-bench task IDs, repo names, pytest names, known patches,
  historical pass/fail labels for the evaluation set, or harness quirks.
- Report the calibration source and whether continual learning inputs were
  enabled. A small diagnostic run can justify the next frozen configuration,
  but it is not paper-level evidence by itself.
- Treat calibration as reusable only if the same procedure could be repeated on
  another enterprise workload with different tasks, values, models, and prices.
- Interpret a repeated failure of the compiled cap, such as starving most
  policies midway through a batch or leaving every strongest-tier baseline
  unconstrained, as a Budget Regime Compiler defect to fix through the abstract
  compiler procedure rather than by hand-editing the cap.

Business-side value and difficulty inputs are part of the deployment objective
when they are pre-registered. In a real deployment, business owners or external
priority systems may define which tasks are worth more, which tasks are
expected to be harder, and how much budget pressure is acceptable. That is the
point of ValueSource and Estimated Task Token Demand: BudgetFlow turns business judgment and
workload features into an auditable budget allocation problem. The research
threat is not that external stakeholders provide value or difficulty. The
threat is seeing outcomes first and then editing those inputs to make a run
look good. To defend against that, freeze the value matrix, estimated token demand
features, model catalog, task list, and task order before the evidence run;
report the calibration passes that produced them; and show whether the signal
survives under at least an equal-value sensitivity view.

The main generalization claim is procedural, not parametric. BudgetFlow should
not argue that a particular target utilization, Model Fit prior, stop-loss
constant, segment signal, or memory rule is universally correct. It should argue
that a customer can provide or calibrate ValueSource, Estimated Task Token Demand, Model Fit,
and CostSource for its own workload, and BudgetFlow turns those inputs into an
auditable shared-budget allocation problem whose evidence is measured by
Resolved Rate, Total Resolved Value, and Total Resolved Value per Dollar.
Continual learning can be added as a separate policy source when its memory
effect is cleanly isolated and improves the same objective.

The clean policy semantics are:

- Budget slack or shadow price measures scarcity. As the shared budget is
  spent, strongest-tier access should become harder unless expected value
  clearly justifies it.
- Progress urgency measures being stuck. No-progress streaks, repair evidence,
  and validation failure can trigger bounded escalation or rescue windows.
- Value density combines Task Value, Model Fit gain, and extra model cost. It
explains when spending more can improve Total Resolved Value per Dollar.

These signals must stay separate in code and traces. A variable named budget
pressure must not simultaneously mean "budget is scarce" and "upgrade because
the agent is stuck."

Do not over-attribute verified passes to individual BudgetFlow mechanisms.
Passing a task means the model, prompt, tools, and harness produced a verified
patch. BudgetFlow mechanisms should be credited for opportunity allocation:
whether they gave the model enough runway, avoided wasting scarce budget,
prevented premature stopping, or chose an appropriate tier under pressure.
Harness and infra diagnostics are validity gates and opportunity boundaries;
they do not become paper mechanisms merely because fixing them increases pass
rate.

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
source, budget, model catalog, harness, and task execution order fixed within
one comparison.

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

## Related Work Boundary

The closest current papers are mostly component-level neighbors. They should
shape Claim 2 diagnostics, but they do not replace Claim 1.

| Work | What it studies | Boundary against BudgetFlow |
|---|---|---|
| Inference-Time Budget Control | Controls tool and token budgets inside one search or QA example. A run that exceeds the per-example budget fails. | Useful contrast for per-request budget control. It does not allocate one shared hard budget across a batch of valued tasks or report paper-defined Total Resolved Value. |
| RouteLLM | Learns a per-query router that predicts whether a strong model should handle a prompt, using preference data and a threshold that controls the share of strong-model calls. | Strong baseline inspiration, not directly reusable. BudgetFlow needs a RouteLLM-inspired task router trained for SWE-bench task outcomes, attached to T2/T3 through a FrozenRouterPlan, and evaluated under the same shared cap. |
| RouteNLP | Deployment-level four-tier cascade routing that minimizes cost while meeting per-task quality constraints, with conformal cascading and distillation co-optimization. | Strong Related Work positioning anchor. It proves industrial routing matters, but it solves the inverse problem: quality floor -> minimize cost. BudgetFlow solves fixed shared budget -> maximize verified task value. RouteNLP has no shared cap, no cross-task budget depletion, and no Task Value. |
| UCCI | Uses calibrated uncertainty in a two-model cascade to decide when to upgrade from a cheaper model to a stronger model under a quality or F1 constraint. | Strong Claim 2 neighbor for Model Fit, uncertainty, and escalation calibration. It is not shared workload budget governance and does not optimize verified task value across a pre-registered value set. |
| Topaz | Builds an auditable routing layer with skill profiles, budget assignment, and explanation traces, mainly in customer-support style case studies and demos. | Useful Claim 2 neighbor for auditability and routing explanations. BudgetFlow still needs verified task execution, frozen ValueSource, shared ledger accounting, and Total Resolved Value under the same hard budget. |

The paper's core distinction is: BudgetFlow asks how a batch of tasks should
share a hard budget so model capability flows toward the highest verified task
value. Per-request budget control, uncertainty cascades, and auditable routers
are related mechanisms or baselines, not the Claim 1 objective.

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
   task difficulty, budget opportunity allocation, insufficient runway,
   premature stop, tier choice, evaluation validity, parser/harness failures,
   or model-price boundary. Do not claim that stop-loss, routing, or compiler
   logic directly created code-solving ability; they shape whether model
   capability had a fair and budget-aware opportunity to act.

The point of each experiment is not to "get a good result." The point is to
identify which layer currently limits paper value: claim, metric, harness,
infra, learning loop, or mechanism.

## Evidence Discipline

- Historical JSONL and historical reports are immutable evidence. Do not patch
  old artifacts to make the current story cleaner.
- Small paid runs are diagnostics, not paper-level evidence.
- The current committed runner is the rollback checkpoint for the harness-v2
  refactor. If the refactor increases noise or blocks paid-run safety gates,
  return to this checkpoint and treat the refactor branch as forensic work.
- Local harness results are part of the evidence system. Because nested Docker
  is not assumed available, local harness adapters, compat patches, host
  dependencies, and checker invalidation rules are first-class evaluation
  risks.
- Harness-v2 work should improve the local no-Docker path first. Do not replace
  the runner wholesale with an external benchmark runner unless that reduces
  moving parts under the same Claim 1/Claim 2 contract.
- The agent should be scored on repository changes, not on a fragile patch
  submission ritual. Runner-side patch collection from the task workspace should
  become the standard artifact path, with explicit submitted patches kept as
  auxiliary evidence.
- Harness and observability refactors must preserve the BudgetFlow mechanism.
  For task-level BudgetFlow, the Budget Regime Compiler supplies the shared
  hard budget and pre-registered per-task runway. It may publish
  runtime-policy projection diagnostics, but it must not assign a model tier to
  each task. Runtime uses that per-task runway, Task Value, Estimated Task Token Demand, Model
  Fit, and CostSource to choose a fixed model tier before each task starts,
  while the shared hard budget still controls the batch. A run where task-level
  BudgetFlow silently degenerates into a pure-tier baseline is a mechanism
  failure, not a weak positive signal.
- Worktree isolation must be auditable. Resetting to `base_commit` and cleaning
  files is necessary but not the whole story: future git history, stale
  worktrees, compat edits, and host Python state are all harness risks. Future
  history exposure is not by itself proof of cheating or model failure, but it
  should be tracked and removed where practical so reviewers do not have to rely
  on agent honesty.
- Do not undertake invasive harness rewrites solely to defend against
  intentional reward hacking by an otherwise honest agent. The local harness
  should score repository workspace diffs, track contamination risks, and keep
  audit artifacts, but the paper's main validity work is credible task
  isolation and verifier-grounded scoring, not adversarial anti-cheat.
- Runtime artifacts under `paper1/data/` are not source code. Do not commit
  trace, heartbeat, checkpoint, or run-output files unless explicitly requested.
- Before paid runs, pass no-paid gates for tests, value/cost confidence,
  provider access, parser behavior, budget mode, worktree isolation, and
  checker output.

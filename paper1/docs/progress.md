# BudgetFlow Progress

> Living execution doc. Audience = human owner + agent.
>
> Update rule:
> - Follow current highest-priority phase.
> - Earlier phase details may be removed after project focus fully shifts.
> - Code root stays `paper1/src/budgetflow/`.

---

## Quick recall: where this stands now

What already exists now:

- `paper1/src/budgetflow/` is no longer empty skeleton only.
- Core runtime pieces already exist: types, ledger, governor, selector, scheduler, zombie handling, mock backend.
- There is now also a **minimal ReAct-like agent loop**. Its job is simple: produce a small sequence of steps like Localization -> Repair -> Validation, send explicit `TurnInfo` into BudgetFlow, and let BudgetFlow decide cheap vs strong model.
- There is also a **comparison runner**. It can run same small workflow under three policies:
  - `workflow_level_router`
  - `budget_only_step_router`
  - `budgetflow_full`
- There are **real small-scale mock tests**, not dummy tests.

What has already been tested:

1. The minimal loop can run end-to-end.
2. Budget reservation / settlement works under small mock runs.
3. Policy comparison really works, meaning the three policies no longer collapse into same behavior.
4. Current small-scale comparison result under current mock assumptions is:
   - `workflow_level_router` -> resolved 0
   - `budget_only_step_router` -> resolved 0
   - `budgetflow_full` -> resolved 2

What this means in plain language:

- Project is past pure design stage.
- Project is also past pure runtime-skeleton stage.
- We already have a runnable tiny experimental system.
- Current question is no longer “can BudgetFlow run at all?”
- Current question is “are current mock assumptions good enough, or should we make them more realistic before wiring real backend?”

What to do next when coming back:

Choose one of two directions:

1. **Refine mock realism first**
   - make cheap vs strong behavior less crude
   - make progress signals less toy-like
   - keep whole system cheap and controllable

2. **Start partial real hookup**
   - keep one tier mocked
   - connect one real backend
   - begin checking whether runtime behavior still looks right with real cost and response patterns

If unsure, default next step:

> Refine mock realism first, then connect one real backend later.

## Part 1. Boss view

### Current phase

**Tier 1**

### What boss wants in current phase

Build minimum BudgetFlow runtime that can answer one question clearly:

> Under fixed budget and shared backend limits, does workflow-aware step budgeting beat weaker baselines on small coding-agent workload?

### What Tier 1 must contain

- Runtime governor, not full agent framework.
- Code root under `paper1/src/budgetflow/`.
- Two-tier backend pool.
- Multi-workflow budget accounting.
- Step-level routing using `stage`, `w_i`, `budget_pressure`.
- Hard budget enforcement via reserve -> settle.
- Small controlled evaluation on Lite-style workload.
- Baselines strong enough to test core claim.

### What Tier 1 does **not** need

- LangChain integration as main path.
- Proxy sidecar as main path.
- Rich calibration pipeline.
- Public `.traj` replay before runtime exists.
- N-ary backend pool.
- Full Tier 2 experiments.
- Complete productization.

### Current accepted architecture

```text
minimal agent loop
        -> TurnInfo
        -> BudgetFlow runtime
        -> 2-tier backend pool
        -> result checker / comparison runner
```

### Current working assumptions

1. Primary code package name = `budgetflow`.
2. Primary Tier 1 integration mode = SDK-like explicit interface.
3. LangChain / callback / proxy remain preserved design options, not current execution priority.
4. Tier 1 may use `zero_calibration` default progress table.
5. Tier 1 evaluation can use Lite warm-up subset, even though broader design still preserves Verified-oriented language.

### Boss-level success criteria

Tier 1 succeeds if all below become true:

- BudgetFlow runtime exists as runnable code.
- Runtime can enforce hard budget under concurrent workflows.
- Runtime can route between cheap and strong tier using explicit stage-aware policy.
- At least one controlled baseline comparison runs end-to-end.
- Results are good enough to say whether idea deserves Tier 2.

---

## Part 2. Agent implementation plan

### Immediate execution order

#### [x] Step 1. Create runtime skeleton

Target dir:

```text
paper1/src/budgetflow/
```

Planned files:

```text
budgetflow/
  __init__.py
  types.py
  ledger.py
  governor.py
  selector.py
  scheduler.py
  zombie.py
```

Why first:
- Need stable object model before scaffold or experiments.
- `paper1_design.md` already commits to these core runtime concepts.

Acceptance:
- Package imports cleanly.
- Core datatypes exist.
- File boundaries roughly match design responsibilities.

#### [x] Step 2. Implement accounting core

Must implement:
- `expected_cost`
- `reserved_cost`
- `actual_cost`
- reserve / settle / release flow

Why:
- Hard budget guarantee is central Paper 1 claim.
- Without accounting core, routing logic not meaningful.

Acceptance:
- Workflow reservation cannot overspend global budget.
- Settlement returns unused reserved cost.
- Concurrent reserve path protected by atomic lock or equivalent.

#### [x] Step 3. Implement model selection rule

Must implement:

$$
w_i \cdot \frac{\Delta \widehat{progress}}{\Delta \widehat{cost}} \ge budget\_pressure
$$

Tier 1 simplifications:
- two backends only
- `zero_calibration` default table
- explicit `stage`
- explicit or fixed `w_i`

Acceptance:
- Cheap-only decision works.
- Upgrade decision works.
- Higher `budget_pressure` reduces upgrades.
- Higher `w_i` increases chance of upgrade.

#### [x] Step 4. Implement scheduler + backend limits

Must implement:
- backend RPM cap
- backend concurrency cap
- admit / queue / reject / downgrade path

Acceptance:
- Runtime blocks or queues calls when backend capacity exhausted.
- Runtime never dispatches beyond configured backend concurrency.
- Queue behavior observable in tests or simulation.

#### [x] Step 5. Implement minimal zombie recovery

Tier 1 minimum:
- timeout detection
- cancel / mark failed
- release reserved budget
- release backend slot

Acceptance:
- Stuck workflow no longer holds slot forever.
- Recovered budget visible in state/logs.

#### [x] Step 6. Build minimal explicit agent loop

What this means in plain language:
- write smallest possible agent loop that can drive BudgetFlow
- loop can look like stripped-down ReAct, but does not need full LangChain or full SWE-agent behavior
- its job is to produce a sequence of steps like Localization -> Repair -> Validation and send explicit `TurnInfo` into BudgetFlow

Goal:
- feed explicit `TurnInfo`
- avoid framework integration complexity
- simulate Localization / Repair / Validation turns

Acceptance:
- Minimal agent loop can produce multi-step workflows.
- Runtime receives explicit stage labels.
- End-to-end call path exists from loop -> runtime -> backend stub.
- We can inspect one workflow trace and see why each step got cheap or strong model.

#### [x] Step 7. Add Tier 1 comparison modes

What this means in plain language:
- run same task with three different decision rules
- this is how we know BudgetFlow helps, not just runs

Need:
- Workflow-Level Router
- Budget-Only Step Router
- BudgetFlow Full

Acceptance:
- Same task input can run under all three policies.
- Output metrics comparable under same budget / backend config.
- One comparison table shows policy differences clearly.

#### [x] Step 8. Run smallest full comparison experiment

What this means in plain language:
- take a few tiny workflows
- run them from start to finish
- collect result numbers in one place

Target first:
- very small Lite-style subset
- low concurrency first, then small concurrent run

Acceptance:
- One reproducible run script/config exists.
- Metrics emitted: resolved/success proxy, total spend, budget violations, queue stats, backend pressure stats if simulated.
- Results are readable enough to decide whether Tier 1 idea is promising.

---

## Part 3. Acceptance checklist by milestone

### Milestone A. Runtime foundation

- [x] `paper1/src/budgetflow/` exists
- [x] package imports cleanly
- [x] core objects defined: `TurnInfo`, `Backend`, `WorkflowLedger`, governor state
- [x] no framework dependency required

### Milestone B. Hard budget core

- [x] reserve path implemented
- [x] settle path implemented
- [x] release path implemented
- [x] concurrent reserve cannot exceed budget
- [x] accounting distinguishes expected / reserved / actual

### Milestone C. Routing core

- [x] stage-aware weights wired
- [x] zero-calibration table wired
- [x] selector returns cheap vs strong tier correctly
- [x] pressure changes affect decisions

### Milestone D. Shared-resource governance

- [x] backend concurrency enforced
- [x] backend RPM enforced or simulated
- [x] queue or rejection path exists
- [x] zombie timeout releases resources

### Milestone E. Tier 1 evaluation readiness

- [x] explicit scaffold exists
- [x] three baselines runnable
- [x] first tiny experiment runnable end-to-end
- [x] result format ready for compare table

---

## Part 4. Known clarifications from design review

### Clarification 1

`paper1_design.md` still preserves broader paper language like `Verified resolved`.

Execution interpretation:
- Tier 1 may start from Lite warm-up subset.
- Design stays broad; current implementation stays narrow.

### Clarification 2

`paper1_design.md` preserves signal-source spectrum: explicit / callback / proxy / budget-only.

Execution interpretation:
- Tier 1 implements explicit path first.
- Callback / proxy remain preserved design, not immediate dependency.

---

## Part 5. Deferred until Tier 2

Do not prioritize before Tier 1 answer exists:

- LangChain adapter implementation
- proxy sidecar implementation
- public `.traj` replay calibration
- held-out calibration split pipeline
- richer backend pool
- large concurrency sweep
- full Verified paper run

---

## Current next move

**Next build step = inspect the current small-scale comparison outputs, decide whether current mock assumptions are too crude, then choose one of two directions: refine mock realism or start wiring one real backend while keeping the second tier mocked.**

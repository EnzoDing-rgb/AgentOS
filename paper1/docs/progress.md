# BudgetFlow Progress

> Living execution doc. Audience = human owner + agent.
>
> Update rule:
> - Follow current highest-priority phase.
> - Earlier phase details may be removed after project focus fully shifts.
> - Code root stays `paper1/dev/src/budgetflow/`.

---

## Part 1. Boss view

### Current phase

**Tier 1**

### What boss wants in current phase

Build minimum BudgetFlow runtime that can answer one question clearly:

> Under fixed budget and shared backend limits, does workflow-aware step budgeting beat weaker baselines on small coding-agent workload?

### What Tier 1 must contain

- Runtime governor, not full agent framework.
- Code root under `paper1/dev/src/budgetflow/`.
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
mini scaffold / SWE-agent-like loop
        -> TurnInfo
        -> BudgetFlow runtime
        -> 2-tier backend pool
        -> evaluator / harness
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

#### [ ] Step 1. Create runtime skeleton

Target dir:

```text
paper1/dev/src/budgetflow/
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

#### [ ] Step 2. Implement accounting core

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

#### [ ] Step 3. Implement model selection rule

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

#### [ ] Step 4. Implement scheduler + backend limits

Must implement:
- backend RPM cap
- backend concurrency cap
- admit / queue / reject / downgrade path

Acceptance:
- Runtime blocks or queues calls when backend capacity exhausted.
- Runtime never dispatches beyond configured backend concurrency.
- Queue behavior observable in tests or simulation.

#### [ ] Step 5. Implement minimal zombie recovery

Tier 1 minimum:
- timeout detection
- cancel / mark failed
- release reserved budget
- release backend slot

Acceptance:
- Stuck workflow no longer holds slot forever.
- Recovered budget visible in state/logs.

#### [ ] Step 6. Build tiny explicit scaffold

Goal:
- feed explicit `TurnInfo`
- avoid framework integration complexity
- simulate Localization / Repair / Validation turns

Acceptance:
- Scaffold can produce multi-step workflows.
- Runtime receives explicit stage labels.
- End-to-end call path exists from scaffold -> runtime -> backend stub.

#### [ ] Step 7. Add Tier 1 baselines

Need:
- Workflow-Level Router
- Budget-Only Step Router
- BudgetFlow Full

Acceptance:
- Same task input can run under all three policies.
- Output metrics comparable under same budget / backend config.

#### [ ] Step 8. Run smallest end-to-end experiment

Target first:
- very small Lite-style subset
- low concurrency first, then small concurrent run

Acceptance:
- One reproducible run script/config exists.
- Metrics emitted: resolved/success proxy, total spend, budget violations, queue stats, backend 429-like pressure stats if simulated.

---

## Part 3. Acceptance checklist by milestone

### Milestone A. Runtime foundation

- [ ] `paper1/dev/src/budgetflow/` exists
- [ ] package imports cleanly
- [ ] core objects defined: `TurnInfo`, `Backend`, `WorkflowLedger`, governor state
- [ ] no framework dependency required

### Milestone B. Hard budget core

- [ ] reserve path implemented
- [ ] settle path implemented
- [ ] release path implemented
- [ ] concurrent reserve cannot exceed budget
- [ ] accounting distinguishes expected / reserved / actual

### Milestone C. Routing core

- [ ] stage-aware weights wired
- [ ] zero-calibration table wired
- [ ] selector returns cheap vs strong tier correctly
- [ ] pressure changes affect decisions

### Milestone D. Shared-resource governance

- [ ] backend concurrency enforced
- [ ] backend RPM enforced or simulated
- [ ] queue or rejection path exists
- [ ] zombie timeout releases resources

### Milestone E. Tier 1 evaluation readiness

- [ ] explicit scaffold exists
- [ ] three baselines runnable
- [ ] first tiny experiment runnable end-to-end
- [ ] result format ready for compare table

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

**Next build step = Step 1: create `paper1/dev/src/budgetflow/` runtime skeleton and core file layout.**

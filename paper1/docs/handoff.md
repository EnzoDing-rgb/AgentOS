# BudgetFlow Handoff

This handoff is for a fresh Codex session taking over BudgetFlow. Read
`AGENTS.md` first, then this file, then `paper1/docs/north_star.md`. Treat
`paper1/docs/progress.md` as useful history but currently noisy and possibly
stale; do not spend time updating it unless a real decision changes.

## Current Commit

- Latest pushed commit: `2f32753` on `main`
- Commit message: `checkpoint budgetflow calibration and runtime updates`
- Fresh checks before that commit:
  - `PYTHONPATH=paper1/src:external/mini-swe-agent/src pytest -q paper1/tests` -> `598 passed`
  - `git diff --check` -> pass
  - `python3 -m compileall -q paper1/src/budgetflow` -> pass

These checks only prove the current tree is internally test-clean. They do not
prove that all new mechanism changes are conceptually right.

## Core Paper Logic

Claim 1 is the paper's center: under one shared hard budget, maximize normalized
verified resolved value, called Yield. Yield per Dollar is the main efficiency
diagnostic. Claim 2 should be treated as mechanism analysis that explains Claim
1, not as a separate product claim competing with Claim 1.

Verified pass is primarily evidence of model capability under a valid harness.
BudgetFlow does not make the model better at coding. Its contribution is
budget governance: deciding which tasks receive model opportunities, runway,
retry chances, stronger-tier access, and continue/stop decisions under one
shared budget. Harness and infra are validity gates and opportunity boundaries;
they should not be over-credited as paper mechanisms merely because fixing them
raises pass rate.

The clearest current framing is two-layer:

1. **Budget Regime Compiler**: pre-run budget regime. It compiles a shared hard
   budget for a fixed task set and fixed task order from ValueSource, Task
   Effort, reference cost scale, clean Cost Memory when available, and target
   pressure. It must not assign T2/T3 or any specific model tier to individual
   tasks.
2. **BudgetFlow Runtime**: runtime execution policy. It runs the same task
   order as every control and allocates model opportunities within the compiled
   budget. It decides when to continue, stop, retry, or use a stronger tier.
   It must not reorder tasks to chase value.

This boundary avoids circular reasoning: the compiler answers "how tight should
this workload's shared budget be?", while runtime answers "where should the
next model opportunity go under that budget?"

## Generalization Stance

The project should not claim one universal constant or threshold. Generalization
comes from a reusable calibration procedure:

- Pre-register task IDs, task order, ValueSource, model catalog, and budget
  compiler inputs.
- Use at most a small diagnostic calibration pass for a new workload/model
  catalog.
- Calibrate abstract inputs/functions only: Task Value scale, Task Effort,
  Model Fit, CostSource, budget pressure, runway/stop policy.
- Never tune on task IDs, repo names, known patches, harness quirks, or
  post-hoc outcome labels for the evaluation set.
- Freeze the compiler, catalog, ValueSource, task list/order, and policy config
  before held-out evidence runs.

The current 6x5 line should be treated as calibration/debug, not paper evidence.
It can expose infra bugs, budget-scale errors, missing Model Fit, or
task-level over-conservatism. Held-out 6x10/6x30-style runs are needed for
evidence after the mechanism is frozen.

## Important Recent Decision

Task order must be fixed across all policies. BudgetFlow may use value inside
routing, continue/stop, retry, and stronger-tier access decisions, but not by
solving high-value tasks first. Otherwise early budget exhaustion would make
Yield uninterpretable.

## Current Code State To Inspect

There is a recently committed Claude Code worker patch. Do not blindly accept
or reject it. It may be useful but may also be conceptually stale relative to
the current compiler/runtime boundary.

Reported worker changes include:

- `paper1/src/budgetflow/model_fit_estimator.py`
- `paper1/tests/test_model_fit_estimator.py`
- modifications in:
  - `paper1/src/budgetflow/adapter/strategies.py`
  - `paper1/src/budgetflow/experiments/budget_binding.py`
  - `paper1/tests/test_tier_frontier.py`

Worker's stated intent: estimate Model Fit from clean historical JSONL and feed
it into both Budget Compiler and task-level tier choice. The high-level
direction may be right, but future Codex should independently review whether:

- the estimator respects the two-layer boundary;
- the compiler is still only compiling a budget regime, not hidden per-task
  model assignments;
- Model Fit is used as a runtime allocation input without task-id or repo
  special casing;
- censored budget-exhausted rows are handled as incomplete evidence, not full
  samples;
- any constants, such as censored penalties or static token assumptions, are
  few, auditable, and not magic knobs.

Do not start from the worker's framing. Start from `north_star.md` and the
compiler/runtime boundary above, then decide what to keep, revise, or delete.

## Current Known Evidence And Risk

A clean 6x5 paid run exists:

- `paper1/data/runs/mainline_6x5_goldpass_20260616a.jsonl`
- Associated reports under `paper1/docs/reports/mainline_6x5_goldpass_*`

High-level result from prior analysis:

- Infra looked clean for that run: completed rows, no major abort/provider
  failure signal.
- Bare T3 solved all five in that run.
- BudgetFlow task-level was too conservative and failed at least one high-value
  hard task because it effectively selected T2 where T3 was much more efficient.
- This exposed a mechanism issue: without meaningful Model Fit, task-level falls
  back to near-equal catalog priors and can underuse the Strongest Model.

Do not overfit this to SymPy or task `16988`. The reusable issue is: task-level
needs a credible Model Fit signal, and the compiler needs a credible budget
scale, while preserving fixed task order and shared-budget fairness.

## Suggested Next Work

1. Review the current diff/commit conceptually, not just by tests.
   - `git show --stat 2f32753`
   - inspect `model_fit_estimator.py`, `strategies.py`, and
     `budget_binding.py`
2. Decide whether the worker's ModelFit estimator belongs in the current design.
   Keep it only if it can be explained as an abstract, cross-task calibration
   input.
3. If keeping it, narrow the interfaces:
   - Compiler uses Model Fit only to improve budget-scale confidence and runway
     estimation.
   - Runtime uses Model Fit for allocation/tier decisions inside the fixed task
     order.
   - Neither layer hard-codes task/repo outcomes.
4. Add or revise tests around the conceptual contract, not only formulas:
   - compiler does not output per-task model assignments;
   - all policies preserve task order;
   - task-level can use learned/pre-registered Model Fit without task-id rules;
   - censored rows do not become complete observations.
5. Do not run another paid experiment until the above design is clear and
   no-paid gates pass.

## What Not To Do

- Do not keep optimizing the same 6x5 until it wins and then call it evidence.
- Do not explain passes as "stop-loss caused pass" or "segment caused pass."
  Say mechanisms allocate opportunity; model capability produces verified
  patches under a valid harness.
- Do not let the compiler silently become a router.
- Do not let runtime reorder tasks for value.
- Do not update `progress.md` just to tidy history. It is noisy; update only for
  a real new decision.

## Suggested Startup Prompt For Future Codex

Read `AGENTS.md`, then `paper1/docs/handoff.md`, then
`paper1/docs/north_star.md`. Your task is to independently review the latest
BudgetFlow calibration/runtime changes at commit `2f32753`, especially
`model_fit_estimator.py`, `adapter/strategies.py`, and
`experiments/budget_binding.py`. Do not assume the worker patch is correct.
Preserve the current two-layer boundary: Budget Regime Compiler compiles a
shared budget for a fixed task set/order and must not assign model tiers;
BudgetFlow Runtime allocates model opportunities within that budget and must
not reorder tasks. Decide what to keep, refactor, or delete, then implement only
the narrow changes needed to make the mechanism clean and testable. Run no-paid
verification before any paid run.

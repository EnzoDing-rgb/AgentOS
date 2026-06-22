# BudgetFlow Handoff

Date: 2026-06-22
Repo: `/root/.dev/AgentOS`
Branch: `main`

## Read First

- `AGENTS.md` is the operating contract.
- `paper1/docs/north_star.md` is the research vocabulary and claim source.
- `paper1/docs/progress.md` has the latest timeline entry.

## Current Objective

Do not resume paid experiments blindly. The active work is to make
BudgetFlow task-level routing auditable across its left and right frontier
boundaries before the next 4x30 paid attempt.

The useful framing from the user:

- Left boundary: reference-tier dominance, mostly T2, T2 with stop-loss or
  bounded Strongest Model probes.
- Right boundary: Strongest Model dominance, strongest-first diagnostics, or
  pure T3 when it is projected cheaper in total and materially higher fit.
- Mixed routing is desirable only when the evidence supports a real allocation
  problem. Do not force mixture to make BudgetFlow look better.

## What Changed In This Slice

- Task-start marginal Yield no longer multiplies the threshold by T3/T2 price
  ratio. Extra expected cost already contains the stronger-tier price.
- Runtime and budget compiler now share the same paid-upgrade gates:
  minimum fit gain, decisive fit gain, criticality/value gate, and high Task
  Effort gate.
- Cold-start task-level BudgetFlow can do bounded uncertainty probes when
  ModelFit is not trusted. The current 4x30 dry-run projects `24 T2 / 6 T3`.
- Fixed-tier task-level routing is split into two cases:
  silent degeneration still halts, explicit frontier selection is allowed and
  warned.
- Run guards now recognize both reference-frontier and strongest-frontier
  explanations from trace/policy decision fields.
- Budget compiler now builds `frontier_diagnostic` before the pressure
  contract, so `strongest_cost_dominant` pure T3 becomes an assertion, not a
  contradictory degeneration violation.
- Readiness gates now treat `reference_cost_dominant` and
  `strongest_cost_dominant` symmetrically.
- Missing tier backends fail fast instead of silently routing to the last
  backend.
- The stale compiler helper `_projection_price_ratio()` was deleted.

## Verification Already Run

- `PYTHONPATH=paper1/src pytest -q paper1/tests/test_compare_readiness.py paper1/tests/test_budget_binding.py paper1/tests/test_task_level_expected_cost.py paper1/tests/test_run_guards.py`
  - Result: `145 passed`
- `PYTHONPATH=paper1/src pytest -q paper1/tests/test_compare_setup.py paper1/tests/test_run_series.py paper1/tests/test_failure_classification.py paper1/tests/test_model_tiers.py paper1/tests/test_trace_fields.py paper1/tests/test_recost.py`
  - Result: `142 passed, 5 skipped`
- `python -m py_compile` on edited runtime modules
- `git diff --check`

## Dry-Run Results

Temporary plans were written under `/tmp` and should not be treated as
committed evidence.

- Cold-start plan:
  - `/tmp/budgetflow_4x30_cold_plan.json`
  - readiness PASS
  - frontier posture: `reference_cost_dominant`
  - BudgetFlow task-level projection: `24 T2 / 6 T3`
  - warning: diagnostic only because projection confidence is unvalidated
- Stage-1 calibrated plan:
  - `/tmp/budgetflow_4x30_stage1_calibrated_plan.json`
  - readiness PASS
  - frontier posture: `strongest_cost_dominant`
  - BudgetFlow task-level projection: pure T3
  - warning: diagnostic only because projection confidence is unvalidated

## Current Paid-Run State

No paid process was running when checked. The interrupted run
`paper1/data/runs/mainline_4x30_stratified_orderfix_20260622-0.jsonl` has 29
rows: 10 `bare_t3_baseline`, 8 `enterprise_router_baseline`, 6
`bare_t2_baseline`, 5 `budgetflow_task_level`. It stopped near stage 1 and is
not paper evidence.

## Recommended Next Session

1. Check `git status`, latest commit, and whether this handoff has been
   committed and pushed.
2. Re-run a narrow no-paid gate if any code changed after this handoff.
3. Decide which budget plan to use for the next 10+10+10 paid attempt:
   cold-start mixed probe is better for boundary exploration; stage-1 calibrated
   pure T3 is a strongest-frontier diagnostic, not mixed-routing evidence.
4. Before paid execution, regenerate the selected budget plan into a committed
   report path if it will be used as the run contract.
5. Run 4x30 in staged form only. Inspect after the first 10 task positions
   across all four policies. Stop on billing/provider/preflight blockers,
   harness contamination, silent fixed-tier degeneration, or clearly hopeless
   BudgetFlow signal.

## Suggested Skills

- `diagnose` or `superpowers:systematic-debugging` if a paid or no-paid gate
  fails.
- `review` if asked to audit the final diff before running.
- `handoff` only when preparing another session; keep it short and factual.

## Prompt For A Fresh Agent

You are continuing BudgetFlow in `/root/.dev/AgentOS`. Read `AGENTS.md`,
`paper1/docs/north_star.md`, `paper1/docs/progress.md`, and `handoff.md`.
Do not run paid experiments until no-paid gates pass. The current goal is to
prepare a staged 4x30 BudgetFlow task-level experiment without reward hacking:
study the left/right frontier boundaries, keep pure T2/T3 baselines strong,
allow fixed-tier BudgetFlow only when trace/readiness explicitly explains it as
frontier selection, and stop on real infra or mechanism blockers. Check git
status and latest commits first, then decide whether to use a cold-start mixed
probe plan or a stage-1-calibrated strongest-frontier diagnostic plan.

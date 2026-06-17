# Mainline 6x5 Refit Diagnostic - 2026-06-17

## Objective

Run the first paid diagnostic after the calibration/runtime boundary refactor.
This run checks whether workload-level Model Fit from the budget plan reaches
runtime allocation, whether the shared hard budget behaves coherently, and
which mechanism layer limits value efficiency before any larger paid run.

This is a refit diagnostic, not paper-level evidence.

## Run Inputs

- Run id: `mainline_6x5_refit_20260617-0`
- JSONL: `paper1/data/runs/mainline_6x5_refit_20260617-0.jsonl`
- Summary: `paper1/data/runs/mainline_6x5_refit_20260617-0.summary.log`
- Budget plan: `paper1/docs/reports/mainline_6x5_refit_budget_plan_20260617.json`
- Budget audit: `paper1/docs/reports/mainline_6x5_refit_budget_audit_20260617.json`
- Value matrix: `paper1/docs/reports/mainline_6x5_goldpass_manual_value_matrix.json`
- Strategy set: `paper1/docs/config/paper_mainline_strategies.v1.json`
- Model catalog: `paper1/docs/config/model_tiers.default.json`

The run used a shared hard budget of `$1.6796` per strategy batch. The budget
plan was generated before commit `978c010`; its `model_fit_evidence.tier_fit`
keys are numeric strings in the artifact, but runtime normalized them to
canonical `tierN` keys. Commit `978c010` fixes the producer for future budget
plans.

## Results

`Yield` below is normalized verified resolved value against the frozen manual
value total `5.7`. `Yield Per Dollar` is normalized `Yield / actual_cost_usd`.

| Strategy | Verified Value | Cost | Yield | Yield Per Dollar |
| --- | ---: | ---: | ---: | ---: |
| `bare_t3_baseline` | 5.7 | 0.8048 | 1.0000 | 1.2426 |
| `budgetflow_task_level` | 5.7 | 0.8884 | 1.0000 | 1.1256 |
| `enterprise_router_baseline` | 5.7 | 0.9606 | 1.0000 | 1.0410 |
| `budgetflow_same_enterprise_router` | 5.7 | 1.3918 | 1.0000 | 0.7185 |
| `budgetflow_segment` | 2.7 | 1.2992 | 0.4737 | 0.3646 |
| `bare_t2_baseline` | 1.8 | 1.6786 | 0.3158 | 0.1881 |

## Artifact Audit

- JSONL rows: 30.
- `model_fit_source=budget_plan:historical_jsonl` on all 30 rows.
- `harness_trust=trusted` on all 25 passing rows.
- No provider, auth, parser, or abort blocker appeared.
- Failures were 3 `budget_fail` rows for `bare_t2_baseline` and 2
  `extract_fail` rows for `budgetflow_segment`.
- The budget plan recorded high-confidence Model Fit evidence from 5 tasks:
  tier1 catalog fallback `0.1500`, tier2 `0.6910`, tier3 `1.0000`.
- Budget audit confidence is high with overall spend MAPE `19.7%`.

Projection error was low for `bare_t2_baseline`, `bare_t3_baseline`,
`budgetflow_same_enterprise_router`, and `budgetflow_segment`; it was high for
`budgetflow_task_level` and `enterprise_router_baseline`, both of which spent
substantially less than projected.

## Interpretation

The refactor did what it was supposed to do operationally: Model Fit entered
runtime as workload-level budget-plan evidence, not repo/task-id runtime prior.
Task order stayed fixed and failures are attributable to mechanism behavior,
not provider or parser instability.

The Claim 1 diagnostic outcome is mixed. `budgetflow_task_level` preserved full
Yield and outperformed the enterprise router on Yield Per Dollar, but it did
not beat the all-Strongest baseline on this five-task slice. In this workload,
all-Strongest is still the best frontier point: full Yield at lower cost than
BudgetFlow task-level. That is a useful control result, not a paper win.

The segment policy is not ready for larger evidence runs. It consumed real
budget and lost verified value through extract/stagnation failures after gold
edits. Treat segment routing as a Claim 2 mechanism hypothesis that currently
needs reliability work or stricter gating.

The all-T2 control demonstrated the intended shared-hard-budget pressure: it
resolved early tasks cheaply, then exhausted the shared budget and lost the
remaining value.

## Follow-Up

- Keep the budget-plan Model Fit path; it is active and auditable.
- Do not use this run as paper-level Claim 1 evidence.
- Before scaling to 6x30, diagnose why all-Strongest is cheaper than
  task-level on this slice and whether BudgetFlow should absorb a stronger
  frontier principle instead of spending extra low-tier turns.
- Fix or disable segment routing for mainline Claim 1 evidence unless its
  extract/stagnation behavior improves under no-paid gates.
- Regenerate the next budget plan after `978c010` so `tier_fit` is written with
  canonical `tierN` keys.

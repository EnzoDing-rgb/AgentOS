# Paid Run Gate Hardening After Harness Review

Date: 2026-06-20

## Objective

Close the remaining paid-run blockers before another 4x25 diagnostic run. The
focus was narrow: make the SWE evaluation harness score only workspace diffs,
remove step-limit entrypoint drift, and align Budget Compiler planned-task
budget metadata with runtime mode names.

## Root Causes

1. The harness refactor had moved scoring toward workspace `git diff`, but the
   runner and official export path still had a fallback to an agent-submitted
   patch. That could reintroduce the exact adapter noise the refactor was meant
   to remove: a model can write a diff in its final response without actually
   editing the worktree.
2. The CLI default step limit was 60, but the lower-level runner still defaulted
   to 250. Any non-CLI caller could silently bypass the paid-mainline cap.
3. The Budget Compiler emitted `planned_task_budget_policy.mode` as the retired
   string `budgetflow_loose_task_budget`, while runtime/readiness use
   `budgetflow_planned_task_budget`.

## Changes

- `adapter.runner` now treats workspace `git diff` as the only scoreable patch.
  Submitted patches are still persisted as audit artifacts, but they are never
  used as the model patch for scoring or official prediction export.
- Official prediction export now reads only `workspace_patch`/`workspace.patch`.
- Observability schema now allows only `workspace_diff` or `none` for current
  `patch_source`; `submission` is invalid in current scoreable rows.
- Runner default step limit now uses `PAID_MAINLINE_STEP_LIMIT` instead of a
  separate hard-coded value.
- Budget Compiler imports the runtime planned-task-budget mode constant, and
  readiness blocks stale budget plans whose mode does not match runtime.
- Generated a fresh 4x25 plan:
  `paper1/docs/reports/mainline_4x25_tasklevel_fix_budget_plan_20260620b.json`.

## Verification

```bash
PYTHONPATH=paper1/src pytest -q paper1/tests
PYTHONPATH=paper1/src python paper1/src/budgetflow/run_mini_swe_compare.py \
  --ids "$TASK_IDS" \
  --strategies bare_t2_baseline,bare_t3_baseline,enterprise_router_baseline,budgetflow_task_level \
  --jobs 4 \
  --budget-plan paper1/docs/reports/mainline_4x25_tasklevel_fix_budget_plan_20260620b.json \
  --frozen-plan paper1/docs/reports/mainline_4x25_glm51_frozen_router_plan_20260618.json \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix paper1/docs/reports/mainline_4x25_glm51_manual_value_matrix_20260618.json \
  --paid-readiness-only
```

Results:

- no-paid tests: `701 passed`
- paid-readiness-only: `PASS`
- readiness facts: `step_limit=60`, T2=`openai/deepseek-v4-pro`, budget plan
  cap `$21.5059`, task-level projected tier mix `tier2=8`, `tier3=17`,
  degeneration `mixed_or_strongest`.

## Residual Risk

The plan still warns `projection_confidence=unvalidated`; the next 4x25 is a
diagnostic run, not final paper evidence. During the run, monitor actual
`patch_source`, harness trust, T2/T3 mix, provider health, and Yield per Dollar.

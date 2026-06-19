# Harness v2 upstream reflection

## Objective

Re-audit the interrupted `mainline_4x25_glm51_rerun_after_billing_20260618-0`
paid partial after the workspace-diff harness v2 slice, remove newly introduced
observability noise, and lock the remaining harness risks with tests.

## Findings

- The partial run is still diagnostic-only: 25 rows were written against a
  100-row heartbeat plan.
- The old checker warning that all historical rows were missing
  `workspace_patch` was a v2 schema bug. Historical `submission` rows do not
  need a `workspace_patch`; only `patch_source=workspace_diff` rows do.
- The two old `budgetflow_task_level` incomplete rows are real stale-harness
  artifacts from the submitted-patch-only runner:
  - `sympy__sympy-24102`: the worktree contained a scoreable edit in
    `sympy/parsing/mathematica.py`; current harness replay applies it and
    classifies it as a trusted failure, not an incomplete no-patch row.
  - `sympy__sympy-11870`: the worktree diff was compat/baseline noise and did
    not touch the target file. Current v2 baseline capture prevents this from
    being scored as an agent patch.
- The `bare_t3_baseline` 4/12 result is not explained by harness incompleteness:
  all 12 T3 rows are trusted, harness-evaluated `submission` rows with no
  provider/parser-wide anomaly. The low 4/12 is also not comparable to the other
  strategies' 2/4 or 2/5 counts because the run stopped with uneven strategy
  progress. On the four common tasks, all four strategies are 2/4.

## Files changed

- `src/budgetflow/run_observability/schema.py`
  - Removed `workspace_patch` from global desired fields.
  - Added a conditional `WORKSPACE_PATCH_MISSING` warning only when a current
    row has `patch_extracted=true` and `patch_source=workspace_diff` without a
    `workspace_patch` artifact.
- `src/budgetflow/adapter/runner.py`
  - Returns `trace_dir` and `trace_steps_path` in `MiniSweRunResult`.
- `src/budgetflow/experiments/compare_execution.py`
  - Persists `trace_dir` and `trace_steps` into JSONL records before building
    observability status.
- `tests/test_run_observability_audit.py`
  - Regression coverage for historical submission rows and current
    workspace-diff rows.
- `tests/test_compare_record_schema.py`
  - Regression coverage that run records expose trace artifact paths.
- `tests/test_workspace_patch_extraction.py`
  - Regression coverage that baseline-only compat diffs are not scoreable
    workspace patches.

## Verification

```bash
PYTHONPATH=paper1/src pytest -q \
  paper1/tests/test_run_observability_audit.py \
  paper1/tests/test_export_official_predictions.py \
  paper1/tests/test_workspace_patch_extraction.py \
  paper1/tests/test_compare_record_schema.py
# 67 passed

git diff --check

PYTHONPATH=paper1/src python -m py_compile \
  $(rg --files paper1/src/budgetflow paper1/tests | rg '\.py$')

PYTHONPATH=paper1/src pytest -q paper1/tests
# 683 passed
```

Checker replay:

- Old partial:
  `records=25 errors=2 warnings=6`, with remaining issue classes
  `SCOREABLE_UNTRUSTED_HARNESS=2`, `PARTIAL_RUN=1`,
  `HEARTBEAT_DEAD_PID=1`, and `COST_ACCOUNTING=4`.
- Harness v2 real-agent validation:
  `records=3 errors=0 warnings=1`, only the expected cost-accounting summary.

Forensic replay for `sympy__sympy-24102`:

- Patch source: old worktree `patch.txt`.
- Current local harness result: `patch_applied=True`,
  `harness_resolved=False`, `fail_to_pass_passed=False`,
  `pass_to_pass_passed=True`.
- Interpretation: v2 would turn the old incomplete row into a scoreable trusted
  fail. It would not change the pass count for that task.

## Residual risks

- Do not use the interrupted 4x25 partial as paper evidence.
- Future paid runs should use the v2 workspace-diff path and current checker.
- No additional paid-run blocker was found in this reflection. The next run can
  proceed after normal no-paid/provider gates, but the result must be evaluated
  on common task coverage rather than uneven partial strategy progress.

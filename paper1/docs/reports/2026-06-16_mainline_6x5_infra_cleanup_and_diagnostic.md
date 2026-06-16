# Mainline 6x5 Infra Cleanup and Diagnostic

## Objective

Clean the current paid-run path before a fresh 6x5 diagnostic, remove stale runtime fallbacks, fix shared mutable infra risks, and inspect the completed run before drawing conclusions.

## Files Changed

- Runtime and harness cleanup:
  - `paper1/src/budgetflow/local_harness.py`
  - `paper1/src/budgetflow/adapter/runner.py`
  - `paper1/src/budgetflow/run_trace.py`
  - `paper1/src/budgetflow/export_official_predictions.py`
  - `paper1/src/budgetflow/run_mini_swe_compare.py`
  - `paper1/src/budgetflow/experiments/compare_cli.py`
  - `paper1/src/budgetflow/experiments/compare_config.py`
- Observability, schema, and classification:
  - `paper1/src/budgetflow/failure_classification.py`
  - `paper1/src/budgetflow/observability.py`
  - `paper1/src/budgetflow/policy_memory.py`
  - `paper1/src/budgetflow/run_observability/audit.py`
  - `paper1/src/budgetflow/run_observability/checks.py`
  - `paper1/src/budgetflow/run_observability/schema.py`
- Tests:
  - `paper1/tests/test_compare_record_schema.py`
  - `paper1/tests/test_compare_setup.py`
  - `paper1/tests/test_failure_classification.py`
  - `paper1/tests/test_local_harness_pytest_nodes.py`
  - `paper1/tests/test_run_observability_audit.py`
  - deleted stale `paper1/tests/test_runner_exit_status.py`
- Budget plan metadata:
  - `paper1/docs/reports/mainline_6x5_budget_plan.json`

## Interface Decisions

- Active patch evidence is submission-only:
  - `patch_source` is now `submission` or `none`.
  - Worktree diff patch extraction and `worktree.patch` export are retired from current runtime.
- Runtime worktrees derive from `--runtime-root` only:
  - Removed active `--worktree-root` and related env override path.
- Local harness no longer runs `pip install -e .` per worktree:
  - Per-policy worktrees are isolated by `cwd` and `PYTHONPATH`.
  - This removes shared writes to the global Python environment under `--jobs 6`.
- Pre-provider budget blocks are explicit cost observations:
  - Future rows with no provider call use `usage_source=none` and `cost_mode=no_provider_call`.
  - Audit treats this as cost-confidence evidence when `total_cost=0`.
- Budget exhaustion remains scoreable:
  - `budget_exhausted` is `budget_fail`, not infra abort.
  - Missing turn trace is allowed for pre-provider budget blocks.

## Deleted Stale Paths and Tests

- Deleted worktree diff patch fallback from active runner/export paths.
- Deleted trusted fallback from policy memory trust.
- Deleted editable-install marker path and installer.
- Deleted stale runner exit-status test that protected retired fallback behavior.

## Verification

- `PYTHONPATH=paper1/src pytest paper1/tests -q`
  - `558 passed`
- `PYTHONPATH=paper1/src python -m py_compile $(rg --files paper1/src | rg '\.py$')`
  - pass
- `git diff --check`
  - pass
- Retired path scan:
  - no hits for `pip install -e`, `_pip_install_editable`, `_pip_marker_path`, `worktree.patch`, `extract_worktree_patch`, `trusted_fallback`, `BUDGETFLOW_WORKTREE_ROOT`, `set_worktree_root`, `--worktree-root`, or `BUDGETFLOW_USE_LEGACY_REPO_CACHE`.
- Provider signature:
  - `tier2` `openai/qwen3.7-plus`: pass
  - `tier3` `openai/gpt-5.4`: pass

## 6x5 Diagnostic Result

Run series:

- `mainline_6x5_paid_small_check_20260616_clean2-0`

Artifacts:

- JSONL: `paper1/data/runs/mainline_6x5_paid_small_check_20260616_clean2-0.jsonl`
- Summary: `paper1/data/runs/mainline_6x5_paid_small_check_20260616_clean2-0.summary.log`

Headline:

- 30 rows completed.
- No provider/parser/infra abort.
- 4 pass, 26 true_fail.
- 24 `budget_fail`, 1 `repair_fail`, 1 `loc_fail`.
- All strategies reached roughly 99.8-100% utilization, so the budget was genuinely tight.

Strategy outcomes:

- `bare_t2_baseline`: 0/5, spent 0.3314.
- `bare_t3_baseline`: 1/5, spent 0.3313.
- `enterprise_router_baseline`: 1/5, spent 0.3321.
- `budgetflow_same_enterprise_router`: 0/5, spent 0.3321.
- `budgetflow_task_level`: 1/5, spent 0.3321.
- `budgetflow_segment`: 1/5, spent 0.3321.

Budget calibration audit:

- Budget plan hard cap: 0.3321.
- Actual utilization:
  - `bare_t2_baseline`: 99.79%.
  - `bare_t3_baseline`: 99.76%.
  - all other strategies: 100%.
- Overall projection MAPE: 29.71%.
- Largest projection error: `bare_t2_baseline`, projected 55% utilization, actual 99.79%.

## Interpretation

The fresh 6x5 did its job as an infra and calibration diagnostic. It did not expose another paid-run infra blocker. It did expose that the current 6x5 cap is too tight for the task ordering and current policy behavior: most policies spend the batch cap on the first one or two tasks, then later tasks become pre-provider budget blocks.

This is not paper evidence for Claim 1. It is evidence that the current Budget Regime Compiler/cap calibration and early-task spend posture need another calibration slice before scaling to 6x30.

## Residual Risks

- Trace scratch directories are keyed by task and strategy, not run series. Running two identical task/strategy series concurrently could overwrite trace scratch. This did not affect the completed run because only one series was active.
- Checker currently reports shared-cap starvation as a top-level error-style issue. For 6x5 diagnostics this is useful pressure evidence, not automatically infra invalidation.
- PolicyMemory was disabled in this run, so learning-loop effects were not tested.
- The local 6x5 artifacts are not committed and should remain immutable local evidence.

## Next Recommended Slice

Use this 6x5 as calibration input, then adjust the Budget Regime Compiler or task-order/cap prior through a general rule, not a hand-picked cap. The next paid diagnostic should check whether task-level BudgetFlow can preserve budget runway across more than the first two tasks while still using T3 productively on high-value or stuck work.

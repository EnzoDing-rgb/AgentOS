# Patch Cleaner False-Negative Fix And Claim 1 Re-read

Date: 2026-06-23

## Objective

Fix the evaluation false negative where a valid workspace diff could be corrupted by patch cleaning and then scored as `model_patch=error: corrupt patch`. Re-read the latest 30-task evidence without mutating historical JSONL.

## Root Cause

`clean_scoreable_patch()` used `.rstrip()`. For git diffs, a trailing blank context line is encoded as a line containing a single leading space. `.rstrip()` removed that space and changed a valid diff into an invalid patch.

Canonical repro: `sphinx-doc__sphinx-8801` in `mainline_3x30_lhm_cycle_stage23_softgate_kv50_20260623`. BF selected T3 and produced a valid submitted patch, but the saved workspace patch was corrupted by cleaning. Re-evaluating the original submitted patch after the cleaner fix resolves the task.

## Code Changes

- Preserve patch trailing whitespace in `patch_cleaning.clean_scoreable_patch()` while still normalizing final newline.
- Add a runner guard: cleaned workspace patches must reverse-apply against the current workspace before becoming scoreable.
- Add `workspace_patch_drop_reason` observability for future extraction failures.
- Add AGENTS.md guidance for filtering speech-to-text noise.
- Update `north_star.md`: initial draft scope is Claim 1 only; Claim 2 is parked.

## Verification

- `PYTHONPATH=paper1/src /root/anaconda3/bin/python3.11 -m pytest -q paper1/tests/test_export_official_predictions.py paper1/tests/test_workspace_patch_extraction.py paper1/tests/test_compare_record_schema.py paper1/tests/test_failure_classification.py paper1/tests/test_run_observability_audit.py`
- Result: 149 passed.

## Corrected Evidence Readout

Historical JSONL remains immutable. The following are forensic re-evaluation corrections from `/tmp/budgetflow_patch_cleaner_corrections_20260623.json`.

Full 30-task run: `mainline_3x30_lhm_cycle_routefix_kv50_20260623`

| Strategy | Raw Yield | Corrected Yield | Cost | Corrected Yield/$ |
|---|---:|---:|---:|---:|
| pure T2 | 18.5 | 19.5 | 9.7729 | 1.9953 |
| pure T3 | 16.5 | 17.5 | 5.1336 | 3.4089 |
| BudgetFlow task-level | 20.0 | 22.0 | 7.1727 | 3.0672 |

Stage 2+3 run: `mainline_3x30_lhm_cycle_stage23_softgate_kv50_20260623`

| Strategy | Raw Yield | Corrected Yield | Cost | Corrected Yield/$ |
|---|---:|---:|---:|---:|
| pure T2 | 8.5 | 9.5 | 4.8634 | 1.9534 |
| pure T3 | 11.0 | 13.0 | 4.3992 | 2.9551 |
| BudgetFlow task-level | 10.0 | 12.0 | 4.1882 | 2.8652 |

## Interpretation For Draft

For Claim 1, the corrected complete 30-task run gives the cleanest current headline: BudgetFlow resolves the highest normalized value (22.0) under the same task set and compiled budget. Yield/$ remains a required diagnostic and pure T3 remains the strongest efficiency boundary. Claim 2 should not be claimed from this run.

## Residual Risks

- Value signal is still narrow: 24 normal tasks and 6 high tasks, no critical tasks.
- T3 is often cheaper in total because it uses far fewer turns despite higher per-turn pricing.
- The local harness remains part of the evidence system; patch extraction, compat patches, and host dependency behavior must be audited before using any run as paper evidence.

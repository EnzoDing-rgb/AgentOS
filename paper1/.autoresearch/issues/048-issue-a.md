# Verify value observability fields in run records

Confirm that value-aware fields are added to run records by the enrichment function.

## Scope

Read-only verification. No code changes, no API calls.

## Acceptance Criteria

- [ ] Read `src/budgetflow/run_mini_swe_compare.py` and confirm `_enrich_record_with_value()` exists and injects: task_value_profile, task_value, resolved_value, value_source, value_matrix_artifact, resolved_value_per_dollar.
- [ ] Confirm `--value-profile` and `--value-matrix` CLI flags are registered in the argument parser.
- [ ] Confirm `_init_value_observability()` is called in main().
- [ ] Run `PYTHONPATH=src python -m pytest tests/test_value_observability.py -v` and confirm 10 tests pass.
- [ ] Do not modify any file. Do not start paid API calls.

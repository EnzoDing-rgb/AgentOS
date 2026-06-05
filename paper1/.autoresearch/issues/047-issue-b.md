# Verify localization diagnostic reads touched_file_paths

Confirm the offline diagnostic in `value_matrix.py` prefers `touched_file_paths` and falls back to regex.

## Scope

Read-only verification. No code changes, no API calls.

## Acceptance Criteria

- [ ] Read `src/budgetflow/value_matrix.py` `diagnose_localization_progress()` and confirm it checks `touched_file_paths` first, falls back to regex.
- [ ] Confirm the artifact `docs/reports/047_value_matrix.json` has `runtime_field_available` and `runtime_field_turns`/`fallback_regex_turns` in meta.
- [ ] Run `PYTHONPATH=src python -m pytest tests/test_value_matrix.py -v -k 'Localization'` and confirm 10 tests pass.
- [ ] Do not modify any file. Do not start paid API calls.

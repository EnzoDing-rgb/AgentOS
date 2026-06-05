# Verify touched_file_paths in turn traces

Confirm that the runtime `touched_file_paths` field is wired into `_build_turn_trace()` and exported correctly.

## Scope

This is a read-only verification. No code changes, no API calls.

## Acceptance Criteria

- [ ] Read `src/budgetflow/adapter/bash_stage.py` and confirm `extract_touched_file_paths()` exists with conservative path extraction.
- [ ] Read `src/budgetflow/adapter/mini_swe_proxy.py` and confirm `touched_file_paths` is in the trace dict and passed at all 3 call sites.
- [ ] Read `tests/test_bash_stage.py` and confirm 17+ new tests for path extraction cover the main cases.
- [ ] Run `PYTHONPATH=src python -m pytest tests/test_bash_stage.py -v` and confirm all 22 tests pass.
- [ ] Do not modify any file. Do not start paid API calls.

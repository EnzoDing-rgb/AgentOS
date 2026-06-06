# Verify Q-fix consistency and manifest provenance

Confirm Phase Q fixes are applied and manifest provenance is correct.

## Scope

Read-only verification. No code changes, no API calls.

## Acceptance Criteria

- [ ] Read `docs/reports/047.md` and confirm API key gate now references DASHSCOPE_API_KEY/AICODE007_API_KEY (not DeepSeek/OpenAI).
- [ ] Confirm `docs/reports/047_value_matrix.json` manifest metadata shows Phase Q (not Phase P).
- [ ] Run `PYTHONPATH=src python -m pytest tests/test_value_matrix.py -v -k 'manifest'` and confirm 10 tests pass including the provenance test.
- [ ] Do not modify any file. Do not start paid API calls.

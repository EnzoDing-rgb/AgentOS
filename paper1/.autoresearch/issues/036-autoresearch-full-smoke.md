# 036 — AutoResearch Full No-Paid Smoke

## Goal

Execute a complete AutoResearch workflow end-to-end without consuming real API
calls, modifying src/, or running Docker harness.

## Issue

Verify the AutoResearch coordinator + CLI + fake worker complete the full loop:

1. Codex creates issue → AutoResearch creates workflow
2. Worker executes (fake) → worker_output.md lands on disk
3. Codex reviews artifacts → codex_review.md written
4. Mark complete → final.md written
5. Status/list confirm recoverable state

## Expected Artifacts

- `state.json` with complete workflow lifecycle
- `worker_prompt.md` (this prompt)
- `attempts/001/worker_output.md` (fake worker output)
- `codex_review.md` (Codex verdict)
- `final.md` (workflow summary)

## Constraints

- No paid API calls
- No src/ modifications
- No Docker or harness invocation
- No experiment data changes

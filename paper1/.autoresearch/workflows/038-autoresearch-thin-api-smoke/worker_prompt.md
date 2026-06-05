# 038 — AutoResearch Thin API Smoke

## Goal

Verify AutoResearch complete workflow loop using the thin API worker
(`scripts/autoresearch_api_worker.py`) which bypasses `claude -p` session
overhead by calling the Anthropic-compatible Messages API directly.

## Issue

Execute the following bounded task:

1. **Read** `docs/autoresearch_workflow.md` — understand the AutoResearch design
2. **Read** `docs/reports/036.md` — understand the previous no-paid smoke results
3. **Write** a concise `worker_output.md` summarizing:
   - What AutoResearch is (2-3 sentences)
   - What Phase F proved (2-3 sentences)
   - Whether the thin API worker bridge works (yes/no, with evidence)
   - Marker: `AUTORESEARCH_REAL_API_SMOKE:PASS`

## Hard Constraints

- Do NOT modify any files in src/, tests/, data/
- Do NOT run BudgetFlow benchmarks or experiments
- Do NOT run SWE-bench Docker or harness
- Write output to the path specified by the Worker bridge

## Expected Output

A markdown file containing:

- Files read (list)
- API call details (base URL masked, model, token counts)
- Artifacts produced (list)
- Summary (concise)
- Marker: AUTORESEARCH_REAL_API_SMOKE:PASS

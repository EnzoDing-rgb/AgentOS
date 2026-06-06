# 037 — AutoResearch Real-API Smoke

## Goal

Verify AutoResearch can complete a full workflow loop with a real Worker CLI
(not a fake script), consuming minimal API budget.

## Issue

Execute the following bounded task:

1. **Read** `docs/autoresearch_workflow.md` — understand the AutoResearch design
2. **Read** `docs/reports/036.md` — understand the previous no-paid smoke results
3. **Write** a concise `worker_output.md` summarizing:
   - What AutoResearch is (2-3 sentences)
   - What Phase F proved (2-3 sentences)
   - Whether the real Worker bridge works (yes/no, with evidence)
   - Marker: `AUTORESEARCH_REAL_API_SMOKE:PASS`

## Hard Constraints

- Do NOT modify any files in src/, tests/, data/
- Do NOT run BudgetFlow benchmarks or experiments
- Do NOT run SWE-bench Docker or harness
- Do NOT make API calls beyond what is needed to read the two files and write the output
- Write output to the path specified by the Worker bridge

## Expected Output

A markdown file written to the output path containing:

- Files read (list)
- Commands run (list)
- Artifacts produced (list)
- Summary (concise)
- Marker: AUTORESEARCH_REAL_API_SMOKE:PASS

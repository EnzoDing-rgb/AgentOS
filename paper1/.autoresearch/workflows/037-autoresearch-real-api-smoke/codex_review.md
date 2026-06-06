# Codex Gate Review — 037-autoresearch-real-api-smoke

## Verdict

VERDICT: BLOCKED
SCORE: N/A

## What Happened

AutoResearch CLI + worker bridge infrastructure worked correctly:
- `create` wrote workflow state + prompt to disk
- `run --worker-cmd` correctly invoked the wrapper script twice (attempt 1 at $0.30, attempt 2 at $0.50)
- Both attempts hit the budget cap before producing output

## Root Cause

`claude -p` spawns a full Claude Code session with substantial token overhead
(system prompt, tool definitions, workspace context, CLAUDE.md processing).
This overhead consumes the budget before the Worker can read its prompt and
write output — even for a trivial two-file-read task.

The Worker bridge (`--worker-cmd`) architecture is sound, but the specific
Worker CLI (`claude -p`) is too heavyweight for sub-$0.50 smoke tasks.

## Cost

- Attempt 1 ($0.30 cap): exceeded, no output produced
- Attempt 2 ($0.50 cap): exceeded, no output produced
- Total spent: < $1.00 (estimated; exact costs unavailable from CLI output)

## Evidence

- `state.json`: status=failed, attempt=2
- `worker_output.md`: "(pending)" — never written by Worker
- CLI stderr both times: "Error: Exceeded USD budget"

## Path Forward

Not a failure of AutoResearch — the coordinator + CLI + worker bridge work.
The fix is at the Worker adapter layer:

1. **Thin API wrapper** — use `curl`/`requests`/`httpx` to call the
   Anthropic-compatible API directly, bypassing Claude Code session overhead.
   A raw API call with a minimal system prompt would use ~2000 input tokens
   vs the ~20000+ tokens `claude -p` consumes for session setup.

2. **Alternative: lighter Worker CLI** — if a lighter-weight agent CLI exists
   (e.g., a direct model-inference script), use that instead of `claude -p`.

3. **Alternative: inline the task** — for such a small smoke (read 2 files,
   write 1 output), a non-LLM script could suffice. But that defeats the
   purpose of testing AutoResearch with a real agent Worker.

## Recommendation

OWNER_SUMMARY: AutoResearch worker bridge is functional but `claude -p` as
Worker CLI has too much session overhead for the $0.50 budget cap. The fix
is a thin API wrapper, not changes to AutoResearch itself.

NEXT_ACTION: implement `scripts/autoresearch_api_worker.py` that calls the
API directly with minimal tokens, then re-run smoke 037.

AUTORESEARCH_RESULT:BLOCKED

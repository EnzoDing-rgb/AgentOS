<!-- AutoResearch API Worker — factual metadata
  model: deepseek-v4-flash
  input_tokens: 4899
  output_tokens: 683
  metadata: worker_metadata.json
-->

```markdown
# AutoResearch Design Summary

The AutoResearch workflow replaces the manual copy-paste loop between Codex and Claude Code with a local coordinator that writes prompts, invokes the Worker, captures outputs, stores checkpoints, and asks Codex for a gate decision, preserving owner control over paid experiments and ensuring all interactions land on disk. It operates as a lightweight scheduler that automates issue creation, worker execution, review, and retry while keeping the owner as the ultimate authority for larger paid runs.

## Goal-Loop Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| 0         | Worker exits successfully; workflow marked **complete**. |
| 1         | Worker exits with nonzero; workflow marked **failed** (eligible for up to two automatic retries). |
| 2         | Pause condition triggered; workflow paused for owner or Codex approval before proceeding. |

**AUTORESEARCH_REAL_API_SMOKE:PASS**
```
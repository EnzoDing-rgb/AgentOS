<!-- AutoResearch API Worker — factual metadata
  model: deepseek-v4-flash
  input_tokens: 4891
  output_tokens: 1154
  metadata: worker_metadata.json
-->

# Thin API Worker: Critical Improvement Summary

The thin API worker replaces the costly `claude -p` direct-invocation approach with a lightweight, zero-API-cost alternative. In the Phase F no-paid smoke (report 036), the fake worker executed a full end-to-end workflow—prompt creation, worker execution, output capture, Codex review, and checkpointing—using zero API calls. The previous `claude -p` pattern would have incurred per-call billing for every small task.

**Cost difference:** `claude -p` costs money per invocation; the thin worker costs nothing for smoke and verification tasks.

**Why it matters for AutoResearch:** The thin worker enables:

- **Frequent, low-risk testing** – No-cost smoke loops allow rapid iteration and debugging without burning API budget.
- **Owner control retention** – The worker does not redefine goals or start paid experiments; it simply executes bounded issues and produces artifacts on disk.
- **Separation of concerns** – Real API calls are gated behind explicit `--paid-3x10` flags and owner approval, preventing accidental expensive runs.
- **Crash-recoverable workflow** – All outputs land on disk; state is captured without any live API dependency.

Without the thin worker, every coordination step would incur Claude Code API costs, making the AutoResearch loop too expensive for frequent smoke tests and retries. The thin worker is the critical enabler of a cost-controlled, gate-keeper-mediated autonomous loop.

AUTORESEARCH_REAL_API_SMOKE:PASS
# Model Tier Decision Note

Date: 2026-06-02

## Decision

Keep Qwen3-Coder-Plus as the default T4 for BudgetFlow compare runs.

Add GPT-5.3 Codex as an opt-in regular T4 candidate:

```bash
BF_T4_PROVIDER=gpt53_codex
```

Keep GPT-5.5 as ceiling-only T5.

## Evidence

- Local API ping confirmed `openai/gpt-5.3-codex` works through AICode007:

```text
[ping] openai/gpt-5.3-codex
[ok] pong usage=21/5
```

- Existing goldpass Qwen report says `all_pro` solved `5/5`, while blind `all_t4` solved `3/5`.
- The current blocker is DashScope/Qwen account state, not model routing.

## Rationale

Qwen3-Coder-Plus remains the default because it is code-specialized and was already integrated into the Qwen tier pool. GPT-5.3 Codex is plausible as a stronger regular T4, but should not silently replace Qwen in every run before a small controlled comparison.

The safe policy is:

```text
default: T1/T2/T3/T4 = Qwen pool
opt-in:  T4 = GPT-5.3 Codex
ceiling: T5 = GPT-5.5 only for all_gpt55/raw ceiling
```

This lets BudgetFlow test the real paper question without accidentally turning the main experiment into an expensive GPT-5.5 run.

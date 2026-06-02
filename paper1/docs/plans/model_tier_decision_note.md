# Model Tier Decision Note

Date: 2026-06-02

## Decision

Keep Qwen3-Coder-Plus as the default T4 for BudgetFlow compare runs.

Add GPT-5.3 Codex as an opt-in regular T4 candidate:

```bash
BF_T4_PROVIDER=gpt53_codex
```

Add Qwen Max as an opt-in regular T4 candidate:

```bash
BF_T4_PROVIDER=qwen_max
```

Keep GPT-5.5 as ceiling-only T5.

Do not silently switch the default T4 to a general `Max` model until a local gold-pass comparison proves it helps this SWE-mini repair workload at acceptable cost.

## Evidence

- Local API ping confirmed `openai/gpt-5.3-codex` works through AICode007:

```text
[ping] openai/gpt-5.3-codex
[ok] pong usage=21/5
```

- Existing goldpass Qwen report says `all_pro` solved `5/5`, while blind `all_t4` solved `3/5`.
- The current blocker is DashScope/Qwen account state, not model routing.
- Local GPT-5.3 Codex text-mode probe solved `3/3` gold-pass Sympy tasks, so GPT-5.3 is a valid strong T4 candidate for controlled probes.
- Qwen API preflight currently fails with `AuthenticationError: Incorrect API key provided`; no new Qwen performance conclusion can be drawn until this is fixed.
- Public model/pricing material says Qwen3.7-Max is a newer strong agentic/general model, with higher listed pricing than older cheap Qwen tiers.
- Public Qwen-Coder material positions the coder line for code generation, tool use, and software-engineering style workflows.

## Rationale

Qwen3-Coder-Plus remains the default because it is code-specialized and was already integrated into the Qwen tier pool. For SWE-Bench style software repair, a coder-tuned model is the more conservative default than a general max model unless local evidence says otherwise.

Qwen Max may be a stronger general/agentic model, but the paper question is not general chat ability or leaderboard maximum. It is repair success per budget unit inside this scaffold. The correct test is a small gold-pass side-by-side once DashScope auth works:

```text
all_t4(coder-plus) vs all_t4(max) vs BF_T4_PROVIDER=gpt53_codex
same tasks, same text/tool scaffold, same harness, same caps
```

Until then, switching to Max by default would mix two changes: model family and cost/ability assumption. That would weaken the BudgetFlow claim.

GPT-5.3 Codex is plausible as a stronger regular T4, but should not silently replace Qwen in every run before a small controlled comparison.

The safe policy is:

```text
default: T2/T3/T4 = Qwen pool
ablation: T1 only when explicitly requested
opt-in:  T4 = Qwen Max or GPT-5.3 Codex
ceiling: T5 = GPT-5.5 only for all_gpt55/raw ceiling
```

This lets BudgetFlow test the real paper question without accidentally turning the main experiment into an expensive GPT-5.5 run.

Implementation note:

- Main compare routing now skips T1 by default.
- `all_flash` / `all_t1` remain available for explicit ablation.
- `all_tier2`, `all_pro`, and `all_t4` select by backend tier, not list index, so skipping T1 does not shift baselines.

## Operational Gate

Before any Qwen-backed BudgetFlow run:

```bash
cd paper1
PYTHONPATH=src:../external/mini-swe-agent/src ../.venv/bin/python -u -m budgetflow.run_deepseek_smoke --tier compare
```

If this fails, do not run compare. Fix `DASHSCOPE_API_KEY` first.

## Candidate Comparison Command

After Qwen auth is fixed, run:

```bash
cd paper1
scripts/run-t4-candidate-goldpass3.sh t4_candidate_goldpass3
```

This compares:

```text
qwen default T4: qwen3-coder-plus
qwen_max T4:     qwen3.7-max
gpt53 T4:        gpt-5.3-codex text mode
```

Use the result to decide whether `qwen3-coder-plus` should remain the default or whether Max deserves promotion.

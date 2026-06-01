# Current Experiment Scoreboard

Date: 2026-06-02

This is the current evidence table for BudgetFlow paper progress. It is not the final paper table because Qwen/DashScope authentication is currently blocked.

## Trust Gates

| gate | status | evidence |
| --- | --- | --- |
| Gold-patch sanity only | active | `data/gold_pass_easy5_instance_ids.json` |
| Docker official eval | disabled | avoided due VM memory pressure |
| GPT-5.5 in normal pool | blocked by design | `build_compare_backends()` excludes `tier5_gpt55` |
| GPT-5.3 regular T4 | opt-in only | `BF_T4_PROVIDER=gpt53_codex` |
| Qwen Max regular T4 | opt-in only | `BF_T4_PROVIDER=qwen_max` |
| GPT text scaffold | opt-in only | `BF_GPT_TEXT_MODE=1` |
| Qwen preflight | required | `scripts/run-auto-v2-goldpass5.sh` exits before compare if Qwen ping fails |

## Results So Far

| run | purpose | tasks | policy/model | pass | cost | interpretation |
| --- | --- | ---: | --- | ---: | ---: | --- |
| `budgetflow_auto_v2_smoke` | BudgetFlow policy smoke | 2 | Qwen pool, tight policies | `1/6` rows, auto_v2 `1/2` | `3368.3` | First positive signal for automatic budget routing; not paper-ready |
| `gpt53_textmode_goldpass2` | strong scaffold ceiling anchor | 3 | SWE-mini + GPT-5.3 Codex text mode | `3/3` | `597.8` | Tasks are solvable when scaffold protocol is correct |
| `qwen_api_ping_20260602` | Qwen provider gate | 0 agent tasks | Qwen flash/pro ping | `0/2` API ping | minimal | Qwen compare currently blocked by invalid DashScope key |

## Key Findings

1. GPT-5.3 Codex is not the earlier failure source. The earlier `all_gpt53` run failed because AICode007/GPT did not work with mini-SWE tool-call mode. Text/backtick mode fixes this.
2. GPT-5.3 Codex solved `3/3` gold-pass Sympy tasks with SWE-mini in text mode.
3. BudgetFlow auto_v2 has a real positive smoke signal: it solved one task that `stage_blind_tight` and `budgetflow_full_tight` did not solve in the same smoke.
4. Qwen-backed formal comparison cannot continue until `DASHSCOPE_API_KEY` is fixed. Running it now would create infra-fail noise, not science.

## Current Commands

Qwen gate:

```bash
cd paper1
PYTHONPATH=src:../external/mini-swe-agent/src ../.venv/bin/python -u -m budgetflow.run_deepseek_smoke --tier compare
```

Resume formal BudgetFlow only after Qwen gate passes:

```bash
cd paper1
scripts/run-auto-v2-goldpass5.sh budgetflow_goldpass5_auto_v2_p030_v1
```

Compare regular T4 candidates only after Qwen gate passes:

```bash
cd paper1
scripts/run-t4-candidate-goldpass3.sh t4_candidate_goldpass3
```

Run GPT-5.3 text-mode ceiling without Qwen:

```bash
cd paper1
scripts/run-gpt53-textmode-goldpass3.sh gpt53_textmode_goldpass2
```

## Next Decision

After Qwen auth is fixed, run a small gold-pass comparison:

```text
budget_only_tight
stage_blind_tight
budgetflow_full_tight
budgetflow_auto_v2_tight
all_gpt53 text-mode ceiling/reference
```

The paper claim should only use rows where:

- gold sanity is PASS,
- provider preflight is PASS,
- local harness evaluates the model patch,
- GPT-5.5 is absent from budgeted routing.

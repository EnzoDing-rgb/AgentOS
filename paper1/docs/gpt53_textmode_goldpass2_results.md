# GPT-5.3 Text-Mode Goldpass Results

Date: 2026-06-02

## Purpose

Establish a low-cost scaffold/model ceiling anchor without Qwen, because the current Qwen/DashScope key is failing authentication.

This is not a BudgetFlow policy comparison. It is a task hardness and scaffold sanity probe.

## Command

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
BF_GPT_TEXT_MODE=1 BF_T4_PROVIDER=gpt53_codex FORCE_COLOR=1 \
HF_HOME=$PWD/data/hf_cache \
PYTHONPATH=src:../external/mini-swe-agent/src \
../.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --ids sympy__sympy-13480,sympy__sympy-17139 \
  --strategies all_gpt53 \
  --out-stem gpt53_textmode_goldpass2 \
  --step-limit 80 \
  --heartbeat 30 \
  --jobs 1 \
  --trace-quiet \
  --trace-turns \
  --trace-max-turns 40 \
  --per-task-cap 1200 \
  --pressure-init 0.30 \
  --resume
```

## Goldpass2 Result

```text
all_gpt53: 2/2 PASS
avg_turns: 7.0
avg_cost: 144.23 governor units
total_cost: 288.47 governor units
```

| task | verdict | gold file | turns | cost |
| --- | --- | --- | ---: | ---: |
| sympy__sympy-13480 | PASS | sympy/functions/elementary/hyperbolic.py | 7 | 138.8 |
| sympy__sympy-17139 | PASS | sympy/simplify/fu.py | 7 | 149.6 |

Output files:

```text
data/runs/gpt53_textmode_goldpass2.jsonl
data/runs/gpt53_textmode_goldpass2.summary.log
data/runs/gpt53_textmode_goldpass2.run.log
```

## Interpretation

GPT-5.3 Codex works with SWE-mini on these gold-pass Sympy tasks when using the text/backtick scaffold.

The earlier GPT-5.3 failures were caused by tool-call protocol mismatch, not task hardness. This makes GPT-5.3 Codex a valid strong regular T4 candidate for small controlled probes once BudgetFlow can route GPT backends through text mode.

## Current Blocker

Qwen-backed BudgetFlow comparison is still blocked by DashScope authentication:

```text
AuthenticationError: Incorrect API key provided
```

Until that is fixed, do not interpret Qwen BudgetFlow failures as model or routing failures.

## Goldpass3 Resume Result

The same stem was resumed with one additional task:

```bash
scripts/run-gpt53-textmode-goldpass3.sh gpt53_textmode_goldpass2
```

Resume skipped the first two completed `(strategy, task)` pairs and ran only `sympy__sympy-20212`.

Final result:

```text
all_gpt53: 3/3 PASS
total_cost: 597.8 governor units
avg_turns: 8.3
```

| task | verdict | turns | cost | note |
| --- | --- | ---: | ---: | --- |
| sympy__sympy-13480 | PASS | 7 | 138.8 | gold tracked |
| sympy__sympy-17139 | PASS | 7 | 149.6 | gold tracked |
| sympy__sympy-20212 | PASS | 11 | 309.4 | harness PASS, but gold tracking showed `none`; do not use this row for localization-rate claims |

Output:

```text
data/runs/gpt53_textmode_goldpass2.jsonl
data/runs/gpt53_textmode_goldpass2.summary.log
data/runs/gpt53_textmode_goldpass2.driver.log
```

This strengthens the task-hardness anchor: these gold-pass Sympy tasks are solvable by SWE-mini + GPT-5.3 Codex when the scaffold protocol is correct.

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

## Goldpass5 Tail Result

To avoid reburning the first three solved tasks, the remaining two gold-pass easy5 tasks were run separately:

```bash
scripts/run-gpt53-textmode-goldpass5-tail2.sh gpt53_textmode_goldpass5_tail2_foreground
```

Result:

```text
all_gpt53 tail: 1/2 PASS
combined gold-pass easy5 anchor: 4/5 PASS
tail total_cost: 502.6 governor units
```

| task | verdict | gold file | turns | cost | failure |
| --- | --- | --- | ---: | ---: | --- |
| sympy__sympy-13647 | PASS | sympy/matrices/common.py | 9 | 211.8 | - |
| sympy__sympy-16988 | FAIL | sympy/sets/sets.py | 11 | 290.9 | repair_fail; patch applied but fail_after still failed |

Output:

```text
data/runs/gpt53_textmode_goldpass5_tail2_foreground.jsonl
data/runs/gpt53_textmode_goldpass5_tail2_foreground.summary.log
data/runs/gpt53_textmode_goldpass5_tail2_foreground.driver.log
data/runs/trace_sympy__sympy-16988_all_gpt53/submitted.patch
```

Interpretation:

- GPT-5.3 Codex text mode is a useful regular T4 candidate, but it is not a perfect ceiling for this five-task set.
- `sympy__sympy-16988` is not an infra or harness failure: gold file was edited, patch extraction and application succeeded, `fail_before` failed as expected, and `pass_to_pass` passed. The model patch failed the target test.
- For BudgetFlow, this means `16988` should be treated as a hard repair case. If automatic budget cannot solve it without GPT-5.5, that is not automatically a routing bug.

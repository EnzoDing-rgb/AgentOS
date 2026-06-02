# BudgetFlow Auto V2 Smoke Results

Date: 2026-06-02

Run stem: `budgetflow_auto_v2_smoke`

Command shape:

```bash
cd paper1
FORCE_COLOR=1 HF_HOME=$PWD/data/hf_cache PYTHONPATH=src:../external/mini-swe-agent/src ../.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --ids sympy__sympy-20212,sympy__sympy-17139 \
  --strategies stage_blind_tight,budgetflow_full_tight,budgetflow_auto_v2_tight \
  --out-stem budgetflow_auto_v2_smoke \
  --step-limit 120 \
  --heartbeat 30 \
  --jobs 1 \
  --trace-quiet \
  --trace-turns \
  --trace-max-turns 60 \
  --per-task-cap 3000 \
  --pressure-init 0.30 \
  --resume
```

## Setup

- Agent scaffold: SWE-mini.
- Evaluation: local harness.
- Docker official eval: not used.
- GPT-5.5: not used.
- Model pool: Qwen T2/T3/T4 only.
- Resume: enabled.
- Jobs: 1, to avoid VM memory pressure.

## Result

| strategy | pass | spent | avg task cost | avg turns | T2 | T3 | T4 | failure classes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `stage_blind_tight` | 0/2 | 602.32 | 301.16 | 29.0 | 73% | 16% | 11% | `repair_fail=2` |
| `budgetflow_full_tight` | 0/2 | 1219.61 | 609.80 | 27.0 | 53% | 14% | 33% | `repair_fail=2` |
| `budgetflow_auto_v2_tight` | 1/2 | 1546.39 | 773.19 | 54.0 | 83% | 10% | 7% | `pass=1`, `repair_fail=1` |

Per-task details:

| task | stage_blind | budgetflow_full | budgetflow_auto_v2 |
|---|---|---|---|
| `sympy__sympy-20212` | FAIL, 354.91, 32t | FAIL, 883.67, 31t | PASS, 1348.53, 84t |
| `sympy__sympy-17139` | FAIL, 247.41, 26t | FAIL, 335.94, 23t | FAIL, 197.86, 24t |

## Interpretation

This is the first positive signal for automatic budget routing:

- Old `budgetflow_full_tight` spent more than `stage_blind_tight` and got 0/2.
- `budgetflow_auto_v2_tight` solved one task that both baselines failed.
- On the second task, auto_v2 found the gold file, opened a bounded T4 repair window, then stopped instead of continuing to burn budget.

This is not paper-ready yet. It is a smoke result, not a final claim.

## What Changed In Auto V2

- Treat stage weights as flat for this policy, so it does not over-penalize repair turns.
- Use a longer evidence window than current `budgetflow_full`.
- Open high-tier rescue only after concrete repair evidence.
- Keep stop-loss after the rescue window if repair does not convert.
- Keep GPT-5.5 out of normal budget routing.

## Current Takeaway

The direction is right:

```text
cheap search first -> evidence appears -> bounded strong repair -> pass or stop-loss
```

The next target is a 5-task run with `budgetflow_auto_v2_tight`. It should either:

- match `budget_only_tight` on pass count at lower cost, or
- beat `stage_blind_tight` on pass count without uncontrolled T4 spend.

If it cannot do either, the policy is still not paper-ready.

# Repair-floor v1 Negative Result

This run tested a simple rule:

> In `budgetflow_full`, once the agent reaches repair/validation or edit/test phases, do not let routing fall below T3.

Run:

```text
stem: data/runs/budgetflow_goldpass5_repairfloor_v1
tasks: same 5 gold-pass sympy tasks as qwen5pol_v2
policy: budgetflow_full_tight only
per-task cap: 3000 governor units
docker: no
gpt-5.5: no
```

## Comparison

| run | resolved | total cost | avg turns | note |
|---|---:|---:|---:|---|
| `budgetflow_goldpass5_qwen5pol_v2` / original BudgetFlow | 4/5 | 2712.6 | 31.2 | baseline |
| `budgetflow_goldpass5_repairfloor_v1` / repair floor | 4/5 | 6217.5 | 37.0 | same pass count, much higher cost |

Per-task comparison:

| task | original BudgetFlow | repair-floor v1 |
|---|---|---|
| `sympy__sympy-13480` | PASS / 236.9 / 17 | PASS / 241.5 / 18 |
| `sympy__sympy-13647` | PASS / 493.4 / 22 | PASS / 663.4 / 24 |
| `sympy__sympy-16988` | FAIL / 759.1 / 52 | FAIL / 2980.4 / 70 |
| `sympy__sympy-20212` | PASS / 554.1 / 31 | PASS / 1793.6 / 50 |
| `sympy__sympy-17139` | PASS / 669.1 / 34 | PASS / 538.7 / 23 |

## Decision

Do not keep repair-floor v1 as default behavior.

It fixes the wrong thing. The original failure pattern was real: after reaching useful repair evidence, weak turns can waste time. But a static floor simply turns that waste into more expensive T3 turns. On `sympy__sympy-16988`, it increased cost from 759.1 to 2980.4 and still failed.

The right next mechanism is not a permanent floor. It should be a bounded rescue/stop-loss rule:

```text
if gold/edit evidence exists
and repair has stalled for N turns
and budget headroom exists:
    try one bounded stronger rescue window
else:
    stop or submit/evaluate current patch
```

For GPT-5.3 Codex / GPT-5.5:

- GPT-5.3 Codex should be tested as a bounded rescue tier after model-name/API validation.
- GPT-5.5 remains ceiling-only, not a normal routing pool member.
- Neither should be used as a permanent floor.


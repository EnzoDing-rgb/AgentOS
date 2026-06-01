# Nightly Automatic Budget p030 Results

Run stem: `budgetflow_goldpass5_autobudget_p030_v1`

Task set: `paper1/data/gold_pass_easy5_instance_ids.json`

Date: 2026-06-02

## Setup

- Agent scaffold: SWE-mini.
- Evaluation: local harness only on gold-sanity PASS tasks.
- Docker official eval: not used.
- GPT-5.5: not used in budgeted routing.
- Model pool: current Qwen tiers.
- `per_task_cap=3000`
- `pressure_init=0.30`
- `step_limit=120`
- `jobs=1`
- Resume loop: active. One provider hang was recovered by timeout + resume.

## Main Result

| strategy | pass | cost | turns | failure classes |
|---|---:|---:|---:|---|
| `budget_only_tight` | 4/5 | 2824.1 | 273 | `pass=4`, `repair_fail=1` |
| `stage_blind_tight` | 3/5 | 1531.8 | 147 | `pass=3`, `repair_fail=2` |
| `budgetflow_full_tight` | 2/5 | 2622.2 | 197 | `pass=2`, `repair_fail=2`, `loc_fail=1` |

Per-task details:

| task | budget_only | stage_blind | budgetflow_full |
|---|---|---|---|
| `sympy__sympy-13480` | PASS, 151.1, 19t | PASS, 154.6, 19t | PASS, 227.4, 15t |
| `sympy__sympy-13647` | PASS, 230.7, 28t | PASS, 260.5, 24t | PASS, 531.3, 38t |
| `sympy__sympy-16988` | FAIL `repair_fail`, 863.3, 83t | FAIL `repair_fail`, 342.2, 39t | FAIL `repair_fail`, 665.2, 42t |
| `sympy__sympy-20212` | PASS, 491.6, 32t | PASS, 607.3, 41t | FAIL `loc_fail`, 1041.4, 78t |
| `sympy__sympy-17139` | PASS, 1087.4, 111t | FAIL `repair_fail`, 167.2, 24t | FAIL `repair_fail`, 156.8, 24t |

## Interpretation

Current BudgetFlow policy is not good enough.

It loses on both pass count and cost:

- Fewer passes than `budget_only_tight`: `2/5` vs `4/5`.
- Fewer passes than `stage_blind_tight`: `2/5` vs `3/5`.
- More expensive than `stage_blind_tight`: `2622.2` vs `1531.8`.
- It uses more T4 on easy tasks but does not convert that into more passes.

The main failure pattern:

- `budgetflow_full_tight` over-spends on repair-heavy routing.
- It can still miss localization (`sympy__sympy-20212`), even though both baselines pass it.
- Evidence rescue helps sometimes, but the stop-loss window is too short or poorly timed for `17139`.
- On `16988`, stronger repair windows did not solve the task and still consumed more than `stage_blind`.

## Runtime Finding

The resume loop worked.

One stage-blind run hung during a provider call. The outer timeout killed the process, and `--resume` skipped completed `(strategy, task)` pairs and continued from the next unfinished run. This validates the experiment runner direction.

Remaining runtime gap:

- LLM-call timeout is still too coarse. Current guard is process-level `timeout 1200s`.
- Add per-call or per-task stall guard if hangs repeat.

## Next Fix Direction

Do not switch benchmark or agent yet. Fix BudgetFlow policy first.

Recommended next changes:

1. Disable T1 in main routing after gold edit.
2. Add stronger localization protection: if no gold file after N turns, do not keep cheap LOC loops; either escalate localization or stop early.
3. Change `budgetflow_full` from repair-heavy to validation/localization-aware for this task set.
4. Keep bounded rescue, but tune the rescue window:
   - open only after real gold edit;
   - keep T4 for fewer but better-timed turns;
   - avoid T4 before evidence is strong.
5. Run a new 5-task compare with:
   - `stage_blind_tight`
   - current `budgetflow_full_tight`
   - a new `budgetflow_auto_v2_tight`

Success target for the next run:

```text
BudgetFlow_auto_v2 should be at least 4/5, and cost should be below budget_only_tight.
```

If it cannot beat `budget_only_tight` on pass count, it must at least beat it on cost at the same 4/5 pass count. If it cannot beat `stage_blind_tight` on either pass or cost, the automatic budget policy is not yet paper-ready.

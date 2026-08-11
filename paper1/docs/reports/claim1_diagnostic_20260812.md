# Claim 1 Diagnostic — Cross-Run Robustness of the BudgetFlow Win

Date: 2026-08-12. No-paid analysis. No model calls. No JSONL required.

This report re-derives the Claim 1 evidence from the four completed audit reports that are
already in this repo. It does not touch historical artifacts. The purpose is to answer one
question honestly: **is the BudgetFlow win robust, or is it an artifact of the value table and
execution noise?**

## 0. Sources and limitations

Sources (per-task matrices + strategy summaries from the audits):

| Run | Audit report | Value table | Policies | Completeness |
|---|---|---|---|---|
| 4x30 | `mainline_4x30_claim1_matrix_order_audit_20260628.md` | aggressive (10 high-value) | 4 | complete |
| 5x30 retryfix | `mainline_5x30_claim1_retryfix_clean_20260629_audit.md` | aggressive (10 high-value) | 5 | complete |
| 5x30 learnedprior | `mainline_5x30_claim1_final_forensic_value_sensitivity_20260629.md` | aggressive (10 high-value) | 5 | **partial_incomplete** |
| 5x30 frontierfix | `outdated/tmp_claim1_audit_frontierfix_20260630.md` | flat (6 high-value) | 5 | complete |

Limitations:

- The per-task matrix costs are **first-tier costs only** (cell format `P/F/A cost first-tier`),
  not total task costs. Use them as lower bounds, not as exact budget attribution.
- `learnedprior` is a **partial, interrupted run** (both BudgetFlow and pure T3 wrote only ~22/30
  rows, spend ~$6.2). Its numbers are not comparable to the complete runs. The north-star evidence
  table currently lists it as a "5x30 learned-router stress case"; it should be marked incomplete
  before any paper use.
- The three 5x30 runs share the **same task order** (task_ids from
  `mainline_5x30_claim1_learnedprior_final_budget_plan_20260630.json`) and the same $9.95 hard cap.
  The value tables differ on **exactly 5 tasks**: `flask-4992`, `flask-4045`, `sphinx-7686`,
  `sphinx-8282`, `sphinx-8801` (2.5 in aggressive runs, 1.0/1.5 in the flat run).

## 1. Evidence matrix (the honest main table)

| Run | Policy | Resolved | Spend | TRV | TRV/$ | BF margin vs best control |
|---|---|---|---:|---:|---:|---:|---:|
| 4x30 | pure T2 | 12/30 | $10.44 | 13.5 | 1.29 | |
| 4x30 | pure T3 | 15/30 | $9.46 | 18.0 | 1.90 | |
| 4x30 | learned router | 13/30 | $9.37 | 15.0 | 1.60 | |
| 4x30 | **BudgetFlow** | 14/30 | $7.98 | **18.5** | **2.32** | **+0.5 vs pure T3** |
| retryfix | pure T2 | 11/30 | $9.95 | 12.0 | 1.21 | |
| retryfix | pure T3 | 17/30 | $9.95 | **20.0** | 2.01 | |
| retryfix | learned router | 14/30 | $9.95 | 17.0 | 1.71 | |
| retryfix | budget-only | 11/30 | $9.95 | 12.0 | 1.21 | |
| retryfix | BudgetFlow | 15/30 | $9.95 | 17.5 | 1.76 | **-2.5 vs pure T3** |
| learnedprior* | pure T3 | 14/30 | $6.34 | 17.0 | 2.68 | |
| learnedprior* | BudgetFlow | 13/30 | $6.20 | 16.0 | 2.58 | **-1.0 vs pure T3** (run incomplete) |
| frontierfix | pure T3 | 15/30 | $9.95 | 16.5 | 1.66 | |
| frontierfix | learned router | 15/30 | $9.95 | 17.0 | 1.71 | |
| frontierfix | **BudgetFlow** | 16/30 | $9.95 | **18.0** | **1.81** | **+1.0 vs learned router** |

Mean BudgetFlow margin vs best control over the four runs: **(+0.5 - 2.5 - 1.0 + 1.0) / 4 = -0.5**.
BudgetFlow wins resolved count only in `frontierfix` (16 vs 15).

## 2. Cross-value-table re-scoring (the core result)

Same executed resolved rows, re-scored under both value tables. This separates "execution
difference" from "value-table difference".

| Run (executed rows) | BF TRV @ aggressive | best control TRV @ aggressive | BF TRV @ flat5 | best control TRV @ flat5 |
|---|---:|---:|---:|---:|
| 4x30 | **18.5** | T3 18.0 | 15.5 | **T3 16.5** |
| retryfix | 17.5 | **T3 20.0** | 16.0 | **T3 18.5** |
| learnedprior | 16.0 | **T3 17.0** | 14.5 | **T3 15.5** |
| frontierfix | 18.0 | router 17.0 | **18.0** | router 17.0 |

Reading:

- Under the **aggressive** value table, BudgetFlow wins 1 of 3 complete runs (4x30, +0.5) and
  loses 2 (retryfix -2.5, learnedprior -1.0).
- Under the **flat** value table, BudgetFlow wins 1 of 4 runs (frontierfix +1.0) and loses 3
  (4x30 -1.0, retryfix -2.5, learnedprior -1.0).
- **The 4x30 win is entirely value-table-dependent**: BudgetFlow's 2.5-point advantage comes from
  resolving `flask-4992` (2.5). Re-scored under the flat table, 4x30 becomes a 1.0 loss.
- The `frontierfix` win is execution-dependent, not value-table-dependent (native == flat5 there).

Conclusion: **BudgetFlow's win is not robust to either the value table or the run. It is a
minority outcome under every way the evidence is sliced.**

## 3. Where the flip comes from

Per-task BudgetFlow-vs-pure-T3 outcomes that flip across runs:

| Task | Value (aggressive) | 4x30 | retryfix | learnedprior | frontierfix |
|---|---|---|---|---|---|
| `flask-4992` | 2.5 | **BF P** ($0.19 T3), T3 F | BF F, T3 F | BF F, T3 F | value=1.0, both F |
| `sympy-15346` | 1.0 | both F | **BF P**, T3 F | T3 P, BF F | both F |
| `sympy-17655` | 1.0 | BF P, T3 F | **BF P**, T3 F | BF P, T3 F | **BF F**, T3 P |
| `seaborn-3407` | 1.5 | BF F, T3 F | **BF F**, T3 P | both F | **BF P**, T3 F |

`flask-4992` is decisive: in 4x30 BudgetFlow solved it with a $0.19 strong-model start and nobody
else did; in every other run it failed for everyone. **A single 2.5-point task that flips on
execution noise is what turns the aggressive-table runs into a win.** The other flips are all on
value-1.0 tasks and roughly cancel out in TRV.

## 4. Budget exhaustion: the concrete loss mechanism

Zero-cost placeholder rows (budget-exhaustion, not failed attempts):

| Run | BudgetFlow zero-cost rows | pure T3 zero-cost rows |
|---|---:|---:|
| 4x30 | 0/30 | 0/30 |
| retryfix | 5/30 | 0/30 |
| learnedprior | 8/30 | 8/30 (run incomplete) |
| frontierfix | 7/30 | 5/30 |

Tasks where BudgetFlow got no value but pure T3 did (and BudgetFlow never reached them — zero-cost
placeholder):

- **retryfix**: `django-13964` (1.0), `sphinx-7975` (1.0), `sympy-18621` (1.0) — 3 tasks / value
  **3.0**, all zero-cost rows for BudgetFlow, all passed by pure T3. Plus `seaborn-3407` (1.5) that
  BudgetFlow failed with a strong-model start while pure T3 passed. Total **4.5 value** left on the
  table to pure T3.
- **4x30**: `django-15851` (1.0), `django-15814` (1.0), `django-13964` (1.0) missed, but the
  `flask-4992` (2.5) win covered the gap.

Interpretation: in `retryfix`, BudgetFlow spent its $9.95 on earlier attempts such that it made 25
paid attempts to pure T3's 30, and missed the late winnable tasks the strong model reached.
First-tier costs show BudgetFlow burning early budget on failing attempts (`sphinx-7738` ≈ $1.01,
`pylint-6506` ≈ $0.50 in retryfix) and on phantom high-value tasks (see below).

## 5. Phantom high-value tasks

High-value tasks (value ≥ 1.5) that **every** policy failed:

| Run | Phantom tasks | Phantom value | BudgetFlow first-tier spend on them |
|---|---:|---:|---:|
| 4x30 | 4 | 9.0 | ~$1.18 |
| retryfix | 4 | 9.0 | ~$0.99 |
| learnedprior | 5 | 11.5 | ~$0.94 |
| frontierfix | 2 | 3.0 | ~$0.37 |

In the aggressive runs, 9–11.5 value sits on tasks nobody can solve. A value-aware allocator has
no way to know these are unwinnable in advance, so it reserves strong-model budget for them and
burns it. This is the natural failure mode the paper must either fix or report.

## 6. Task-level model advantage (frontier structure)

Comparable paid T2/T3 pairs per run (from the audits):

| Frontier bucket | retryfix | frontierfix |
|---|---:|---:|
| T2 cheaper pass | 4 | 6 |
| T3 cheaper pass | 5 | 5 |
| T2-only pass | 2 | 0 |
| T3-only pass | 0 | 0 |
| both fail | 6 | 7 |
| comparable tasks | 17 | 18 |

The batch does contain a real frontier (T2 wins some tasks, T3 wins others). BudgetFlow can only
win by capturing the cheap-model opportunities **and** not losing the strong-model-only passes. The
flip analysis in §3 shows it currently does neither consistently.

## 7. Conclusions

1. **The paper's positive claim is not robust.** BudgetFlow wins 1 of 4 runs at native value
   (4x30, +0.5), and its only clean five-policy win (frontierfix, +1.0) uses a flat value table.
   Mean margin vs the best control is **-0.5**. A reviewer who replays or cross-checks the three
   5x30 runs will see the win is borderline and run-dependent.
2. **The win is concentrated in single-task, value-table-dependent luck.** 4x30's win is
   `flask-4992` flipping to BudgetFlow; under the flat table it becomes a loss.
3. **The concrete, fixable failure is budget exhaustion.** In `retryfix`, BudgetFlow made 25 paid
   attempts vs pure T3's 30 and missed 3.0 value of late winnable tasks. It burned early budget on
   failing attempts and on phantom high-value tasks.
4. **`learnedprior` must be flagged incomplete** before any paper use.
5. **The positive-case audit is filed under `outdated/`** while the negative runs are in the main
   reports directory. Before the paper uses the frontierfix win as the headline, that report should
   be promoted and the negative runs should appear beside it, or the selection will look
   cherry-picked.

## 8. Recommended next experiment (paid, later, targeted)

Do not spend on the 17-run A/B/D shotgun from `conf_targets.md` yet. The diagnosis localizes one
decisive, testable fix:

- **Mechanism fix to test**: value-aware **stop/defer** (stop spending on failing attempts early;
  do not reserve strong-model budget for high-value tasks until there is evidence they are
  winnable — gate on Model Fit / estimated token demand), so BudgetFlow stays in budget to reach
  the late winnable tasks.
- **Single controlled paid run**: re-run the aggressive-table 5x30 protocol (same 30 tasks, same
  order, same $9.95, same value table, same verifier) with the fix. Success criterion: BudgetFlow
  no longer has zero-cost late rows on tasks pure T3 passes, and TRV ≥ pure T3.
- If it works, the paper gets a real, explainable mechanism claim ("budget-aware stop-loss makes
  value-aware allocation robust") instead of a fragile leaderboard. If it does not, the honest
  finding is that value-aware allocation is fragile under phantom high-value tasks — itself a
  reportable boundary result.

## 9. What is blocked without the run JSONL

- KV-cache cost-discount recosting (needs per-turn input/output token counts).
- Precise per-task budget attribution and stop-loss headroom (matrix costs are first-tier only).
- Re-running the repo audit tooling (`claim1_value_sensitivity.py`, `recost.py`, budget replay) on
  the actual rows.
- Clean value/budget sensitivity on the `frontierfix` run (its per-task rows exist only as the
  summarized matrix here).

If the run JSONL can be restored from the execution machine (`/root/.dev/AgentOS/...` per the
runtime CostSource audits), the audit tooling in `paper1/code/budgetflow/experiments/` can
reproduce all three sensitivity families directly.

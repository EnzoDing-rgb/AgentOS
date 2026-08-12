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

## 6.1 BudgetFlow vs the value-blind controls (learned router, budget-only)

The paper's core mechanism claim is "value-aware allocation beats value-blind allocation".
Per-task comparison of BudgetFlow against the two value-blind controls:

| Run | BF-only vs learned router | router-only | BF value delta | BF-only vs budget-only | budget-only-only |
|---|---:|---:|---:|---:|---:|
| 4x30 | 4 tasks / val 6.5 | 3 / val 3.0 | **+3.5** | 14 / val 18.5 | 0 |
| retryfix | 5 tasks / val 7.0 | 4 / val 6.5 | **+0.5** | 5 / val 7.0 | 1 / val 1.5 |
| learnedprior* | — | — | +4.0 (TRV 16.0 vs 12.0) | — | — |
| frontierfix | 2 tasks / val 2.0 | 1 / val 1.0 | **+1.0** | 5 / val 6.0 | 1 / val 1.0 |

**BudgetFlow beats the learned router and budget-only in every run.** The value signal works. This
is the paper's most robust empirical statement, and it is currently under-claimed.

BudgetFlow vs pure strong-model-only (pure T3) is the real contest:

| Run | BF TRV | pure T3 TRV | margin |
|---|---:|---:|---:|
| 4x30 | 18.5 | 18.0 | **+0.5** |
| retryfix | 17.5 | 20.0 | -2.5 |
| frontierfix | 18.0 | 16.5 | **+1.5** |

Among complete runs, BudgetFlow beats pure T3 in 2 of 3 by small margins and loses one by -2.5
(mean ≈ -0.17, effectively a toss-up). The paper's honest headline should be the first table
(value-aware beats value-blind, robustly), with the pure-T3 comparison reported as boundary.

## 6.2 Hard ceiling: tasks no policy ever resolves

Across all four runs and all five policies, 8 tasks are never solved:

| Task | Value |
|---|---:|
| `pallets__flask-4045` | 2.5 |
| `sphinx-doc__sphinx-7686` | 2.5 |
| `sphinx-doc__sphinx-8282` | 2.5 |
| `sympy__sympy-13177` | 1.5 |
| `pylint-dev__pylint-6506` | 1.0 |
| `sympy__sympy-12171` | 1.0 |
| `sympy__sympy-24102` | 1.0 |
| `sphinx-doc__sphinx-8273` | 1.0 |

Three of the four 2.5-value tasks are in this ceiling, so most of the "phantom value" (§5) is
unobtainable by any policy, not just by BudgetFlow. The remaining 2.5-value task `flask-4992` is
the one BudgetFlow alone solved in 4x30.

## 6.3 Consolidated budget-cap curve

No-paid replay (from the audits) of each policy's observed rows under tighter caps; this is the
paper's cost-value curve data.

| Cap | retry BF | retry T3 | retry route | front BF | front T3 | front route |
|---|---:|---:|---:|---:|---:|---:|---:|
| $2.99 | 5.0 | 5.0 | **8.0** | 7.5 | 7.5 | 7.5 |
| $3.98 | 6.0 | 7.5 | **10.0** | **9.0** | 8.5 | 8.5 |
| $4.98 | 8.5 | 9.5 | **12.0** | 10.0 | **11.0** | 8.5 |
| $5.97 | 9.5 | 9.5 | **12.0** | 11.0 | **12.0** | 11.0 |
| $7.47 | 11.5 | **17.0** | 14.5 | 12.0 | 12.0 | **13.0** |
| $9.95 | 17.5 | **20.0** | 17.0 | 17.0 | 16.5 | 17.0 |

- **retryfix**: learned router leads at every tight cap ($2.99–$5.97); pure T3 leads at loose caps.
  BudgetFlow never leads. Its cost-value curve is below both controls everywhere.
- **frontierfix**: BudgetFlow leads at $3.98 and ties at $2.99/$9.95; pure T3 leads at $4.98/$5.97.
  Competitive but not dominant.

The cost-value curve flips between runs, exactly like the point estimates in §1.

## 6.4 Self-consistency check

Recomputed resolved count / TRV from the per-task matrices for both BudgetFlow and pure T3 in all
three complete runs; all six spot checks match the audit strategy summaries exactly. The numbers
in this report are internally consistent with the audits.

## 6.5 Local tooling status

`python3` on this box has neither `pip` nor `pytest`; the audit/sensitivity tooling under
`paper1/code/budgetflow/` (e.g. `claim1_value_sensitivity.py`, `recost.py`) imports cleanly but the
test suite cannot run here. If replay tooling is needed later, run it where the JSONL and a
complete Python environment live.

## 7. Conclusions

1. **The value-aware claim is supported; the leaderboard claim is not.** BudgetFlow robustly beats
   the value-blind controls (learned router, budget-only) in every run (§6.1). Against pure
   strong-model-only it is a toss-up among complete runs (4x30 +0.5, retryfix -2.5,
   frontierfix +1.5). The paper should headline the first result and report the second as a
   boundary.
2. **The headline win still rides on single-task luck.** 4x30's win is `flask-4992` flipping to
   BudgetFlow; re-scored under the flat table it becomes a loss. frontierfix's +1.0 is execution
   luck on a favorable (flat) value table.
3. **The concrete failure is budget exhaustion under phantom high-value tasks.** In `retryfix`,
   BudgetFlow made 25 paid attempts vs pure T3's 30 and missed 3.0 value of late winnable tasks.
   It burned early budget on failing attempts and on phantom high-value tasks. The fix direction
   (progress-gated escalation) is inside-task policy and belongs to future work per
   `north_star.md`; the E1 oracle quantifies this boundary (see §8).
4. **`learnedprior` must be flagged incomplete** before any paper use.
5. **The positive-case audit is filed under `outdated/`** while the negative runs are in the main
   reports directory. Promote it or the selection will look cherry-picked.
6. **8 tasks are a hard ceiling** (3 of them 2.5-value); most of the phantom value is unobtainable
   by any policy, which bounds the upside of any allocation scheme.

## 8. Locked experiment plan (2026-08-12 addendum)

Two experiments are planned. E1 is locked; E2 is designed with two decisions ratified
(aggressive criticality value table; discrimination-first code task selection).

### E1 — 5x30 completion run (LOCKED)

One run, one self-consistent dataset. The point of running all lanes to completion is **not** the
oracle per se — it is that every comparison and curve in the paper is then derived from a single
dataset, eliminating the cross-run variance that makes the current four-run evidence fragile.

- Tasks: fixed 30-task set, fixed order. Policies: the 5 mainline strategies
  (bare T2, bare T3, learned router, budget-only, BudgetFlow task-level).
- Shared hard budget with the cap raised so every lane attempts all 30 tasks (the pure-T2 lane
  currently exhausts at ~24–26 tasks under $9.95; completion cap ≈ $12–13).
- Value table: aggressive criticality (10 high-value tasks incl. 4×2.5), frozen pre-registration.
- Outputs, all from the one dataset:
  1. 5-policy comparison at $9.95 (replayed from completed rows).
  2. Budget-cap replay at $2 / $4 / $6.5 / $9.95 — the paper's cost-value frontier figure.
  3. Observed-tier oracle (hindsight ceiling): the BF-to-oracle gap **quantifies the phantom-trap
     boundary** (how much value task-level allocation loses to high-value-but-unsolvable tasks).
  4. Per-task budget attribution to verify the $1.22 phantom-trap accounting end-to-end.
- **No 6th strategy.** Progress-gated escalation ("solvability gating") is inside-task escalation
  policy — exactly the "when should scarce strong-model opportunities be spent inside a task"
  question that `north_star.md` deliberately defers to future work (finer-grained allocation
  policy, stage/segment-aware routing + escalation + learned stop/continue). The phantom trap is
  reported as a measured boundary, not fixed in this paper.
- **Future-work entry (added 2026-08-12)**: progress-gated escalation is the concrete
  instantiation of future-work #1: probe solvability with cheap-model attempts before committing
  strong-model budget to high-value tasks; stop or escalate on progress evidence. The E1 oracle
  gap quantifies exactly how much value the phantom trap costs, giving this future-work entry a
  measured failure mode to motivate it.
- Cost: ~$50.

### E2 — 10+10 mixed batch (design; code task selection ratified, text tasks to finalize)

20 tasks, one shared budget, two verifier families:

- 10 code tasks selected from the fixed 30 with **discrimination-first + repo balance**
  (criterion ratified): prefer tasks where policies disagree in the audits; keep all six repos.
  Candidate list: `flask-4992`, `flask-4045`, `seaborn-3407`, `sympy-15346`, `sympy-17655`,
  `django-15814`, `django-13964`, `sphinx-7975`, `sphinx-7738`, `pylint-7993`
  (8 discriminating, 2 trap/ceiling, 1 easy-pass; 6 repos represented).
- 10 text tasks sampled from **public, authoritative datasets** (no self-made tasks):
  - 5 × SummEval (news summarization; human expert scores on 4 dimensions — the human scores let
    us validate the LLM judge: judge-human agreement is a paper number).
  - 5 × AlpacaEval (instruction following; standard LLM-as-judge benchmark, ~2k stars, active).
  - IFEval dropped by decision.
- Verifier forms in one batch: binary tests (code), graded rubric with human-validation
  (SummEval), LLM-as-judge (AlpacaEval). "Resolved" = score ≥ frozen threshold for TRV
  comparability; continuous score × value reported as secondary.
- Judge: frozen rubric + frozen prompt + frozen model, blind to policy, judge-human agreement
  reported on the SummEval subset.
- Values pre-registered before execution (code values from the aggressive criticality table;
  text values newly pre-registered, mixed 1.0/1.5/2.5).
- Analyses: overall + per-family TRV, oracle gap, verifier-type breakdown, stop-vs-downgrade
  behavior per family, judge robustness.
- This is the generalization evidence: value-aware allocation under heterogeneous verifiers,
  directly answering the "0/1 vs continuous" critique.
- Cost: ~$30–40.

### Dataset logistics

SummEval (100 articles / 1600 summaries) and AlpacaEval (805 prompts) are small; no Lite
versions exist or are needed. Both load via HuggingFace (`mteb/summeval`, `tatsu-lab/alpaca_eval`)
through the HF mirror configured for this host.

## 9. Insights from the 2026-08-12 discussion

1. **Dimensions narrow to value + effort.** "Difficulty" is a conflation; the correct second
   dimension is effort (run-before estimated token demand — the schema already names it
   `task_effort` / Estimated Task Token Demand). Value = exogenous economic weight injected
   before execution; effort = cost of attempting. High effort ≠ high value (reading many PDFs).
   The paper should drop "difficulty" language entirely.
2. **The learned-router control is the middle rung of the signal ladder.** budget-only
   (no signal) → learned router (effort signal) → BudgetFlow (effort + value). It is the
   strongest value-blind competitor in the data (current run: router 21.0 vs BF 15.0), so it
   must be kept — and trained/calibrated fairly (it imitates historical start-tier choices; its
   training provenance must be disclosed).
3. **Generalization needs a second domain, not an argument.** Value is domain-independent by
   construction; effort features are domain-specific (the router must be retrained per domain).
   The 10+10 mixed batch turns "mechanism-level portability" from an abstraction into evidence
   across verifier forms, with SummEval's human scores validating the judge.
4. **BudgetFlow's mechanism does not learn.** The allocation policy is frozen rules consuming
   pre-registered value; memory infrastructure exists but the mainline evidence ran with
   prior/adapt off; cross-run continual learning is future work. This asymmetry is deliberate:
   the comparison isolates the value signal ("learned, value-blind" vs "frozen, value-aware").
5. **The oracle is a boundary meter, not the headline.** The paper's claim is BF vs the
   value-blind baselines on one self-consistent dataset; the oracle quantifies the phantom-trap
   boundary and doubles as a standard regret-style diagnostic.

## 10. What is blocked without the run JSONL

- KV-cache cost-discount recosting (needs per-turn input/output token counts).
- Precise per-task budget attribution and stop-loss headroom (matrix costs are first-tier only).
- Re-running the repo audit tooling (`claim1_value_sensitivity.py`, `recost.py`, budget replay) on
  the actual rows.
- Clean value/budget sensitivity on the `frontierfix` run (its per-task rows exist only as the
  summarized matrix here).

If the run JSONL can be restored from the execution machine (`/root/.dev/AgentOS/...` per the
runtime CostSource audits), the audit tooling in `paper1/code/budgetflow/experiments/` can
reproduce all three sensitivity families directly.

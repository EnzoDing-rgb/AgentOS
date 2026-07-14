# 5×20 Postmortem Audit — June 15, 2026

## Executive Summary

The 5×20 experiment (20 tasks × 5 strategies = 100 target runs) spent **$3.50 raw**
across 137 rows (22 duplicate) but only achieved **22-47% budget utilization**
against a $1.2262/task hard cap. The budget was **not binding**.

Root causes (ranked):
1. **Projection overestimated costs by 24-73%** — bootstrap model with zero-history
   estimates inflated T3 costs especially. Budget set by p75 reference / 0.80 = $1.2262
   but actual max per-strategy spend was only $0.57.
2. **Stall guard truncated baselines** — bare/enterprise baselines were killed by
   `check_stagnation` which was BudgetFlow-only code. Fixed post-run.
3. **Run fragmented across 5 JSONL files** — sibling stems `v1-0` through `v1-4`
   due to resume instability. 37 duplicate rows cost $1.43 in overhead.
4. **20% of tasks are infrastructure/protocol noise** — Requests, some Django/Sphinx
   tasks hit parser crashes, billing guards, and model crashes with no agent work.

---

## 1. Budget Utilization: Why the Budget Was Not Binding

| Strategy | Projected | Actual | Util (proj) | Util (actual) | Error |
|---|---|---|---|---|---|
| bare_t2_baseline | $0.7546 | $0.5726 | 61.5% | 46.7% | -24.1% |
| bare_t3_baseline | $1.5091 | $0.4049 | 100.0% | 33.0% | -73.2% |
| enterprise_router_baseline | $0.7546 | $0.3697 | 61.5% | 30.2% | -51.0% |
| budgetflow_same_enterprise_router | $0.7546 | $0.2655 | 61.5% | 21.7% | -64.8% |
| budgetflow_segment (as budgetflow_full) | $0.9809 | $0.4489 | 80.0% | 36.6% | -54.2% |

**Overall projection MAPE: 53.5% → confidence: LOW.**

The budget was calculated as `p75($0.9809) / 0.80 = $1.2262` per strategy, but:
- The p75 reference itself was an overestimate (projected $0.98 vs actual $0.45 for budgetflow_segment).
- Bootstrap zero-history estimates inflated costs by 2-5× for tasks with no prior JSONL.
- T3 price normalization used a 2× diagnostic multiplier, amplifying the overestimate.
- The stall guard killed bare/enterprise baselines early, making their actual spend even lower.

### Fixes Applied
- `_build_pressure_contract()` now formalizes expected shape with grade (pass/warn/fail).
- `audit_calibration()` compares projected vs actual post-run and computes confidence.
- `calibrate_budget()` accepts `prior_calibration` — MAPE > 60% → BLOCK, 30-60% → WARNING.
- The 5×20 calibration audit is at `docs/reports/mainline_5x20_calibration_audit.json`.
  If this audit is passed as `prior_calibration` to the next budget plan, the readiness gate
  will **BLOCK** target_utilization mode until the projection model is recalibrated.

---

## 2. Old 16 (SymPy) vs New 4 (Requests, Django, Sphinx)

### Pass/Cost Summary

| Repo | Rows | Passes | Pass Rate | Total Cost | Avg Cost/Row |
|---|---|---|---|---|---|
| sympy | 60 | 25 | 41.7% | $0.8325 | $0.0139 |
| django | 20 | 2 | 10.0% | $0.6933 | $0.0347 |
| sphinx-doc | 10 | 2 | 20.0% | $0.1924 | $0.0192 |
| psf/requests | 10 | 0 | 0.0% | $0.3435 | $0.0344 |

The new 4 tasks (8 unique, 40 rows) contributed **$1.23 in cost (60% of total)** with only
**4 passes (13.8% of all passes)**. They are disproportionately expensive and low-signal.

### Per-Task Classification

#### Requests (psf__requests-1963, psf__requests-3362) — **HARNESS NOISE / PROTOCOL FAIL**
- **0 passes across 10 rows.**
- Dominant failure: `format_error_text_action` (parser crash on patch format) and `NameError` (model crash on test import).
- `requests-3362` shows `fail_after=pass; pass_to_pass=fail` — the agent produced a patch that passed f2p but broke p2p. This is a **legitimate agent failure** (localization incomplete).
- `requests-1963` had provider billing guard errors mid-run — **infrastructure noise**.
- Verdict: **Both tasks are harness-admissible but agent-unsolvable with current model tier.** The cookie module in requests is structurally different from the test pattern; models consistently produce incorrect patches.

#### Sphinx (sphinx-doc__sphinx-7975, sphinx-doc__sphinx-10325) — **MIXED**
- **sphinx-7975**: 2 passes (bare_t2, budgetflow_segment), 3 fails. The failures are `repair_fail` with `model_patch=ok; fail_after=fail` — the model produces a patch but it doesn't fix the issue. **Agent solvable by some strategies.**
- **sphinx-10325**: 0 passes, 5 fails. Dominant failure: `NameError` (model crash on Sphinx API deprecation — `Node.traverse()` vs `Node.findall()`). **Model capability gap** — the model can't navigate the deprecated Sphinx API.
- Verdict: **sphinx-7975 is harness-admissible and solvable.** sphinx-10325 is a **ceiling task** — requires model that understands Sphinx 7.x API changes.

#### Django (django__django-10924, 12113, 15388, 16046) — **INFRA/PROTOCOL HEAVY**
- **django-10924**: 1 pass (bare_t2), 1 model crash, 2 parser protocol failures, 1 repair fail. The pass at $0.12 is real but expensive.
- **django-12113**: 0 passes. Budget exhaustion, provider billing guard errors. **Infrastructure noise dominant.**
- **django-15388**: 0 passes. Budget exhaustion, provider insufficient balance, model crashes. **Infrastructure + model failure.**
- **django-16046**: 1 pass (bare_t3 at $0.005 — suspiciously cheap, likely trivial), 2 parser crashes, 2 model crashes.
- Verdict: **django-10924 and django-16046 are harness-admissible.** django-12113 and django-15388 are **infrastructure-contaminated** — billing guard and budget exhaustion prevent clean signal.

---

## 3. Raw 137 vs Dedup 100 — Cost Accounting

| Metric | Value |
|---|---|
| Raw rows (all JSONL fragments) | 137 |
| Raw paid cost | **$3.4960** |
| Dedup unique (strategy, task) rows | 100 |
| Dedup scored cost | **$2.0616** |
| Duplicate rows | 37 |
| Duplicate retry overhead | **$1.4343 (41% of dedup cost)** |

**Why duplicates happened:** The run was fragmented across 5 JSONL files (sibling stems
`v1-0` through `v1-4`). Each resume attempt re-ran some tasks that had already completed
in a previous fragment. The duplicate pairs are concentrated in new-4 tasks (Django,
Requests, Sphinx) where the agent frequently hit parser errors or billing guards and
was retried.

**The sibling stem problem is now addressed** by Phase 2 changes:
- PID-based lock files prevent concurrent allocation of the same stem.
- Sibling stem detection blocks new runs when multiple -N suffixes exist for the same series.
- `--repair` flag allows explicit acknowledgment and targeting of the latest stem.
- `_check_cost_accounting()` in the checker now separates raw/dedup/retry costs.

---

## 4. Exit Owner & Failure Classification

### By Strategy

| Strategy | Pass | Repair Fail | Extract Fail | Loc Fail | Budget Fail | Infra Fail |
|---|---|---|---|---|---|---|
| bare_t2_baseline | 6 | 1 | 11 | 1 | — | 1 |
| bare_t3_baseline | 9 | 8 | — | 2 | — | 1 |
| enterprise_router_baseline | 3 | 5 | 9 | — | 3 | — |
| budgetflow_same_enterprise_router | 3 | 6 | 9 | 1 | 1 | — |
| budgetflow_segment | 8 | 5 | 3 | 3 | — | 1 |

### Key Observations
- **11 extract_fail in bare_t2** — The T2 model (qwen3.7-plus) consistently fails to produce
  parseable patches. This is a **protocol/model quality issue**, not a harness problem.
- **bare_t3 has the most passes (9)** but also the most repair_fail (8) — GPT-5.4 produces
  patches but they often don't fix the issue.
- **enterprise_router and budgetflow_same_enterprise_router are dominated by extract_fail
  and budget_fail** — the frozen plan caps were too tight for these tasks, and the parser
  couldn't extract patches.
- **budgetflow_segment has the best signal** with 8 passes, balanced failure distribution,
  and only 3 extract_fail — the value-aware routing successfully avoided T2-only parser issues.

---

## 5. Residual Risks for Next Round

1. **Projection model is unvalidated** — bootstrap zero-history estimates overestimate by
   2-5×. Next round should either:
   - Use `frozen_plan_cap_sum` mode with explicit per-task caps, OR
   - Provide at least 10 tasks with historical JSONL data per strategy before using
     `target_utilization` mode.
2. **New-4 tasks (Requests, Sphinx, Django) should be pre-screened** with gold harness
   gates before inclusion in paid experiments. The Phase 6 15-task gate addresses this.
3. **Parser protocol fragility** — `format_error_text_action` is the dominant abort for
   T2 strategies. The parser is too brittle for non-SymPy repos.
4. **Provider billing guard instability** — at least 3 tasks hit provider balance/billing
   errors. Preflight provider signature checks are essential.
5. **Sibling stem fragmentation** is now addressed by Phase 2 lock files, but the
   existing 5×20 JSONL artifacts remain fragmented.

---

## 6. Recommendations for Next Paid Round

1. **DO NOT use target_utilization budget mode** until projection MAPE < 30%.
   Use `frozen_plan_cap_sum` with explicit per-task caps from the frozen plan.
2. **Drop psf__requests-1963 and psf__requests-3362** — 0 passes across 10 rows,
   dominated by parser and infrastructure noise.
3. **Drop django__django-12113 and django__django-15388** — infrastructure-contaminated.
   Keep django-10924 and django-16046 if gold harness passes.
4. **Keep sphinx-doc__sphinx-7975, drop sphinx-10325** as ceiling task.
5. **Use calibration audit from this report** as `prior_calibration` for the next
   budget plan to activate the readiness gate.
6. **Run at 15 tasks max** — the Phase 6 gate will identify which of the 15 candidates
   are harness-admissible.

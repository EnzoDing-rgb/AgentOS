# 6x10 Postmortem & Fix Plan — June 15, 2026

## What broke in 6x10

6x10 Stage 1 exposed 4 structural problems that make its results unusable as paper evidence.

### Problem 1: Budget asymmetry (BLOCK)

**Evidence.** `build_batch_budget_modes` gave `enterprise_router_baseline` and `budgetflow_same_enterprise_router` a different cap type (`frozen_plan_cap_sum`) from the other 4 strategies (`constrained_budget`). In 6x10:

| Strategy | Cap type | Actual cap |
|---|---|---|
| bare_t2_baseline | constrained_budget | $2.999 |
| bare_t3_baseline | constrained_budget | $2.999 |
| budgetflow_task_level | constrained_budget | $2.999 |
| budgetflow_segment | constrained_budget | $2.999 |
| enterprise_router_baseline | frozen_plan_cap_sum | $0.06 |
| budgetflow_same_enterprise_router | frozen_plan_cap_sum | $0.06 |

The 50x cap difference means `enterprise_router` variants operated under an entirely different scarcity regime. Cross-policy comparison is invalid when two policies had 50x less budget.

**Fix (Phase 1).** `build_batch_budget_modes` rewritten: all 6 paper mainline strategies get `constrained_budget` as shared batch cap. `_frozen_routings` no longer triggers a separate cap. Frozen plan provides only `preferred_model`/`effort` priors via `effective_frozen_caps`, not per-task caps. Budget mode label: `frozen_router_caps` → `shared_batch_hard_budget`. `per_task_cap` and `auto_budget` are now explicit diagnostic modes, only active when `--per-task-cap` or `--auto-budget` is passed.

**Deleted.** `_cap_for` branch returning `frozen_cap_sum`. `_mode_for` returning `"frozen_router_caps"`. Scaling logic in `target_utilization` mode.

### Problem 2: No per-policy utilization audit (WARNING)

**Evidence.** Readiness reports aggregated utilization against one global hard cap, not per-policy. No prefix/stage waterline to detect burn-rate divergence in staged runs.

**Fix (Phase 2).** `CalibrationAudit`: per-policy utilization against each strategy's own cap. `ReadinessReport`: per-policy planned-vs-actual spend, WARNING if bare_t3_baseline or budgetflow_task_level deviates >2x from planned burn, BLOCK if >4x. Added `planned_spend_prefix` to `BudgetBindingPlan`.

**Deleted.** Single `hard_cap` for all strategies in utilization computation.

### Problem 3: T3 cost overestimation by budget compiler (WARNING)

**Evidence.** Budget compiler projected `bare_t3` cost from token prices (t3x3 catalog: T3 output = $5.38/1M vs T2 = $1.12/1M, ~4.8x). 6x10 actual data contradicts price-only projection:

| Strategy | Total cost | Avg cost/task | Avg turns |
|---|---|---|---|
| bare_t3_baseline | $0.3255 | $0.0326 | 5.3 |
| bare_t2_baseline | $0.5133 | $0.0513 | 14.5 |

`bare_t3` was the cheapest strategy — 37% cheaper than `bare_t2`. T3 solves faster (fewer turns), so higher per-token prices don't translate to higher total cost. Price-only projection is mechanically wrong. (Note: t3x3 catalog inflates T3 prices 3x over actual transaction prices; this is a diagnostic catalog, not billing reality — see Problem 4.)

**Fix (Phase 3).** `calibrate_budget`: computes `strategy_cost_per_effort` from historical JSONL (median of `hist_cost / bootstrap_difficulty` per strategy). When available, projection uses cost-per-effort instead of pure token-price ratio. Per-strategy calibration confidence replaces hardcoded `"unvalidated"`.

**Deleted.** `_estimate_t3_cost_share` hardcoded strategy→share mapping. Hardcoded `projection_confidence = "unvalidated"`.

### Problem 4: T3 binary gate + pre-selected backend (BLOCK)

**Evidence.** 6x10 used `model_tiers.t3x3.json` — a diagnostic catalog where T3 prices are inflated 3x above actual transaction prices. In that catalog:

- T3/T2 input ratio: 3.15, output ratio: 4.80
- `cost_ratio = 4.80 >= 1.8` → `early_allow_strongest = False`
- **The T3 gate was CLOSED in 6x10.**

This means `bare_t3` (the all_t3 baseline) had **zero budget constraint on tier access** — it always used T3 because `all_t3` strategy bypasses the router entirely — but every *budgeted* policy was blocked from escalating to T3 by the binary gate. The gate used inflated diagnostic prices that don't reflect actual billing, making the block spurious. Meanwhile:

1. **No ModelFit signal.** The gate ignored catalog `progress_priors` entirely. T3 progress deltas (0.01–0.03 vs T2) are tiny in both t3x3 and default catalogs.
2. **No TaskValue signal.** High-value tasks got no preference for stronger tiers.
3. **`value_aware_task_level` pre-selected backend once.** It computed one backend at init and re-used it every turn — making it a disguised `fixed_tier` baseline, not a value-driven policy.

**Fix (Phase 4).** Complete TierFrontier rewrite:

- Replaced `early_allow_strongest: bool` with `frontier_score(stage, allocation, budget_pressure) → float`. Score < 1.0: T3 justified. 1.0–2.0: marginal. > 2.0: T3 cost not justified.
- Score = `cost_ratio × (1 + pressure × 0.5) / (progress_delta × task_value)` when expected gain is positive; when gain is non-positive, score falls back to the cost ratio penalty.
- `model_fit` in `AllocationContext` allows per-task ModelFit override of catalog priors.
- `value_aware_task_level` now routes through `BootstrapPolicy` per-turn (segment=None — Claim 1). `budgetflow_segment` adds segment signal (Claim 2).
- `max_tier_pressure_threshold()` varies by cost_ratio (0.10 / 0.20 / 0.35), not hardcoded to 0.15.

**Deleted.** `early_allow_strongest` field and binary `cost_ratio < 1.8` gate. `task_level_backend` pre-computation. Hardcoded `strongest_threshold = 0.15`.

## Known remaining gaps (not yet fixed)

These are structural issues identified during the fix process. They are *not* addressed by Phases 1–4 and need explicit attention before paper-scale results are reported.

### Gap A: frontier_score is still too conservative in the default catalog

The default catalog has T2→T3 progress deltas of 0.01–0.03. With cost_ratio ≈ 1.60, the `frontier_score("repair")` ≈ 1.60 / 0.03 ≈ 53. This is well above 2.0 — BudgetFlow will still not send tasks to T3 under the advisory score.

The formula is correct; the problem is the input data. Catalog `progress_priors` are heuristic estimates — T3 is scored only 1–3% more effective than T2 at repair. Unless these priors are empirically calibrated from real run data, the frontier score will remain a "T3 avoidance" signal regardless of the binary/advisory distinction.

**What this means.** The fix removed two bugs (binary gate, pre-selected backend), but does not by itself make BudgetFlow *use* T3. Until empirical ModelFit data shows T3 > T2 by a meaningful margin, Claim 1's main policy will behave conservatively — correctly so, given the data it has.

### Gap B: ModelFit is structurally wired but empirically weak for fresh runs

`AllocationContext.model_fit` and the `model_fit_source` provenance are wired into runtime, turn traces, and `TierFrontier`. The canonical schema is per-tier rates such as `{"tier2": 0.30, "tier3": 0.80}`; `TierFrontier` converts this to strongest-minus-reference delta. On a fresh clean run with no prior traces, `has_model_fit = False` — the frontier score falls back to catalog progress priors, which are too weak to differentiate T2/T3 (see Gap A).

For the paper, ModelFit must be derived from empirical repair/localization/validation success rates per (tier, task_difficulty) — either from prior paid runs or from a dedicated calibration batch. The catalog priors are placeholders.

### Gap C: 6x10 traces are contaminated — calibration eligibility

The 6x10 JSONL has:
- Budget asymmetry (Problem 1): enterprise_router variants ran under $0.06/task caps
- Closed T3 gate (Problem 4): no budgeted policy could escalate to T3, so T3 cost/effort data exists only from `bare_t3` (no router, no budget constraint)
- Diagnostic catalog with 3x inflated T3 prices

These rows are **forensic evidence only**. They cannot enter cost-per-effort calibration or ModelFit estimation without contaminating the signal. The `calibrate_budget` function must distinguish:

| Calibration source | Eligible for cost-per-effort | Eligible for ModelFit |
|---|---|---|
| Fresh 6x10 (post-fix, clean budget, default catalog) | Yes | Yes |
| 6x10 (contaminated, t3x3 catalog) | No — forensic only | No — forensic only |
| Future staged runs under clean conditions | Yes | Yes |

`calibrate_budget` now applies row-level eligibility filters for known contamination: `frozen_router_caps`, diagnostic catalogs such as `t3x3`, budget errors, and known router-contamination markers. The filter intentionally does **not** exclude rows merely because the budget plan source says `frozen_plan_cap_sum`; after the budget semantics fix, that source can still produce a clean `shared_batch_hard_budget` runtime. Enterprise-router rows with `va_active=False` remain eligible; only impossible `enterprise_router + va_active=True` rows are treated as contaminated. A future gate should still validate source-level cap uniformity and catalog choice before ingestion.

### Gap D: Stage-specific frontier is fixed, but empirical stage ModelFit is still missing

`_budgetflow_max_tier()` now computes frontier score from the current turn stage instead of hardcoding `"repair"`. This prevents localization/validation caps from being opened by repair-only priors. The remaining gap is empirical: catalog progress deltas are still generic priors, not stage-calibrated outcomes from clean runs.

## Why 6x10 cannot resume

The 6x10 checkpoint is structurally invalid for the paper:

1. **Budget asymmetry cannot be fixed retroactively.** `enterprise_router` and `bf_same_enterprise_router` rows ran under $0.06/task caps vs $2.999 for others. Within-run decisions (backend selection, tier escalation, abort timing) were shaped by the wrong cap — traces are contaminated.
2. **T3 gate was closed by an inflated diagnostic catalog (t3x3).** No budgeted policy could escalate to T3. The only T3 data comes from `bare_t3` (unconstrained all-T3 baseline, no router). Cross-tier cost/efficiency comparison is impossible — we can't measure "did BudgetFlow correctly choose T3?" when the gate prevented any choice.
3. **`value_aware_task_level` was not value-aware.** It pre-selected one backend at init — the 6x10 result for this policy is indistinguishable from a `fixed_tier` baseline. Any Claim 1 evidence from 6x10 would be fabricated.
4. **Budget compiler projections were price-only under inflated T3 catalog.** The readiness report's "projected total ≈ $5.20" is based on T3 prices 3x above actual billing. Projection has no calibration backing.

**Verdict: 6x10 cannot resume. Start fresh with 6x30 Stage 1 using the default catalog (actual transaction prices) and the fixed code.**

## No-paid gates for next 6x30 attempt

### Gate 1: Cap uniformity (BLOCK)

All 6 paper mainline strategies must have identical `batch_budget_cap` and mode `shared_batch_hard_budget`.

```
Check: len(set(modes.batch_caps.values())) == 1 for the 6 mainline strategies
```

### Gate 2: Catalog is NOT a diagnostic/inflated catalog (BLOCK)

The loaded catalog must have T3 prices matching actual billing, not 3x diagnostic prices. Check: `cost_ratio < 2.5` (default catalog T3/T2 output ≈ 1.60). If cost_ratio >= 3.0, the catalog is likely a diagnostic/sensitivity variant — BLOCK unless `--diagnostic-catalog` is explicitly set.

### Gate 3: Per-policy calibration confidence (WARNING)

`calibrate_budget` must report per-strategy confidence. If no historical data exists, the projection is `"first_run_estimate"` (not `"unvalidated"`). If historical data exists but comes from contaminated runs (see Gap C), it must be excluded.

### Gate 4: Frozen plan priors only (WARNING)

If a frozen router plan is provided, `effective_frozen_caps` must not change batch caps. Verify `batch_caps[name] == constrained_budget` for all 6 strategies.

### Gate 5: Tier frontier calibration (WARNING)

`TierFrontier.from_catalog()` must return non-None with ≥2 tiers. The frontier score must be a finite positive float. If progress deltas are all < 0.05 (as in current catalog), emit WARNING: "catalog progress priors are too similar to differentiate T2/T3 — empirical ModelFit calibration recommended."

### Gate 6: Test suite (BLOCK)

`PYTHONPATH=src python -m pytest tests/ -q` must pass (currently 538 passed, 1 skipped).

### Gate 7: Budget plan decision (BLOCK)

`resolve_budget_plan` must return `decision = "PASS"` or `"GO"`. If `decision = "BLOCK"`, the run must not proceed.

## Disagreement notes

**On the plan's suggestion to "compute cost_per_bootstrap_effort from clean historical rows":** Agreed, implemented in Phase 3. The first paid run after this fix will have no clean historical data — the 6x10 rows are contaminated (see Gap C). The `calibrate_budget` function handles the no-history case; Gate 3 above formalizes the "first run" degradation.

**On the plan's Phase 2 per-policy utilization check:** Uses WARNING at 2x deviation, BLOCK at 4x. For staged runs, 1.5x threshold at Stage 1 would catch burn-rate issues earlier. I did NOT lower it because 6x10 data shows high variance (sympy-15346 is a 10x outlier), and a tight threshold would false-positive on legitimate heavy tasks. Keep 2x/4x for now, revisit after clean 6x10 data.

**On catalog choice for next run:** The t3x3 catalog was a diagnostic catalog (T3 prices 3x actual). This was appropriate for mechanism isolation (the plan called for "sensitivity to stronger-model cost"), but the inflated prices combined with the binary gate created an unintended interaction: budgeted policies were blocked from T3 while `bare_t3` (unconstrained) got free T3 access. The next run should use the default catalog (`model_tiers.default.json`) with actual transaction prices, or the t3x3 catalog must be paired with `--diagnostic-catalog` and the T3 gate must be advisory (which it now is, after the frontier_score rewrite).

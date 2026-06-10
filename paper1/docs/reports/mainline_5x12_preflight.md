# 5×12 Mainline Preflight — 2026-06-10

## Experiment shape

| Parameter | Value |
|---|---|
| strategies | 5 (bare_t2_baseline, bare_strong_model, enterprise_router_baseline, budgetflow_same_router, budgetflow_full) |
| tasks | 12 SymPy SWE-bench Lite |
| task_set_kind | familiar (8 canonical + 4 new zero-history) |
| budget_mode | frozen_router_caps (for enterprise_router + budgetflow_same_router) |
| hard_cap_usd | 2.70 (auto-computed from frozen plan selected cap sum) |
| budget_source | frozen_plan_cap_sum |
| planned_cap | 2.70 |
| value_profile | manual_value |
| value_source | pre_registered_manual (explicit --value-source-kind) |
| policy_memory | disabled (--disable-policy-memory) |
| auto_budget_learn | disabled (--no-auto-budget-learn) |
| model_catalog | docs/config/model_tiers.t3x2.json (revision 2026-06-10-t3x2) |

## Strategy design

| # | Strategy | Routing | Budget | Purpose |
|---|---|---|---|---|
| 1 | bare_t2_baseline | all_tier2 | shared batch | Cost floor: pure T2, no routing |
| 2 | bare_strong_model | bare_strong | shared batch | Capability ceiling: pure T3 |
| 3 | enterprise_router_baseline | enterprise_router | frozen per-task caps | Static plan, no ledger |
| 4 | budgetflow_same_router | budgetflow_same_router | frozen per-task caps | +shared ledger over same plan |
| 5 | budgetflow_full | budgetflow_value_aware | shared batch | +value-aware routing + tier frontier |

Mechanism isolation: strategies 2-4 use the same frozen router plan. Strategy 5 adds BudgetFlow's full policy stack (shared ledger, reservation/settlement, stop-loss, escalation, audit) with value-aware routing and tier frontier calibration.

Strategy 1 (bare_t2_baseline) is new — provides the T2-only cost floor against which all other strategies can measure their T3 premium.

## T3×2 diagnostic catalog

Uses `docs/config/model_tiers.t3x2.json`:
- T1: unchanged ($0.30/$1.50 per 1M)
- T2: unchanged ($0.28/$1.12 per 1M)
- T3: 2× transaction price ($0.588/$3.586 per 1M)

This is a mechanism-isolation sensitivity analysis. The 2× multiplier normalizes the stronger-model price so that BudgetFlow's T2/T3 tradeoff decision carries real weight — T3 is ~2× T2 cost, not nearly equal as in the default catalog.

NOT a real billing catalog. Real prices are in `model_tiers.default.json`.

## Tier frontier calibration

Loaded from `tier_frontier.py`, computed once at startup from the active catalog.

**Reference tier:** second-cheapest when ≥3 tiers (enterprise default T2), cheapest when only 2 tiers.
The calibration answers "is strongest tier worth upgrading from the reference tier?"

| Catalog | reference_tier | T3/T2 output ratio | T3/T2 input ratio | early_allow | Rule |
|---|---|---|---|---|---|
| default | 2 (qwen3.7-plus) | ~1.60 | ~1.05 | True | cost_ratio=1.60<1.8, progress OK |
| t3x2 | 2 (qwen3.7-plus) | ~3.20 | ~2.10 | False | cost_ratio=3.20≥1.8, too expensive |

With T3×2 catalog: BudgetFlow starts conservative (default_cap = T2), escalates to T3 when budget_pressure ≥ 0.15.

The frontier reason and calibration are recorded in:
- Top-level run record: `tier_frontier` field (via `to_dict()`)
- Per-turn trace: `tier_frontier_active`, `tier_frontier_reason`, `strongest_vs_reference_cost_ratio`, `strongest_progress_delta`, `max_tier_before_frontier`, `max_tier_after_frontier`

## 12 tasks (same as 4×12)

Canonical 8:
- sympy__sympy-13480
- sympy__sympy-14774
- sympy__sympy-16988
- sympy__sympy-20212
- sympy__sympy-12419
- sympy__sympy-19007
- sympy__sympy-20154
- sympy__sympy-20639

New 4 (zero-history):
- sympy__sympy-15011
- sympy__sympy-16792
- sympy__sympy-21055
- sympy__sympy-23117

## Cap sum breakdown

Same as 4×12: 2.70.

| Task | base_cap |
|---|---|
| sympy__sympy-13480 | 0.18 |
| sympy__sympy-14774 | 0.16 |
| sympy__sympy-16988 | 0.30 |
| sympy__sympy-20212 | 0.36 |
| sympy__sympy-12419 | 0.18 |
| sympy__sympy-19007 | 0.20 |
| sympy__sympy-20154 | 0.20 |
| sympy__sympy-20639 | 0.22 |
| sympy__sympy-15011 | 0.24 |
| sympy__sympy-16792 | 0.26 |
| sympy__sympy-21055 | 0.22 |
| sympy__sympy-23117 | 0.18 |
| **Sum** | **2.70** |

## Planned command

```bash
PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare \
  --strategies "bare_t2_baseline,bare_strong_model,enterprise_router_baseline,budgetflow_same_router,budgetflow_full" \
  --ids "sympy__sympy-13480,sympy__sympy-14774,sympy__sympy-16988,sympy__sympy-20212,sympy__sympy-12419,sympy__sympy-19007,sympy__sympy-20154,sympy__sympy-20639,sympy__sympy-15011,sympy__sympy-16792,sympy__sympy-21055,sympy__sympy-23117" \
  --value-profile manual_value \
  --value-matrix docs/reports/mainline_4x12_manual_value_matrix.json \
  --value-source-kind pre_registered_manual \
  --frozen-plan docs/reports/mainline_4x12_frozen_router_plan.json \
  --model-catalog docs/config/model_tiers.t3x2.json \
  --disable-policy-memory \
  --no-auto-budget-learn \
  --jobs 5
```

`--budget 2.70` is optional (auto-computed from frozen plan).

## Gate checklist

| Check | Result | Detail |
|---|---|---|
| Catalog preflight | PASS | frozen_router_caps, model_tiers.t3x2.json rev 2026-06-10-t3x2 |
| Value matrix coverage | PASS | 12/12 tasks, manual_value profile, pre_registered_manual |
| Frozen plan coverage | PASS | 12/12 tasks, planned_cap=2.70 == hard_cap=2.70 |
| Auto-budget rule | PASS | selected_cap_sum=2.7000, budget_source=frozen_plan_cap_sum |
| Paid readiness (auto) | PASS | budget=2.70 auto-computed |
| Paid readiness (explicit) | PASS | --budget 2.70 matches selected cap sum |
| Mismatch blocking | PASS | --budget 3.00 vs cap sum 2.70 → BLOCK |
| New test suite | PASS | 13/13 tier frontier tests |
| bare_t2_baseline routing | PASS | all_tier2 → always T2 |
| Tier frontier calibration | PASS | reference=tier2, T3×2 → early_allow=False, default → early_allow=True |
| Frontier observability | PASS | 6 fields (reference-named) in turn traces + top-level record |
| Full test suite | PASS | 387/387 (no regressions) |

## Verdict: GO

No blockers. All gates pass. Recommend proceeding to paid 5×12 diagnostic.

# 4×12 Mainline Preflight — 2026-06-10

## Experiment shape

| Parameter | Value |
|---|---|
| strategies | 4 (bare_strong_model, enterprise_router_baseline, budgetflow_same_router, budgetflow_full) |
| tasks | 12 SymPy SWE-bench Lite |
| task_set_kind | familiar (8 canonical + 4 new zero-history) |
| budget_mode | frozen_router_caps |
| hard_cap_usd | 2.70 (auto-computed from frozen plan selected cap sum) |
| budget_source | frozen_plan_cap_sum |
| planned_cap | 2.70 |
| value_profile | manual_value |
| value_source | pre_registered_manual (explicit --value-source-kind) |
| policy_memory | disabled (--disable-policy-memory) |
| auto_budget_learn | disabled (--no-auto-budget-learn) |
| model_catalog | docs/config/model_tiers.default.json (revision 2026-06-10-a) |

## Budget rule (NEW)

When `--frozen-plan` is passed without explicit `--budget`, the hard budget is set to
`FrozenRouterPlan.selected_cap_sum(task_ids)` — the sum of `base_cap` for only the
tasks selected via `--ids`, not all entries in the frozen plan file.

If `--budget` is explicitly passed and does not match the selected cap sum, the
paid-readiness check BLOCKs the run.

### 4×12 cap sum breakdown

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

## 12 tasks

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

## Planned command

`--budget 2.70` is optional (kept as double-check; auto-compute also produces 2.70).

```bash
PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare \
  --strategies "bare_strong_model,enterprise_router_baseline,budgetflow_same_router,budgetflow_full" \
  --ids "sympy__sympy-13480,sympy__sympy-14774,sympy__sympy-16988,sympy__sympy-20212,sympy__sympy-12419,sympy__sympy-19007,sympy__sympy-20154,sympy__sympy-20639,sympy__sympy-15011,sympy__sympy-16792,sympy__sympy-21055,sympy__sympy-23117" \
  --value-profile manual_value \
  --value-matrix docs/reports/mainline_4x12_manual_value_matrix.json \
  --value-source-kind pre_registered_manual \
  --frozen-plan docs/reports/mainline_4x12_frozen_router_plan.json \
  --model-catalog docs/config/model_tiers.default.json \
  --budget 2.70 \
  --disable-policy-memory \
  --no-auto-budget-learn \
  --jobs 4
```

## Gate checklist

| Check | Result | Detail |
|---|---|---|
| Catalog preflight | PASS | frozen_router_caps, model_tiers.default.json rev 2026-06-10-a |
| Value matrix coverage | PASS | 12/12 tasks × 3 profiles (equal, manual_value, bootstrap_difficulty) |
| Frozen plan coverage | PASS | 12/12 tasks, planned_cap=2.70 == hard_cap=2.70, unique priorities |
| Auto-budget rule | PASS | selected_cap_sum=2.7000, budget_source=frozen_plan_cap_sum |
| Paid readiness only (auto) | PASS | budget=2.70 auto-computed, no --budget flag needed |
| Paid readiness only (dual) | PASS | --budget 2.70 matches selected cap sum 2.70 |
| Mismatch blocking | PASS | --budget 2.70 vs 3-task cap sum 0.64 → BLOCK |
| Provider signature check | PASS | T1=779ms, T2=3015ms, T3=9572ms — all ok |
| Focused tests | PASS | 55/55 |
| Full test suite | PASS | 373/373 |

## Verdict: GO

No blockers. All gates pass. Recommend proceeding to paid 4×12.

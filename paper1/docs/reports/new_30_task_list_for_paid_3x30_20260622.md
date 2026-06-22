# 30-task list rebuilt for paid 3x30 staged run (2026-06-22)

**Date:** 2026-06-22
**Scope:** `paper1/docs/reports/` (task order, value matrix, budget plan)
**Decision:** Verified (no paid providers)

## Changes

### 1. Removals (2 tasks, evidence-backed)

| Task | Reason |
|------|--------|
| `matplotlib__matplotlib-25433` | host_dependency_contamination: ImportError `_c_internal_utils`, harness_trust=invalid, build_risk: full C extension build required |
| `pylint-dev__pylint-5859` | dependency_noise: pip install fails with astroid metadata, manifest flags as PASS_w_risk |

### 2. Additions (2 tasks, gold_harness verified)

| Task | Evidence |
|------|----------|
| `sphinx-doc__sphinx-7975` | gold_harness=PASS (2026-06-17 probe), repo=sphinx-doc/sphinx, adapter=stable |
| `sphinx-doc__sphinx-8801` | gold_harness=PASS (2026-06-17 probe), repo=sphinx-doc/sphinx, adapter=stable |

### 3. New task order (3 stages of 10)

Effort distribution: low=14, medium=9, high=7. Stages stratified by effort level and repo diversity.

| Stage | Avg Effort | Low | Med | High | Dominant Repos |
|-------|-----------|-----|-----|------|----------------|
| 1 | 28.6 | 4 | 3 | 3 | django(3), sympy(2), sphinx(2), flask(2) |
| 2 | 32.4 | 4 | 4 | 2 | sphinx(3), seaborn(3), django(2), sympy(2) |
| 3 | 25.9 | 6 | 2 | 2 | sympy(4), django(2), sphinx(2), pylint(2) |

### 4. KV50 budget plan

- **File:** `docs/reports/mainline_3x30_stage_prefix10_kv50_budget_plan_20260622.json`
- **Catalog:** `model_tiers.kv50.json` (2026-06-22 revision, T3 progress_prior 0.72/0.72/0.70)
- **Value matrix:** `mainline_3x30_criticality_value_matrix_20260622.json`

| Metric | Value |
|--------|-------|
| hard_cap_usd | $11.0158 |
| generation_mode | stage_prefix_pressure |
| decision | PASS |
| projected_spend (bare_t2) | $3.4209 |
| projected_spend (bare_t3) | $11.7290 |
| projected_spend (budgetflow) | $6.2663 |
| degeneration (overall) | mixed (T2=17, T3=13, 43.3% T3) |
| stage_prefix_degeneration | mixed (T2=9, T3=1 first 10) |
| pressure_contract.grade | pass |
| frontier_diagnostic | mixed_or_unproven |

### 5. Readiness checks at max-tasks 10, 20, 30

| Check | Decision | Degeneration | T2 | T3 |
|-------|----------|--------------|----|-----|
| max_tasks=10 | PASS | mixed | 9 | 1 |
| max_tasks=20 | PASS | mixed | 11 | 9 |
| max_tasks=30 | PASS | mixed | 17 | 13 |

No pure-tier degeneration at any stage boundary. All three checks pass.

## Artifacts

| File | Description |
|------|-------------|
| `mainline_3x30_staged_task_order_20260622.json` | 30-task order with 3 stages, effort/criticality per task |
| `mainline_3x30_criticality_value_matrix_20260622.json` | Bootstrap value matrix (criticality_value profile) |
| `mainline_3x30_stage_prefix10_kv50_budget_plan_20260622.json` | KV50 stage-prefix budget plan |

## Residual risks

- No calibration evidence (bootstrap_estimate only) — projection_confidence=unvalidated
- KV50 is a diagnostic sensitivity catalog; default catalog plan needed for primary evidence
- frontier_diagnostic remains mixed_or_unproven — needs trusted ModelFit from calibration run
- sphinx-7975 and sphinx-8801 have higher effort (41.4, 54.9) — monitor for budget pressure skew in stage 2
- Stage 2 has sphinx-7686 at effort=88.8 (extreme outlier) — may dominate stage 2 spend
- T3 progress_prior values (0.72/0.72/0.70) are heuristic — sensitivity-check before paper-scale runs

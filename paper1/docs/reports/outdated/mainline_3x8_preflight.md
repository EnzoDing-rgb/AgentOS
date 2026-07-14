# Mainline 3x8 Mechanism Preflight

Date: 2026-06-09

## Objective

Prepare the next paid mainline mechanism diagnostic without mixing in continual
learning. The experiment target is BudgetFlow Mechanism value under the same
hard budget, not Learn Policy value.

## Design Decision

The next run should compare only the three mainline roles:

- `bare_strong_model`
- `enterprise_router_baseline`
- `budgetflow_same_router`

Routing/Escalation Memory and Cost Memory should be disabled for this run with
`--disable-policy-memory --no-auto-budget-learn`. Continual learning is a
separate follow-up claim and should not be mixed into this mechanism-isolation
run.

## Task Set

The 8 tasks are:

- `sympy__sympy-13480`
- `sympy__sympy-14774`
- `sympy__sympy-16988`
- `sympy__sympy-20212`
- `sympy__sympy-12419`
- `sympy__sympy-19007`
- `sympy__sympy-20154`
- `sympy__sympy-20639`

The first four preserve the calibrated anchor set. The four added tasks are
zero-occurrence SymPy SWE-bench Lite tasks in current run JSONL history, with
complete `test_patch` and `FAIL_TO_PASS` metadata. This expands anti-overfit
coverage without adding a cross-repo harness variable.

## Artifacts

- `docs/reports/mainline_3x8_manual_value_matrix.json`
- `docs/reports/mainline_3x8_frozen_router_plan.json`

The value matrix is `pre_registered_manual`, primary T1 evidence, and includes
`equal`, `manual_value`, and `bootstrap_difficulty` profiles. Manual values are
fixed before the paid run.

The frozen plan has 8 entries and `hard_cap_usd=1.8`; base caps sum to 1.8.

## Observability Fix

Compact audit now reports both:

- `Yield/total$`: resolved value divided by all model spend, including aborts.
- `Yield/score$`: resolved value divided by scoreable spend only.

The paper-facing diagnostic should use `Yield/total$`. Scoreable-only remains a
diagnostic for separating protocol abort cost.

## Verification

Focused tests:

```bash
PYTHONPATH=paper1/src pytest -q \
  paper1/tests/test_run_observability_audit.py::test_compact_audit_reports_value_metrics \
  paper1/tests/test_compare_readiness.py \
  paper1/tests/test_frozen_router.py \
  paper1/tests/test_value_efficiency.py
```

Result: `40 passed`.

No-paid readiness:

```bash
PYTHONPATH=paper1/src:external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare \
  --preset 3x3 \
  --limit 8 \
  --ids sympy__sympy-13480,sympy__sympy-14774,sympy__sympy-16988,sympy__sympy-20212,sympy__sympy-12419,sympy__sympy-19007,sympy__sympy-20154,sympy__sympy-20639 \
  --strategies bare_strong_model,enterprise_router_baseline,budgetflow_same_router \
  --jobs 3 \
  --budget 1.8 \
  --frozen-plan paper1/docs/reports/mainline_3x8_frozen_router_plan.json \
  --value-profile manual_value \
  --value-matrix paper1/docs/reports/mainline_3x8_manual_value_matrix.json \
  --value-source-kind pre_registered_manual \
  --disable-policy-memory \
  --no-auto-budget-learn \
  --paid-readiness-only \
  --runtime-root /tmp/budgetflow-runtime \
  --out-stem mainline_3x8_plus_mechanism
```

Result: PASS. Readiness confirmed 8 tasks, 3 strategies, policy jobs 3,
primary T1 manual value source, frozen plan 8 entries, planned cap 1.8000, hard
cap 1.8000, and dynamic caps off.

## Residual Risks

This is still a paid diagnostic, not paper-scale evidence. The four added tasks
are intentionally unseen by current run history, so failures may expose model
capability, harness/parser issues, or task difficulty rather than only mechanism
quality. The post-run report must separate verifier true-fails from
abort/protocol failures and must interpret `Yield/total$` before mechanism
storytelling.

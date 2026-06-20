# DeepSeek V4 Pro T2 Catalog Switch

Date: 2026-06-20

## Objective

Replace T2 from GLM-5.1 on DashScope to DeepSeek V4 Pro without changing
BudgetFlow runtime or routing semantics.

## Root Cause

The previous paid attempt was blocked before task execution by the T2 provider
account, not by SWE task execution. The default tier catalog still mapped
`tier2` to `openai/glm-5.1` with `DASHSCOPE_API_KEY`, so the T2 baseline and
any policy that needed T2 depended on the DashScope account state.

## Changes

- Updated T2 in all model tier catalogs:
  - `paper1/docs/config/model_tiers.default.json`
  - `paper1/docs/config/model_tiers.t3x2.json`
  - `paper1/docs/config/model_tiers.t3x3.json`
- T2 now uses:
  - model: `openai/deepseek-v4-pro`
  - API base: `https://api.deepseek.com/v1`
  - key env: `DEEPSEEK_API_KEY`
  - protocol: `tool_call`
- Preserved normalized T2 cost semantics. The `cost_per_*` values are
  BudgetFlow experimental units, not public provider billing rates.
- Added `catalog_semantic_revision` so provider-only swaps can keep using
  historical normalized-tier calibration rows. GLM-5.1, DeepSeek V4 Pro, and
  future Qwen-style T2 replacements are equivalent to BudgetFlow when
  normalized cost/progress/turn semantics are unchanged.
- Added a catalog regression test so default T2 cannot silently drift back to
  GLM/DashScope.
- Regenerated `mainline_4x25_tasklevel_fix_budget_plan_20260620.json` against
  the new catalog hash.

## Validation

Commands run:

```bash
PYTHONPATH=paper1/src pytest -q paper1/tests/test_model_tiers.py paper1/tests/test_trace_fields.py
PYTHONPATH=paper1/src pytest -q paper1/tests/test_budget_binding.py paper1/tests/test_compare_readiness.py paper1/tests/test_model_tiers.py
PYTHONPATH=paper1/src pytest -q paper1/tests/test_budget_binding.py paper1/tests/test_compare_readiness.py paper1/tests/test_task_level_expected_cost.py paper1/tests/test_model_fit_estimator.py paper1/tests/test_compare_setup.py paper1/tests/test_compare_record_schema.py paper1/tests/test_run_guards.py paper1/tests/test_model_tiers.py paper1/tests/test_trace_fields.py
PYTHONPATH=paper1/src python - <<'PY'
from budgetflow.model_tiers import load_env_file
from budgetflow.provider_signature import check_backend_signature
load_env_file()
print(check_backend_signature("tier2"))
PY
PYTHONPATH=paper1/src python paper1/src/budgetflow/run_mini_swe_compare.py \
  --ids "$TASK_IDS" \
  --strategies bare_t2_baseline,bare_t3_baseline,enterprise_router_baseline,budgetflow_task_level \
  --jobs 4 \
  --budget-plan paper1/docs/reports/mainline_4x25_tasklevel_fix_budget_plan_20260620.json \
  --frozen-plan paper1/docs/reports/mainline_4x25_glm51_frozen_router_plan_20260618.json \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix paper1/docs/reports/mainline_4x25_glm51_manual_value_matrix_20260618.json \
  --paid-readiness-only
```

Results:

- `test_model_tiers.py` plus `test_trace_fields.py`: `17 passed, 5 skipped`
- final no-paid regression set: `217 passed`
- DeepSeek T2 provider signature: `ok=True`, model `openai/deepseek-v4-pro`
- paid-readiness-only: `PASS`

## Current 4x25 Gate

The 4x25 budget plan was regenerated after the catalog switch. Because the
swap is provider-only at the BudgetFlow tier level, historical rows from
`2026-06-17-glm51-t2-t3x5` remain compatible through
`catalog_semantic_revision=t2-normalized-v1-t3x5`.

This keeps the routing/runtime interpretation unchanged: replacing the physical
T2 provider does not by itself change Budget Compiler or Runtime ModelFit.

Current projection after the switch:

- hard cap: `$21.5059`
- ModelFit evidence: `tier2=0.81`, `tier3=0.85`
- task-level projection: `tier2=8`, `tier3=17`
- pressure contract: `pass`

## Residual Risk

DeepSeek V4 Pro is callable and tool-call compatible in the provider preflight,
but it has not yet been observed in full SWE task rows under this provider.
That is a provider/runtime risk to monitor, not a reason to discard normalized
T2 calibration when the tier semantics are unchanged.

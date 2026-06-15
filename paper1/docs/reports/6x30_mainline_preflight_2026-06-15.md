# 6x30 Mainline Pre-Flight Report — June 15, 2026

## Verdict

**GO for staged paid run after paid-readiness-only passes.** Run as 6x10, inspect artifacts and budget waterline, then resume the same run identity with 20 and finally 30 cumulative task ids. The later stages continue from the same checkpoint and JSONL ledger.

## Fixed Since Worker Report

- Pending SymPy gold gate completed: 5/5 PASS.
- 6x30 manifest now has 30/30 harness-admissible tasks.
- Missing artifacts generated:
  - `docs/reports/mainline_6x30_frozen_router_plan.json`
  - `docs/reports/mainline_6x30_budget_plan.json`
- `manual_value` source cleaned: outcome-free verification-breadth formula from f2p/p2p metadata only. T3 solvability probe labels are not used for value.
- Pip marker cache poison fixed in code: marker now lives inside the current worktree as `.budgetflow_pip_ok`.
- Checkpoint resume now upgrades `total_runs` when the staged run expands from 6x10 to 6x20 to 6x30.
- Resume completion is keyed by unique scoreable policy-task pairs (`pass`/`true_fail`), not raw JSONL row count. Duplicate rows and abort rows do not make a run complete.

## Task Set

Source: 10 Phase-6 gate tasks + 15 expanded candidate gate tasks + 5 pending SymPy tasks now gold-gated.

| Repo | Count | Notes |
|---|---:|---|
| sympy | 8 | all gold-gated |
| django | 7 | harness-admissible |
| sphinx | 5 | harness-admissible |
| seaborn | 4 | harness-admissible |
| pylint | 3 | harness-admissible |
| flask | 2 | harness-admissible |
| matplotlib | 1 | harness-admissible; heavier build/runtime |
| **Total** | **30** | 30/30 gold-harness PASS |

## T3 Solvability Probe Interpretation

Paid T3 probe covered 15 harness-admissible tasks:

| Class | Count | Tasks |
|---|---:|---|
| Solved | 7 | seaborn-3407, sphinx-8595, django-11179, django-12908, django-13964, django-15814, django-15851 |
| Harness-verified model fail | 5 | flask-4045, flask-4992, seaborn-3190, sphinx-7738, matplotlib-25433 |
| Infra/dependency noise | 1 | pylint-5859 |
| Patch/protocol fail | 2 | sphinx-8282, django-11049 |

This diagnostic is deliberately kept out of the mainline manifest and value matrix. It is useful for postmortem classification and model-capability interpretation, but not for selecting task value, frozen caps, or budget allocation.

## Budget Plan

| Parameter | Value |
|---|---:|
| Strategy set | `docs/config/paper_mainline_strategies.v1.json` |
| Policies | 6 |
| Budget mode | `frozen_plan_cap_sum` |
| Model catalog | `docs/config/model_tiers.t3x3.json` |
| Hard cap per policy | `$2.9990` |
| Value matrix | `docs/reports/mainline_6x30_manual_value_matrix.json` |
| Frozen plan | `docs/reports/mainline_6x30_frozen_router_plan.json` |
| Budget plan | `docs/reports/mainline_6x30_budget_plan.json` |

Cap rule is code-generated from pre-run metadata:

`base_cap = round(clamp(0.06, 0.13, 0.04 + 0.00030 * bootstrap_effort), 4)`

`target_utilization` is intentionally not used because the 5x20 projection audit had MAPE=53.5%.

## Stage 1: Paid-Readiness Only For First 10

Run this first; it performs local setup/readiness validation without executing the main experiment. Provider signature checks run when the paid command starts, so a formal paid launch can still stop before spending if provider access fails.

```bash
cd /root/.dev/AgentOS/paper1
PYTHONPATH=src python -m budgetflow.run_mini_swe_compare \
  --ids "$(python -c "import json; print(','.join(json.load(open('docs/reports/6x30_mainline_manifest.json'))['candidates'][:10]))")" \
  --strategy-set docs/config/paper_mainline_strategies.v1.json \
  --budget-mode frozen_plan_cap_sum \
  --frozen-plan docs/reports/mainline_6x30_frozen_router_plan.json \
  --budget-plan docs/reports/mainline_6x30_budget_plan.json \
  --model-catalog docs/config/model_tiers.t3x3.json \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix docs/reports/mainline_6x30_manual_value_matrix.json \
  --run-series mainline_6x30_v1 \
  --runtime-root /tmp/budgetflow-runtime \
  --step-limit 150 \
  --jobs 6 \
  --paid-readiness-only
```

## Stage 2: 6x10 Paid Run

```bash
cd /root/.dev/AgentOS/paper1
PYTHONPATH=src python -m budgetflow.run_mini_swe_compare \
  --ids "$(python -c "import json; print(','.join(json.load(open('docs/reports/6x30_mainline_manifest.json'))['candidates'][:10]))")" \
  --strategy-set docs/config/paper_mainline_strategies.v1.json \
  --budget-mode frozen_plan_cap_sum \
  --frozen-plan docs/reports/mainline_6x30_frozen_router_plan.json \
  --budget-plan docs/reports/mainline_6x30_budget_plan.json \
  --model-catalog docs/config/model_tiers.t3x3.json \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix docs/reports/mainline_6x30_manual_value_matrix.json \
  --run-series mainline_6x30_v1 \
  --runtime-root /tmp/budgetflow-runtime \
  --step-limit 150 \
  --jobs 6
```

After 6x10 finishes, inspect checker/summary/JSONL before continuing. Do not draw paper conclusions from the 6x10 checkpoint alone.

## Stage 3: Resume To 6x20

Use the first 20 cumulative ids with `--resume`; completed 6x10 pairs are skipped, and the same output stem/checkpoint carries forward.

```bash
cd /root/.dev/AgentOS/paper1
PYTHONPATH=src python -m budgetflow.run_mini_swe_compare \
  --ids "$(python -c "import json; print(','.join(json.load(open('docs/reports/6x30_mainline_manifest.json'))['candidates'][:20]))")" \
  --strategy-set docs/config/paper_mainline_strategies.v1.json \
  --budget-mode frozen_plan_cap_sum \
  --frozen-plan docs/reports/mainline_6x30_frozen_router_plan.json \
  --budget-plan docs/reports/mainline_6x30_budget_plan.json \
  --model-catalog docs/config/model_tiers.t3x3.json \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix docs/reports/mainline_6x30_manual_value_matrix.json \
  --run-series mainline_6x30_v1 \
  --runtime-root /tmp/budgetflow-runtime \
  --step-limit 150 \
  --jobs 6 \
  --resume
```

After 6x20 finishes, inspect checker/summary/JSONL and budget utilization before continuing.

## Stage 4: Resume To 6x30

Use all 30 cumulative ids with `--resume`; completed 6x20 pairs are skipped, and the same output stem/checkpoint carries forward.

```bash
cd /root/.dev/AgentOS/paper1
PYTHONPATH=src python -m budgetflow.run_mini_swe_compare \
  --ids "$(python -c "import json; print(','.join(json.load(open('docs/reports/6x30_mainline_manifest.json'))['candidates']))")" \
  --strategy-set docs/config/paper_mainline_strategies.v1.json \
  --budget-mode frozen_plan_cap_sum \
  --frozen-plan docs/reports/mainline_6x30_frozen_router_plan.json \
  --budget-plan docs/reports/mainline_6x30_budget_plan.json \
  --model-catalog docs/config/model_tiers.t3x3.json \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix docs/reports/mainline_6x30_manual_value_matrix.json \
  --run-series mainline_6x30_v1 \
  --runtime-root /tmp/budgetflow-runtime \
  --step-limit 150 \
  --jobs 6 \
  --resume
```

## Stop Conditions

1. Provider auth/model access failure: stop immediately.
2. More than 3 consecutive provider/model crashes: pause and inspect provider health.
3. Any strategy shows repeated harness adapter errors on the same repo: pause and classify as infra, not model evidence.
4. Sibling stems detected for `mainline_6x30_v1`: do not merge by hand during the run; use explicit repair only after audit.
5. Stage 2 6x10 shows budget utilization still far below the intended scarcity regime: stop before +10 and audit cost/catalog/governor behavior.

## Residual Risks

- `pylint-dev__pylint-5859` has dependency/setup noise in the T3 probe; keep it visible in postmortem classification.
- Matplotlib is harness-admissible but heavier; expect longer local setup.
- 15/30 tasks have no T3 solvability probe; that is acceptable for the mainline, but classify failures carefully after the run.
- `t3x3` is a normalized diagnostic catalog, not the real billing catalog. Paper tables should report both diagnostic scarcity results and cost-sensitivity/recost analysis.

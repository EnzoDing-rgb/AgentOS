# 6x30 Mainline Pre-Flight Report — June 15, 2026

## Verdict

**GO for staged paid run after paid-readiness-only passes.** Run as 6x20 first, inspect artifacts, then resume the same run identity with all 30 task ids so the final +10 continues from the same checkpoint and ledger.

## Fixed Since Worker Report

- Pending SymPy gold gate completed: 5/5 PASS.
- 6x30 manifest now has 30/30 harness-admissible tasks.
- Missing artifacts generated:
  - `docs/reports/mainline_6x30_frozen_router_plan.json`
  - `docs/reports/mainline_6x30_budget_plan.json`
- `manual_value` source cleaned: outcome-free verification-breadth formula from f2p/p2p metadata only. T3 solvability probe labels are not used for value.
- Pip marker cache poison fixed in code: marker now lives inside the current worktree as `.budgetflow_pip_ok`.
- Checkpoint resume now upgrades `total_runs` when 6x20 expands to 6x30.

## Task Set

Source: 10 Phase-6 gate tasks + 15 expanded candidate gate tasks + 5 pending SymPy tasks now gold-gated.

| Repo | Count | Notes |
|---|---:|---|
| sympy | 8 | all gold-gated |
| django | 7 | 5/6 solved in T3 probe among new Django probe tasks |
| sphinx | 5 | mixed T3 solvability, harness-admissible |
| seaborn | 4 | new repo, 1/2 solved in T3 probe |
| pylint | 3 | harness-admissible; one probed task has dependency/setup noise |
| flask | 2 | harness-admissible; both T3 probe failures |
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

This is not alarming by itself. The probe suggests the new pool has real difficulty and repo variance. It also shows one task (`pylint-dev__pylint-5859`) should be watched as dependency/adapter noise, not treated as clean model-capability evidence.

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

## Stage 1: Paid-Readiness Only

Run this first; it performs local setup/readiness validation without executing the main experiment. Provider signature checks run when the paid command starts, so a formal paid launch can still stop before spending if provider access fails.

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
  --paid-readiness-only
```

## Stage 2: 6x20 Paid Run

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
  --jobs 6
```

After 6x20 finishes, inspect checker/summary/JSONL before continuing. Do not draw paper conclusions from the 6x20 checkpoint alone.

## Stage 3: +10 Resume to 6x30

Use all 30 ids with `--resume`; completed 6x20 pairs are skipped, and the same output stem/checkpoint carries forward.

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
5. Stage 1 6x20 shows budget utilization still far below the intended scarcity regime: stop before +10 and audit cost/catalog/governor behavior.

## Residual Risks

- `pylint-dev__pylint-5859` has dependency/setup noise in the T3 probe; keep it visible in postmortem classification.
- Matplotlib is harness-admissible but heavier; expect longer local setup.
- 15/30 tasks have no T3 solvability probe; that is acceptable for the mainline, but classify failures carefully after the run.
- `t3x3` is a normalized diagnostic catalog, not the real billing catalog. Paper tables should report both diagnostic scarcity results and cost-sensitivity/recost analysis.

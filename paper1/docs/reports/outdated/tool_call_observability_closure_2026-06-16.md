# Tool-Call and Observability Closure

Date: 2026-06-16

## Objective

Fix the paid-run infra failure exposed by the two 6x10 runs before any further paid experiment:

- active action protocol must be one canonical path, not text regex plus fallbacks;
- failure rows must explain whether the owner is protocol, harness, budget, model, or task;
- current JSONL must carry structured trust/scoring fields instead of requiring post-hoc parsing of `detail`.

## Evidence From Two 6x10 Runs

Audited:

- `data/runs/mainline_6x30_v1-0.jsonl`
- `data/runs/mainline_6x30_shared_budget_t3x3_20260615-0.jsonl`

Repeated infra patterns:

- Protocol/parser aborts dominated: 20 and 21 rows with `abort_owner=protocol`, `format_error_text_action`, and `protocol=text_regex`.
- `NameError` rows were model/patch quality failures, not provider or harness failures.
- `HarnessFailed` rows were scoreable true failures when `test_patch=ok`, `fail_before=fail`, and the model patch was evaluated.
- Several `untrusted_harness_evidence` aborts were taxonomy errors: `model_patch=... error` means patch-apply/model failure, not harness infra.
- Budget exhaustion is scoreable when the shared-cap contract is valid; budget contract/cap asymmetry is infra.

## Code Changes

- Removed active `text_regex` action parsing from `budgetflow.adapter`.
- All model tier catalogs now require `tool_call`; active runner calls LiteLLM with `tools=[BASH_TOOL]` and parses `message.tool_calls`.
- Catalog content hash is now part of the budget plan and resume/readiness contract.
- Removed legacy regex fallback from localization diagnostics; current diagnostics use `touched_file_paths` only.
- Added structured harness stage status fields to `HarnessEvidence`.
- Persist current JSONL fields: `harness_trust`, `harness_issues`, `harness_owner`, `harness_severity`.
- Tightened current JSONL schema so those trust fields are required.
- Reclassified model patch apply failures as scoreable model true failures (`repair_fail` / `patch_apply_model_fail`) instead of harness aborts.

## Verification

Commands run:

```bash
PYTHONPATH=paper1/src:external/mini-swe-agent/src python -m pytest paper1/tests/ -q
PYTHONPATH=paper1/src:external/mini-swe-agent/src python -m py_compile $(find paper1/src paper1/tests -name '*.py' -not -path '*/__pycache__/*')
git diff --check
```

Result: `545 passed`; py_compile clean; diff check clean.

No-paid readiness:

```bash
PYTHONPATH=src:../external/mini-swe-agent/src python -m budgetflow.run_mini_swe_compare \
  --ids "<first 10 ids from docs/reports/6x30_mainline_manifest.json>" \
  --strategy-set docs/config/paper_mainline_strategies.v1.json \
  --frozen-plan docs/reports/mainline_6x30_frozen_router_plan.json \
  --budget-plan docs/reports/mainline_6x30_budget_plan.json \
  --model-catalog docs/config/model_tiers.t3x3.json \
  --diagnostic-catalog \
  --value-profile manual_value \
  --value-source-kind pre_registered_manual \
  --value-matrix docs/reports/mainline_6x30_manual_value_matrix.json \
  --run-series mainline_6x30_toolcall_canary_20260616 \
  --runtime-root /tmp/budgetflow-runtime \
  --worktree-root /tmp/budgetflow-runtime/worktrees \
  --step-limit 150 \
  --jobs 6 \
  --paid-readiness-only
```

Result: PASS. Warning remains: budget projection confidence is unvalidated, so do not claim the 90% utilization target is empirically calibrated.

## Next Step

Run a small paid tool-call canary before another 6x10:

- 2 tasks x 2 strategies is enough to validate provider tool-call behavior.
- Stop if protocol-owner abort rate is above 5%, protocol retry rate is above 10%, provider returns tool-call unsupported errors, or current JSONL misses required trust fields.
- If canary is clean, rerun 6x10 under `mainline_6x30_toolcall_canary_20260616`; do not resume either text-regex 6x10 series.

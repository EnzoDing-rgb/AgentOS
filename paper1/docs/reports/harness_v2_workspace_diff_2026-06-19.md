# Harness v2 workspace-diff slice

## Objective

Reduce evaluation-harness noise in the no-Docker SWE task runner.

The old runner treated the agent submission text as the only scoreable patch.
That made real workspace edits invisible when the agent edited files but did not
complete the custom submit protocol. The new path scores the runner-side
workspace diff first and keeps `submitted.patch` as auxiliary protocol evidence.

## Files changed

- `src/budgetflow/adapter/runner.py`
  - Captures a git tree snapshot after checkout and local compat setup.
  - Collects a clean `workspace.patch` after the agent exits.
  - Evaluates `workspace_diff` first, falling back to explicit submission only
    when no workspace diff exists.
- `src/budgetflow/run_trace.py`
  - Computes changed files and patch digests relative to the same baseline tree,
    so compat edits do not look like agent progress.
- `src/budgetflow/adapters/swebench_progress.py`
  - Emits `workspace_patch` in run records.
- `src/budgetflow/observability.py`
  - Treats `workspace_diff` as a known patch source.
- `src/budgetflow/run_observability/schema.py`
  - Allows `patch_source=workspace_diff`.
- `src/budgetflow/export_official_predictions.py`
  - Exports `workspace_patch` before `submitted_patch`.
- Tests added/updated:
  - `tests/test_workspace_patch_extraction.py`
  - `tests/test_export_official_predictions.py`
  - `tests/test_compare_record_schema.py`
  - `tests/test_swebench_adapters.py`

## Interface decisions

- `patch_source=workspace_diff` means the scoreable patch came from the actual
  repository worktree after the agent run.
- `workspace_patch` points to `workspace.patch`, the scoreable artifact.
- `submitted_patch` still points to `submitted.patch` when the agent used the
  submit protocol. It is no longer required for a row to be scoreable.
- Baseline isolation uses a temporary git tree object, not a git commit. It does
  not move `HEAD`, and it still works if the agent creates its own commit.
- Auxiliary files such as `patch.txt`, `submitted.patch`, `workspace.patch`,
  `.budgetflow_*.patch`, caches, and bytecode are excluded from the scoreable
  workspace diff.

## Verification

No-paid gates:

```bash
PYTHONPATH=paper1/src pytest -q paper1/tests/test_export_official_predictions.py \
  paper1/tests/test_workspace_patch_extraction.py \
  paper1/tests/test_swebench_adapters.py \
  paper1/tests/test_compare_record_schema.py \
  paper1/tests/test_run_observability_audit.py \
  paper1/tests/test_failure_classification.py
# 132 passed

PYTHONPATH=paper1/src pytest -q paper1/tests
# 680 passed

git diff --check
PYTHONPATH=paper1/src python -m py_compile $(rg --files paper1/src/budgetflow paper1/tests | rg '\.py$')
```

Real-agent validation:

```bash
cd /root/.dev/AgentOS/paper1
PYTHONPATH=src:../external/mini-swe-agent/src \
BUDGETFLOW_RUNTIME_ROOT=/tmp/budgetflow-runtime \
python -u -m budgetflow.run_mini_swe_compare \
  --ids sympy__sympy-14774,sympy__sympy-16988,django__django-10924 \
  --strategies budgetflow_task_level \
  --jobs 1 \
  --per-task-cap 0.50 \
  --value-profile equal \
  --step-limit 80 \
  --trace-turns \
  --trace-max-turns 80 \
  --runtime-root /tmp/budgetflow-runtime \
  --out-stem harness_v2_real_agent_3x1
```

Result:

- JSONL: `data/runs/harness_v2_real_agent_3x1.jsonl`
- Rows: 3
- Pass: 3
- Total cost: 0.9023729 governor units
- `patch_source`: 3/3 `workspace_diff`
- `workspace_patch`: 3/3 present
- `harness_trust`: 3/3 `trusted`
- Harness issues: none
- Submitted patch projection under the old path: only 1/3 rows had
  `submitted_patch`; 2/3 trusted passes would have been missed as scoreable
  artifacts by the old submitted-patch-only path.

The checker reported 0 errors and 1 cost-accounting summary warning:

```text
COST_ACCOUNTING budgetflow_task_level: raw_paid_cost=$0.9024 dedup_scored_cost=$0.9024 duplicate_retry_overhead=$0.0000 rows=3
```

Official prediction export was also checked:

```bash
PYTHONPATH=src python -m budgetflow.export_official_predictions \
  data/runs/harness_v2_real_agent_3x1.jsonl \
  --out /tmp/harness_v2_real_agent_3x1.predictions.jsonl \
  --model-name budgetflow-harness-v2
```

It exported 3 predictions and all 3 `model_patch` fields came from
`workspace.patch`.

## Residual risks

- This is a harness validation slice, not paper-level evidence. The real-agent
  run used 3 tasks and one strategy.
- The local no-Docker harness still depends on repo-specific adapters and host
  dependencies. This slice reduces patch extraction noise; it does not prove
  every task environment is correct.
- `workspace_diff` can score edits even when the agent never follows the submit
  protocol. That is intentional for the paper claim, but protocol adherence
  should remain an auxiliary diagnostic.

## Next recommended slice

Run a small cross-policy validation only after this commit is pushed. The next
question should be mechanism behavior under the same harness path, not another
patch-extraction refactor.

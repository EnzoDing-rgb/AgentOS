# Forensic Attribution + 3x3 Diagnostic Plan

## Goal

Before scaling BudgetFlow experiments, add a compact forensic attribution layer and run a small 3x3 diagnostic experiment that can distinguish policy/runtime problems from model weakness, task difficulty, patch extraction issues, harness artifacts, and weak failure taxonomy.

This is not a scale-up plan. It is a diagnostic plan.

## Constraints

- Use exactly three model tiers:
  - T1: Coder Flash
  - T2: Coder Plus
  - T3: GPT-5.3 Codex
- Remove GPT-5.5 from the normal code path for now.
- Do not add more raw trace noise.
- Add minimal, high-signal forensic summaries to each run record.
- Use a 3 policies x 3 tasks experiment, not 5 tasks.

## Phase 1: Forensic Attribution Layer

### Problem

Current `failure_class` is too coarse for scientific diagnosis. In particular, `repair_fail` is a residual bucket, not a root cause, and budget-related runtime errors can be mislabeled as infra failures.

Example failure pattern already observed:

- `exit_status=BudgetFlowBudgetError`
- `exit_reason=budget_exhausted`
- `patch_extracted=true`
- `patch_source=worktree`
- `agent_gold_edited=true`
- `agent_submitted=false`
- local harness detail includes `model_patch=ok; fail_after=fail`
- current class can become `infra_fail`

This is misleading. It should be surfaced as budget exhaustion after repair progress, with patch/protocol details preserved.

### Implementation target

Add a compact `forensic_summary` object to each JSONL run record, computed from existing record fields.

Likely files:

- `paper1/src/budgetflow/failure_classification.py`
- `paper1/src/budgetflow/run_mini_swe_compare.py`
- `paper1/tests/test_failure_classification.py`
- possibly `paper1/scripts/build_paper_result_table.py`

### Proposed `forensic_summary` schema

```json
{
  "primary_axis": "budget | protocol | localization | repair_quality | harness | model_behavior | task_difficulty | infra | pass",
  "failure_chain": [
    "budget_exhausted",
    "patch_extracted",
    "gold_file_edited",
    "harness_fail_after_failed"
  ],
  "patch": {
    "extracted": true,
    "source": "submission | worktree | none | unknown",
    "gold_edited": true,
    "submitted": false,
    "attempted_submit": false
  },
  "harness": {
    "test_patch": "ok | fail | unknown",
    "fail_before": "ok | fail | unknown",
    "model_patch": "ok | fail | unknown",
    "fail_after": "ok | fail | unknown",
    "pass_to_pass": "ok | fail | unknown"
  },
  "budget": {
    "exhausted": true,
    "exhausted_after_patch": true,
    "spent": 0.0,
    "available": 0.0
  },
  "policy": {
    "backend_mix": ["..."],
    "rescue_seen": false,
    "stop_loss_seen": false
  },
  "confidence": "high | medium | low",
  "missing_evidence": []
}
```

Keep it compact. It should be readable from the JSONL/table without opening raw traces.

### Attribution rules

Recommended initial deterministic rules:

1. If `harness_resolved=true`, primary axis is `pass`.
2. If `exit_reason` or `exit_status` indicates budget/cap exhaustion, primary axis is `budget`.
   - If a patch exists or a gold file was edited, add `budget_exhausted_after_patch`.
3. If no patch was extracted:
   - If format errors or no tool calls are visible, primary axis is `protocol`.
   - If stagnation/no-progress is visible, primary axis is `model_behavior`.
   - Otherwise primary axis is `protocol` with lower confidence.
4. If patch exists but gold file was not edited, primary axis is `localization`.
5. If patch applies but fail-after still fails, primary axis is `repair_quality`.
6. If test patch or harness setup fails, primary axis is `harness`.
7. Only use `infra` for real API/auth/rate-limit/runtime infrastructure failures after budget/protocol checks.

### Failure classification fix

Update `classify_failure()` so budget/cap conditions are checked before generic `"error" in status.lower()` infra matching.

Add regression tests for at least:

```python
{
    "harness_resolved": False,
    "patch_extracted": True,
    "agent_gold_edited": True,
    "exit_status": "BudgetFlowBudgetError",
    "exit_reason": "budget_exhausted",
}
```

Expected coarse class: `budget_fail`, not `infra_fail`.

## Phase 2: Remove GPT-5.5 and Normalize Model Tiers

### Required model tiers

- T1: Coder Flash
- T2: Coder Plus
- T3: GPT-5.3 Codex

GPT-5.5 should be removed from active code paths, not merely hidden in docs.

### Likely files to inspect/change

- `paper1/src/budgetflow/adapter/backends.py`
- `paper1/src/budgetflow/adapter/strategies.py`
- `paper1/src/budgetflow/adaptive_routing.py`
- `paper1/src/budgetflow/compare_checkpoint.py`
- launcher scripts under `paper1/scripts/`
- tests under `paper1/tests/`
- result table/report scripts that special-case `all_gpt55`
- docs that describe current intended model tiers

### Expected code outcome

- No active `all_gpt55` strategy.
- No GPT-5.5 backend in the default or explicit experiment backend pool.
- `all_gpt53` remains only if needed as GPT-5.3 Codex ceiling strategy.
- Tier language should treat GPT-5.3 Codex as T3, not T4.
- Historical artifact files may remain, but should not drive current experiment configuration.

## Phase 3: 3x3 Diagnostic Experiment

### Policies

Use exactly three policies:

1. `budget_only_tight`
   - Baseline budget pressure without full BudgetFlow adaptive behavior.
2. `budgetflow_full_tight`
   - Main BudgetFlow policy under tight budget.
3. `budgetflow_auto_v2_tight`
   - Current auto/rescue/stop-loss variant.

### Tasks

Use exactly three tasks:

1. `sympy__sympy-13480`
   - Easy/control task.
   - Purpose: verify harness/protocol/model path can still pass.
2. `sympy__sympy-20212`
   - Mid-difficulty task.
   - Purpose: distinguish routing quality from trivial pass/fail behavior.
3. `sympy__sympy-16988`
   - Hard sentinel task.
   - Purpose: stress budget exhaustion, rescue behavior, and patch quality.

### Matrix

| Task | budget_only_tight | budgetflow_full_tight | budgetflow_auto_v2_tight |
|---|---:|---:|---:|
| `sympy__sympy-13480` | run | run | run |
| `sympy__sympy-20212` | run | run | run |
| `sympy__sympy-16988` | run | run | run |

Total: 9 runs.

### What to compare

For each cell, compare:

- pass/fail
- `failure_class`
- `forensic_summary.primary_axis`
- patch extraction status
- patch source: submission vs worktree
- gold file edited or not
- harness stage breakdown
- budget exhausted before or after repair progress
- backend picks / tier mix
- rescue/stop-loss evidence
- total cost and turns

### Decision logic after 3x3

- If all policies fail on the hard task but GPT-5.3 Codex ceiling previously passes similar tasks, suspect BudgetFlow routing/budget policy.
- If all policies fail with `protocol` or `no_patch_extracted`, fix patch extraction/protocol before more experiments.
- If failures cluster at `localization`, inspect early-stage tier allocation and escalation timing.
- If failures cluster at `repair_quality` after successful patch extraction and gold edits, compare backend mix and whether GPT-5.3 Codex was reached soon enough.
- If failures are mostly `budget` after repair progress, tune caps/rescue/stop-loss rather than blaming model capability.
- If easy/control task fails, stop and fix harness/protocol before interpreting BudgetFlow.

## Phase 4: Paper Table Update

After `forensic_summary` exists, update result table generation so `next_action` is evidence-backed instead of mechanical.

Current bad pattern:

- `repair_fail` -> `inspect repair failures`

Desired examples:

- `budget` + `exhausted_after_patch=true` -> `tune cap/rescue after repair progress`
- `protocol` + no patch -> `fix submission/protocol before scaling`
- `localization` -> `escalate earlier in localization`
- `repair_quality` + patch applies but fail-after fails -> `compare high-tier repair quality on same task`
- `harness` -> `verify local harness before conclusions`

## Execution Order

1. Implement and test `forensic_summary` generation.
2. Fix budget-vs-infra failure classification and add regression tests.
3. Remove GPT-5.5 active code paths and normalize tiers to T1/T2/T3.
4. Update table/report generation to consume forensic summaries where available.
5. Run unit tests.
6. Run the 3x3 diagnostic experiment.
7. Regenerate result table and inspect forensic summaries before any scale-up decision.

## Non-goals

- Do not run a 5-task matrix now.
- Do not add GPT-5.5 back unless explicitly requested later.
- Do not treat the local harness as official SWE-bench leaderboard evidence.
- Do not add large raw traces as the main fix.
- Do not claim BudgetFlow is good or bad until the 3x3 forensic evidence is available.

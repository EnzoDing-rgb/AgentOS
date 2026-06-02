# BudgetFlow Handoff

Current priority: **fix and deepen local harness before any new experiment**.

Do not run larger matrices until the harness can prove PASS_TO_PASS is clean on the base environment. Current pass/fail tables may be polluted by local environment incompatibility.

## Current Facts

- Date: 2026-06-02.
- Active tiers:
  - T1 = `qwen3-coder-flash`
  - T2 = `qwen3-coder-plus`
  - T3 = `GPT-5.4` / `openai/gpt-5.4`
- GPT-5.3 Codex is historical only. It is not exposed by the provider.
- GPT-5.4 command parsing was fixed in commit `105edc6`.
- `all_pro` now means strongest tier/T3.
- `budget_only` now starts from the cheapest available tier.
- Trace observability is now good enough for root-cause debugging.
- Latest GPT-5.4 probe: `paper1/data/runs/result1-0.jsonl`.
- Harness investigation: `paper1/docs/reports/002.md`.
- Directory cleanup plan: `paper1/docs/reports/003.md`.
- Cross-repo harness finding: Django/Requests cannot be assumed easier until gold patch sanity passes.

## Current Blocking Issues

### 1. SymPy Environment False Failure

`result1` showed GPT-5.4 can now execute commands, edit the gold file, and submit a patch. The run failed as `repair_fail` because `pass_to_pass=fail`.

But `002.md` found this is likely a **false P2P failure**:

- Task: `sympy__sympy-14774`.
- Model patch only changes inverse trig LaTeX handling.
- P2P fails on `latex(1.0*oo) == "\\infty"`.
- The same P2P test fails on clean base without model patch.
- Root cause: old SymPy + current `mpmath 1.4.1`; `mpmath.libmp.to_str(...)` returns `"inf"` instead of old `"+inf"`.

Conclusion: this is a local harness/environment compatibility bug, not a GPT-5.4 repair-quality result.

### 2. Django Test Mapping Failure

A small gold patch probe on Django failed before any model was involved:

```text
paper1/data/runs/gold_probe_django_requests_3.jsonl
```

Examples:

- `django__django-12113`: gold patch failed because no pytest node id was produced.
- `django__django-10924`: gold patch failed and P2P also failed.

Key error shape:

```text
no pytest node ids:
tests/backends/sqlite/test_creation.py::test_custom_test_name
  (backends.sqlite.test_creation.TestDbSignatureTests)
```

Conclusion: current local harness is too SymPy-shaped. It needs repo-specific test mapping, not just one generic pytest-node function.

## What To Do Now

P0:

1. Fix SymPy compatibility for old SymPy + current mpmath.
2. Fix Django SWE-bench test id mapping.
3. Add a small repo-specific harness seam so SymPy/Django/Requests can diverge safely.
4. Add gold patch sanity as a gate before model experiments on any repo.
5. Re-evaluate `sympy__sympy-14774`, `django__django-12113`, and `django__django-10924` with gold patches.
6. Only after gold sanity passes, rerun a small model probe.

P1:

1. Resume directory cleanup from `003.md`.
2. Use numeric report names going forward: `001.md`, `002.md`, `003.md`, `004.md`.
3. Archive old reports/scripts instead of mixing them with active docs.

## Harness Fix Scope

Files likely involved:

- `paper1/src/budgetflow/local_harness.py`
- possible new module under `paper1/src/budgetflow/`, e.g. `harness_adapters.py`
- tests near `paper1/tests/test_local_harness_pytest_nodes.py` or a new focused test

Required shape:

- Keep `LocalHarness` as the top-level evaluator.
- Add a small repo adapter seam:

```text
LocalHarness
  -> RepoHarnessAdapter
      -> SymPyAdapter
      -> DjangoAdapter
      -> RequestsAdapter
```

- Adapters should own repo-specific compatibility and test id mapping.
- Keep the seam small. Do not rewrite the full compare runner.

Required fixes:

### SymPy

- Extend `apply_python_compat()` / `_patch_python_compat_text()` with a narrow SymPy LaTeX Float compatibility patch:

```python
elif str_real in ("+inf", "inf"):
    return r"\infty"
```

Reason:

- This belongs in the existing compatibility layer.
- It fixes local harness execution under modern Python/dependencies.
- It does not alter the submitted model patch.
- It is lower risk than trying to pin `mpmath` first.

### Django

- Support SWE-bench test identifiers with parenthesized class labels.
- Example input:

```text
tests/backends/sqlite/test_creation.py::test_custom_test_name
  (backends.sqlite.test_creation.TestDbSignatureTests)
```

- Convert it into a runnable pytest node, likely:

```text
tests/backends/sqlite/test_creation.py::TestDbSignatureTests::test_custom_test_name
```

- Preserve existing SymPy node behavior.

### Requests

- Do not assume Requests is easy.
- First add it to gold sanity only if Django/SymPy harness is clean.
- If Requests has repo-specific mapping or env failures, add a Requests adapter rather than patching generic logic blindly.

Acceptance criteria:

- Clean base + test_patch + no model_patch: PASS_TO_PASS passes for `sympy__sympy-14774`.
- Base + test_patch + result1 model_patch: fail_before fails, fail_after passes, pass_to_pass passes.
- Gold patch passes for `django__django-12113`, or the report gives a precise remaining harness blocker.
- Gold patch passes for `django__django-10924`, or the report gives a precise remaining harness blocker.
- Harness detail or report records which compatibility files were patched.
- The submitted patch remains only the model patch, not harness compatibility edits.
- A report is written to `paper1/docs/reports/004.md`.

## Do Not Do Now

- Do not run 5x3, 15x7, or 105-row experiments.
- Do not interpret `result1` as GPT-5.4 repair failure until harness is fixed.
- Do not implement Automatic Budgeting runtime logic before harness trust is restored.
- Do not swap T2/T3 models.
- Do not clean/move broad directories while harness code is being fixed.
- Do not delete `external/mini-swe-agent`; it is the runtime dependency.
- Do not use Docker as the current plan. Current plan is local harness only.

## After Harness Is Fixed

Run minimal verification first:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
PYTHONPATH=src:../external/mini-swe-agent/src \
../.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 1 --step-limit 20 \
  --strategies all_pro \
  --ids sympy__sympy-14774 \
  --trace-turns --trace-max-turns 20 \
  --run-series result2
```

Expected decision:

- If `result2` passes: GPT-5.4 parser + harness are clean for this sanity task.
- If `result2` still fails: inspect whether failure is real model behavior or another harness issue.

Then rerun a small clean probe, not a large matrix:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
PYTHONPATH=src:../external/mini-swe-agent/src \
../.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 2 --step-limit 80 \
  --strategies all_tier2,all_pro,budget_only_tight,budgetflow_full_tight \
  --jobs 4 \
  --ids sympy__sympy-14774,sympy__sympy-13480 \
  --trace-turns --trace-max-turns 80 \
  --run-series clean_gold2_after_harness
```

## Required Report From Next Executor

Write `paper1/docs/reports/004.md` with:

- Files changed.
- Tests run and exact results.
- Evidence that clean base P2P passes.
- Evidence that result1 patch passes/fails after harness fix.
- Evidence for Django gold patch sanity on `django__django-12113` and `django__django-10924`.
- Explanation of the repo adapter seam implemented.
- Whether submitted patch excludes harness compatibility edits.
- Whether experiments are safe to resume.

# Harness PASS Audit: postfix_011_sanity

**Date:** 2026-06-03
**Experiment:** postfix_011_sanity-0.jsonl
**Total PASS rows:** 22
**Audit focus:** fake-pass risks (worktree fallback, gold-detector gaps, compat contamination)

---

## 1. Worktree-fallback PASSes

4 of 22 PASS rows used `patch_source="worktree"` (agent budget exhausted before submit, harness fell back to worktree state). All 4 are **authentic**:

| # | Instance | Strategy | Gold File | Fix Summary |
|---|----------|----------|-----------|-------------|
| 1 | sympy-14774 | budgetflow_full_tight | sympy/printing/latex.py | Added `"acsc"`, `"asec"` to inverse trig table |
| 2 | sympy-14774 | budgetflow_full_loose | sympy/printing/latex.py | Same fix as above |
| 3 | sympy-18621 | budget_only_loose | sympy/matrices/expressions/blockmatrix.py | Added `_entry()` method to BlockDiagMatrix(*) |
| 4 | sympy-18189 | budget_only_tight | sympy/solvers/diophantine.py | Added `syms=None, permute=permute` to recursive diophantine call |

**Assessment:**
- All 4 worktree.patch files touch ONLY the gold file identified in the JSONL.
- All 4 have `agent_gold_edited=True` and correct `agent_gold_files`.
- No conftest, pytest, compat, setup.cfg, or any harness-infrastructure files appear in any patch.
- Exit status for all 4 is `BudgetFlowBudgetError` (budget exhausted, never submitted).

**Caveat for #3 (sympy-18621):** The worktree.patch has a duplicate `_entry()` method definition — one correctly placed inside the `BlockDiagMatrix` class, and a second copy nested inside the module-level `blockcut()` function (dead code, syntactically valid as a local function). The duplicate is sloppy but does not invalidate the pass — the correct `_entry` at the class level provides the fix, and the nested copy is harmless dead code. The fix approach differs from the gold patch (adding `_entry` vs fixing the `blocks` property), but the tests confirm it works.

---

## 2. Gold-detector gaps

1 of 22 PASS rows has `agent_gold_edited=False` and `agent_gold_files=[]`:

| Instance | Strategy | Gold File (expected) | Agent Patch File | Assessment |
|----------|----------|---------------------|------------------|------------|
| django-10924 | budget_only_loose | django/db/models/fields/__init__.py | django/forms/fields.py | Real pass, alternative fix |

**Details:**
- The gold fix for django-10924 (FilePathField path-as-callable) is in the **models layer**: `django/db/models/fields/__init__.py`, where `formfield()` should call `self.path()` if callable.
- The agent's fix is in the **forms layer**: `django/forms/fields.py`, adding a `path` property to `FilePathField` that evaluates callables at access time.
- The tests pass with only the forms-layer fix applied (harness used `submitted.patch`, not `worktree.patch`).
- The agent DID edit the gold file in the worktree (confirmed in `worktree.patch`), but the submitted patch only included the forms file. The gold-detector correctly identified that the submitted patch contains no gold-file edits.
- Patch format is non-standard (`--- ./django/forms/fields.py.bak` with timestamps, from manual `diff` against backup), but the harness applied it successfully (confirmed by `harness_resolved=True`).

**Verdict: Not a fake pass.** The fix is a valid alternative approach that independently satisfies the test requirements. The gold-detector gap is a false alarm — the agent fixed the bug in a different file than the canonical gold patch.

---

## 3. Compat contamination check

All 22 PASS patches (18 submission + 4 worktree) were scanned for:
- `conftest.py` or `conftest` references
- `import pytest`, `from pytest`, or `pytest.` calls
- `compat` module imports
- `setup.cfg`, `pyproject.toml`, `tox.ini`, `Makefile`, or `.yml`/`.yaml` file edits
- Non-source file paths in diff headers

**Result: ZERO contamination found.** Every patch touches only the intended source files (model/application code). No harness-infrastructure files were modified by any agent.

Per-instance summary:
- sympy-14774 (5 passes): all edit `sympy/printing/latex.py` only
- django-10924 (4 passes): edit `django/db/models/fields/__init__.py` only (3) or `django/forms/fields.py` only (1, the gap case)
- sympy-18189 (5 passes): all edit `sympy/solvers/diophantine.py` only
- sympy-18057 (3 passes): all edit `sympy/core/expr.py` only
- sympy-18621 (5 passes): all edit `sympy/matrices/expressions/blockmatrix.py` only

---

## 4. Verdict

**ALL PASSES CLEAN — no issues found.**

- **Worktree fallbacks:** 4/4 are authentic. Gold files edited, model-only code, no harness contamination.
- **Gold-detector gap:** 1 false alarm. django-10924 × budget_only_loose is a real pass via an alternative fix path in a different file.
- **Compat contamination:** 0/22 patches contain any harness-infrastructure code.

No evidence of fake passes, harness leakage, or compat contamination in the postfix_011_sanity experiment.

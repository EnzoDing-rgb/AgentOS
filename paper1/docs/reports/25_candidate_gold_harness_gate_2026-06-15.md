# 25-Candidate Gold Harness Gate — June 15, 2026

No-paid verification that the local test harness can execute SWE-bench gold
patches for the expanded 6×30 candidate pool.

## Summary

| Metric | Value |
|---|---|
| Candidates tested | 25 |
| **PASS** (harness-admissible) | **15** |
| FAIL (harness-inadmissible) | 10 |
| New repos cleared | pylint, seaborn, flask, django |
| Adapter fixes required | 3 (FlaskHAdapter v2, DjangoHAdapter, matplotlib pip cache) |

## Results

### PASS (15) — Harness-Admissible

| Task | Repo | Notes |
|---|---|---|
| `pallets__flask-4045` | flask | FlaskHAdapter v2 fixes |
| `pallets__flask-4992` | flask | FlaskHAdapter v2 fixes |
| `pylint-dev__pylint-5859` | pylint | Standard pytest, clean |
| `mwaskom__seaborn-3190` | seaborn | Standard pytest, clean |
| `mwaskom__seaborn-3407` | seaborn | Standard pytest, clean |
| `sphinx-doc__sphinx-7738` | sphinx | SphinxHAdapter compat |
| `sphinx-doc__sphinx-8282` | sphinx | SphinxHAdapter compat |
| `sphinx-doc__sphinx-8595` | sphinx | SphinxHAdapter compat |
| `django__django-11049` | django | DjangoHAdapter: tests/__init__.py + conftest |
| `django__django-11179` | django | DjangoHAdapter |
| `django__django-12908` | django | DjangoHAdapter |
| `django__django-13964` | django | DjangoHAdapter |
| `django__django-15814` | django | DjangoHAdapter |
| `django__django-15851` | django | DjangoHAdapter |
| `matplotlib__matplotlib-25433` | matplotlib | Requires full pip install (C extensions) |

### FAIL (10) — Harness-Inadmissible

#### p2p Regression (3)

Gold patch fixes f2p tests but breaks pass-to-pass tests. SWE-bench test spec
issue — not fixable at harness layer.

| Task | Detail |
|---|---|
| `pallets__flask-5063` | f2p=ok, p2p regression |
| `pylint-dev__pylint-7080` | f2p=ok, p2p test_file_can_be_combined fails |
| `sphinx-doc__sphinx-8435` | f2p=ok, p2p namespace package noise |

#### Patch Doesn't Fix f2p (5)

Gold patch applies but f2p tests still fail post-patch. Root causes vary.

| Task | Root Cause | Harness Fixable? |
|---|---|---|
| `matplotlib__matplotlib-23964` | vcs_versioning build error | No — build chain issue |
| `psf__requests-2148` | Test spec mismatch (test removed in this commit) | No |
| `pylint-dev__pylint-7114` | ImportError: `from pylint import checkers` during conftest load | Maybe — needs PylintHAdapter with pip install |
| `pylint-dev__pylint-7228` | Same ImportError as 7114 | Maybe — same root cause |
| `sphinx-doc__sphinx-8506` | Namespace package noise, f2p tests don't pass | No |

#### Bug Not Detected (2)

Pre-patch f2p tests already pass — the harness can't distinguish bug absence
from bug presence. SWE-bench test spec limitation.

| Task | Detail |
|---|---|
| `sphinx-doc__sphinx-8721` | fb=True (pre-patch tests pass), p2p=ok |
| `psf__requests-863` | fb=True, p2p fails — double failure |

## Adapter Fixes Applied

### FlaskHAdapter v2

**Original bug:** pytest 9.1.0 removed `_pytest.monkeypatch.notset` (lowercase).
Flask conftest's `_reset_os_environ` fixture injects `monkeypatch.notset`
directly into `monkeypatch._setitem`, which is then compared by identity against
`NOTSET` in `MonkeyPatch.undo()`.

**Fix:** Alias `_pytest.monkeypatch.notset = _pytest.monkeypatch.NOTSET` instead
of injecting `object()`. The identity check `value is NOTSET` in `undo()` must
pass.

**v1 error chain:**
1. `notset = object()` injected
2. `_reset_os_environ` stores `object()` in `_setitem`
3. `undo()` compares `object() is NOTSET` → False
4. `os.environ[key] = object()` → `TypeError: str expected, not object`

**v2 fix:** `notset = _pytest.monkeypatch.NOTSET` (the module-level singleton)

### DjangoHAdapter

**Fix:** Create `tests/__init__.py` when missing. Django 3.0 alpha doesn't have
it, causing `ModuleNotFoundError: No module named 'tests.test_sqlite'`.

**Files created:** `tests/__init__.py` with `# BudgetFlow compat` marker.

### matplotlib pip cache poisoning

**Bug:** `_pip_marker_path` writes a `.pip_ok` marker in the worktree parent
directory. When the worktree is removed and recreated, the stale marker causes
`pip install` to be skipped — but the installed C extensions were in the deleted
worktree.

**Fix (manual during probe):** Deleted stale `.pip_ok` files before re-probing.
**Root cause fix after audit:** The pip marker now lives inside the current worktree as `.budgetflow_pip_ok`, so deleting/recreating a worktree invalidates the marker automatically.

## Repo Health Summary

| Repo | Candidates | PASS | FAIL | Status |
|---|---|---|---|---|
| pallets/flask | 3 | 2 | 1 | Ready (FlaskHAdapter v2) |
| pylint-dev/pylint | 4 | 1 | 3 | Partial — 3 failing need investigation |
| mwaskom/seaborn | 2 | 2 | 0 | Ready — clean |
| sphinx-doc/sphinx | 6 | 3 | 3 | Partial — 3 failing are spec/namespace issues |
| django/django | 6 | 6 | 0 | Ready (DjangoHAdapter fix) |
| psf/requests | 2 | 0 | 2 | Blocked — both are test spec failures |
| matplotlib/matplotlib | 2 | 1 | 1 | Partial — 25433 PASS, 23964 build chain |

## 15 Harness-Admissible Tasks for Next Round

```
pallets__flask-4045
pallets__flask-4992
pylint-dev__pylint-5859
mwaskom__seaborn-3190
mwaskom__seaborn-3407
sphinx-doc__sphinx-7738
sphinx-doc__sphinx-8282
sphinx-doc__sphinx-8595
django__django-11049
django__django-11179
django__django-12908
django__django-13964
django__django-15814
django__django-15851
matplotlib__matplotlib-25433
```

Repo coverage: flask(2), pylint(1), seaborn(2), sphinx(3), django(6), matplotlib(1)

Note: 0 requests tasks pass — drop from 6×30.

## Residual Risks

1. **pylint-7114 and pylint-7228** fail with import errors during conftest
   load. A PylintHAdapter with `pip install -e .` might fix them — deferred to
   future round.

2. **requests repo is not admitted into the 6x30 mainline.** Both requests candidates failed the gold gate, so they remain forensic-only.

3. **matplotlib requires heavier local setup** than most repos. Budget allocation and runtime expectations must account for this in the frozen router plan and postmortem.

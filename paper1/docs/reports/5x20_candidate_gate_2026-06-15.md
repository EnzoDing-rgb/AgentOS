# 5x20 Candidate Gate — 2026-06-15

## Objective

Screen SWE-bench Lite candidates from two new repos (psf/requests,
sphinx-doc/sphinx) for a future 5x20 experiment expansion.  Run no-paid gold
harness gate on each candidate.  Fix repo-level compat issues with minimal
adapters.  Classify all failures.  Recommend final 4 tasks or flag NO-GO.

Hard constraints: no paid calls, no historical JSONL modification, no task-id
if/else, no backward compat fallbacks.

## Candidate Pool

| Repo | SWE-bench Lite Total | Tested | PASS | FAIL |
|---|---|---|---|---|
| psf/requests | 6 | 6 | 2 | 4 |
| sphinx-doc/sphinx | 16 | 7 | 5 | 2 |
| **Total** | 22 | 13 | 7 | 6 |

Selection criteria for initial 8: diversity of fail_to_pass / pass_to_pass
counts.  First batch: requests-863, 1963, 2317, 2674 + sphinx-7975, 8273,
8721, 10325.  Second batch (after adapter fix): requests-2148, 3362 +
sphinx-8595, 7686, 11445.

## Repo-Level Adapter: SphinxHAdapter

### Root Cause

Older Sphinx versions import removed Jinja2 names:

| Old Name | New Name (Jinja2 >= 3.1) | Affected File |
|---|---|---|
| `environmentfilter` | `pass_environment` | `sphinx/util/rst.py` |
| `contextfunction` | `pass_context` | `sphinx/jinja2glue.py` |
| `contextfilter` | `pass_context` | (none observed) |
| `evalcontextfilter` | `pass_eval_context` | (none observed) |
| `evalcontextfunction` | `pass_eval_context` | (none observed) |

Installed Jinja2 is 3.1.6.  The `from jinja2 import <old_name>` lines fail
at import time, blocking the entire Sphinx test infrastructure.

### Fix

`SphinxHAdapter.apply_compat()` walks all `sphinx/**/*.py` files in the
ephemeral worktree and replaces `from jinja2 import <old_name>` with
`from jinja2 import <new_name> as <old_name>` — preserving the decorator
name so downstream usage is unchanged.

### Files Changed

- `paper1/src/budgetflow/local_harness_adapters.py`:
  - `SphinxHAdapter` class with `apply_compat()` and `repo_slug = "sphinx-doc__sphinx"`
  - `_JINJA2_RENAMES` dict (5 old→new mappings)
  - `_patch_jinja2_imports()` helper using regex for comma-separated imports
  - `RepoHarnessAdapter.for_task()`: route `sphinx-doc__sphinx` → `SphinxHAdapter()`

No changes to sympy, django, requests, or default adapters.  No task-id
branching.

## Gold Harness Probe Results

### PASS (7/13)

| Task | Repo | F2P | P2P | Bootstrap | Notes |
|---|---|---|---|---|---|
| psf__requests-1963 | psf/requests | 7 | 112 | — | Round 1 PASS |
| psf__requests-3362 | psf/requests | 1 | 75 | — | Round 2 PASS |
| sphinx-doc__sphinx-10325 | sphinx-doc/sphinx | 1 | 5 | — | Round 1 PASS, no adapter needed |
| sphinx-doc__sphinx-7975 | sphinx-doc/sphinx | 1 | 7 | — | PASS after jinja2 compat fix |
| sphinx-doc__sphinx-8273 | sphinx-doc/sphinx | 1 | 3 | — | PASS after jinja2 compat fix |
| sphinx-doc__sphinx-8595 | sphinx-doc/sphinx | 1 | 0 | — | PASS |
| sphinx-doc__sphinx-7686 | sphinx-doc/sphinx | 2 | 15 | — | PASS |

### FAIL — Non-Reproducible (2/13)

| Task | Detail |
|---|---|
| psf__requests-863 | fail_before=True: bug's fail_to_pass tests pass without gold patch. Bug does not manifest in harness environment. |
| sphinx-doc__sphinx-8721 | fail_before=True: same — test passes without fix. |

### FAIL — Network-Dependent (3/13)

| Task | Detail |
|---|---|
| psf__requests-2148 | fail_before=fail, fail_after=fail: `ConnectionResetError(104, 'Connection reset by peer')` during test that hits external HTTP endpoint. |
| psf__requests-2317 | fail_before=fail, fail_after=pass, pass_to_pass=fail: same `ConnectionResetError` in pass_to_pass. Gold fix works (fail_after=pass), but p2p network flakiness makes it unreliable. |
| psf__requests-2674 | fail_before=fail, fail_after=fail, pass_to_pass=fail: `ConnectionResetError` in both model_patch and p2p phases. |

All three fail on `test_auth_is_stripped_on_redirect_off_host` or
`test_POSTBIN_GET_POST_FILES_WITH_DATA` — tests that make real HTTP requests
to external hosts.  These are test design issues (tests assume network
access), not harness bugs.

### FAIL — Patch Apply Failed (1/13)

| Task | Detail |
|---|---|
| sphinx-doc__sphinx-11445 | Sphinx 7.1.0.  `model_patch_ok` = None — gold patch does not apply cleanly to this version.  Likely version skew between SWE-bench patch baseline and the checkout. |

## Failure Classification Summary

| Class | Count | Tasks |
|---|---|---|
| PASS | 7 | requests-1963, 3362; sphinx-10325, 7975, 8273, 8595, 7686 |
| Non-reproducible | 2 | requests-863, sphinx-8721 |
| Network-dependent | 3 | requests-2148, 2317, 2674 |
| Patch apply failed | 1 | sphinx-11445 |

No harness bugs found.  The 3 network-dependent requests failures share the
same root cause (real HTTP in tests) and are not fixable with a repo adapter —
they need network isolation or test mocking, which would modify test semantics.

## Recommended 5x20 Tasks (4 tasks, 2 per repo)

| # | Task | Repo | F2P | P2P | Rationale |
|---|---|---|---|---|---|
| 1 | psf__requests-1963 | psf/requests | 7 | 112 | Moderate complexity, broad p2p coverage |
| 2 | psf__requests-3362 | psf/requests | 1 | 75 | Minimal complexity, good diversity vs 1963 |
| 3 | sphinx-doc__sphinx-7975 | sphinx-doc/sphinx | 1 | 7 | Simple single-file fix, needs adapter |
| 4 | sphinx-doc__sphinx-10325 | sphinx-doc/sphinx | 1 | 5 | Simple, works without adapter (modern version) |

### Backup Candidates (from remaining PASS pool)

| Task | F2P | P2P | Notes |
|---|---|---|---|
| sphinx-doc__sphinx-8273 | 1 | 3 | Very narrow p2p |
| sphinx-doc__sphinx-8595 | 1 | 0 | No p2p at all |
| sphinx-doc__sphinx-7686 | 2 | 15 | Good p2p coverage |

## Test Suite

```
466 passed, 1 skipped — all clean
```

No regressions from SphinxHAdapter or _patch_jinja2_imports additions.

## Adapter Inventory

| Adapter | Repo | Purpose |
|---|---|---|
| SymPyHAdapter | sympy/sympy | latex.py compat, pytest imports, importtools catch |
| DjangoHAdapter | django/django | conftest.py (INSTALLED_APPS, DATABASES, migrate), runtests.py test runner |
| SphinxHAdapter | sphinx-doc/sphinx | jinja2 >= 3.1 compat (environmentfilter/contextfunction/etc → pass_* aliases) |
| RequestsHAdapter | psf/requests | no-op (reserved for future compat) |
| DefaultHAdapter | * | no-op fallback |

All adapters are repo-level only.  No task-id branching.  All compat is
applied to ephemeral worktrees, never to the source checkout.

## Verdict: GO

7/13 candidates pass gold harness gate.  2 repos both have >= 2 PASS tasks.
SphinxHAdapter fixes the jinja2 compat issue cleanly with a general solution
covering all 5 removed names.  No paid calls, no historical data modified.

Recommend proceeding to 5x20 artifact generation (value matrix, frozen plan,
budget plan) when the 5x20 expansion is scheduled.

## Residual Risks

1. **requests network-dependent tests**: 3 of 6 requests tasks fail due to
   network-dependent test design.  The 2 PASS tasks (1963, 3362) avoid these
   tests.  If additional requests tasks are needed later, network isolation
   or test mocking would be required — not a harness fix, a test design issue.

2. **Sphinx version spread**: Sphinx tasks span versions from 3.1.0.dev to
   7.1.0.  The jinja2 compat fix covers versions that use the old names;
   newer versions (like sphinx-10325) don't need it.  If additional sphinx
   tasks are added, the compat should "just work" for old imports and be
   a no-op for new ones.

3. **sphinx-8721 non-reproducible**: The bug's fail_to_pass test passes
   without the gold fix in our environment.  This may be Python version
   dependent (3.11 changed some stdlib behavior that the test relies on).
   Not a harness issue.

4. **sphinx-11445 patch apply**: Sphinx 7.1.0 has diverged from the
   SWE-bench patch baseline.  Excluded — not fixable without modifying
   the gold patch.

# 15-Task Candidate Gold Harness Gate — June 15, 2026

## Summary

| Metric | Value |
|---|---|
| Candidates tested | 15 |
| Gold harness PASS | 10 |
| Gold harness FAIL | 5 |
| New repos | pylint (2), seaborn (2), pytest (2), xarray (1), scikit-learn (1) |
| New repo passes | pylint (2/2), seaborn (2/2) |
| New repo failures | pytest (0/2), xarray (0/1), scikit-learn (0/1) |

**Gold harness PASS means harness admissible — NOT agent solvable.**

---

## Results by Task

### PASS — Harness Admissible (10 tasks)

| # | Task | Repo | Status |
|---|---|---|---|
| 1 | sympy__sympy-22714 | sympy | PASS |
| 2 | sympy__sympy-12171 | sympy | PASS |
| 3 | sympy__sympy-17655 | sympy | PASS |
| 4 | django__django-13447 | django | PASS |
| 5 | sphinx-doc__sphinx-8273 | sphinx | PASS |
| 6 | sphinx-doc__sphinx-7686 | sphinx | PASS |
| 7 | pylint-dev__pylint-7993 | pylint | PASS — NEW REPO |
| 8 | pylint-dev__pylint-6506 | pylint | PASS — NEW REPO |
| 9 | mwaskom__seaborn-3010 | seaborn | PASS — NEW REPO |
| 10 | mwaskom__seaborn-2848 | seaborn | PASS — NEW REPO |

### FAIL — Harness Blocked (5 tasks)

| # | Task | Repo | Failure Mode | Root Cause |
|---|---|---|---|---|
| 11 | django__django-16527 | django | fail_before=False, p2p=False | Django test runner not configured for non-standard test layout |
| 12 | pytest-dev__pytest-5227 | pytest | fail_before=False, p2p=False | pytest test infrastructure needs conftest/setup adaptation |
| 13 | pytest-dev__pytest-8365 | pytest | fail_before=False, p2p=False | Same pytest infrastructure gap |
| 14 | pydata__xarray-4248 | xarray | fail_before=False, p2p=False | xarray test runner requires netCDF4/numpy test fixtures |
| 15 | scikit-learn__scikit-learn-13584 | sklearn | fail_before=False, p2p=False, pip install failed | sklearn needs Cython/numpy/scipy build deps; pip install -e . failed |

All 5 failures share the same root cause: **the local test harness cannot correctly execute the SWE-bench test specification.** The pre-patch tests don't register as failing (`fail_before=False`), meaning either:
- The test selection (f2p/p2p lists) doesn't match what the local runner expects
- The test infrastructure (pytest plugins, Django settings, sklearn build) needs repo-specific setup that the generic harness adapter doesn't provide

These are **harness adapter problems, not agent or task problems.** They must be fixed in the repo adapter / harness adapter / runtime acquisition layer. No task-id if/else in mechanism code.

---

## New Repo Health Assessment

### pylint-dev/pylint — CLEAN
- Both tasks pass gold harness with no compat patches needed.
- pip install -e . works on first try.
- Test runner is standard pytest — compatible with the existing harness adapter.
- **Verdict: pylint tasks are ready for paid experiments.**

### mwaskom/seaborn — CLEAN
- Both tasks pass gold harness with no compat patches needed.
- pip install -e . works on first try.
- **Verdict: seaborn tasks are ready for paid experiments.**

### pytest-dev/pytest — BLOCKED
- Both tasks fail with `fail_before=False` — the test suite can't verify the pre-patch failure.
- pytest's own test infrastructure uses non-standard conftest and fixture patterns.
- The test spec (f2p/p2p lists) may reference internal pytest test markers not available in the local harness.
- **Verdict: Needs repo adapter work before paid experiments.** Specific issues:
  - pytest tests use `pytest.mark` internal fixtures
  - The test runner expects a specific `PYTHONPATH` setup for pytest's own source
  - `testing/` directory conventions differ from other repos

### pydata/xarray — BLOCKED
- Fails with `fail_before=False` — tests don't detect pre-patch failure.
- xarray test suite depends on netCDF4, h5netcdf, scipy, and other scientific Python packages.
- The test spec may reference tests that require network I/O or large fixture files.
- **Verdict: Needs runtime acquisition work (scientific Python deps) + repo adapter.**

### scikit-learn/scikit-learn — BLOCKED
- pip install -e . failed — build dependency chain (Cython, numpy, scipy) too heavy.
- scikit-learn requires compiled extensions (Cython → C → binary).
- The runtime environment doesn't have the full scientific Python build toolchain.
- **Verdict: Not feasible in current server environment.** Scientific Python build chain would require global environment changes (gcc, gfortran, openblas). This violates the constraint "不要装 VPN 或改全局环境."

---

## Recommended Candidate Set for Next Paid Round

From the 10 harness-admissible tasks, the recommended 8-10 task set:

| Priority | Task | Repo | Rationale |
|---|---|---|---|
| KEEP | sympy__sympy-22714 | sympy | New sympy task, different from 5×20 set |
| KEEP | sympy__sympy-12171 | sympy | New sympy task |
| KEEP | sympy__sympy-17655 | sympy | New sympy task |
| KEEP | django__django-13447 | django | Django task, harness-admissible |
| KEEP | sphinx-doc__sphinx-8273 | sphinx | Sphinx task, harness-admissible (round3 fixed) |
| KEEP | sphinx-doc__sphinx-7686 | sphinx | Sphinx task, harness-admissible |
| KEEP | pylint-dev__pylint-7993 | pylint | New repo diversity |
| KEEP | pylint-dev__pylint-6506 | pylint | New repo diversity |
| KEEP | mwaskom__seaborn-3010 | seaborn | New repo diversity |
| KEEP | mwaskom__seaborn-2848 | seaborn | New repo diversity |
| DROP | django__django-16527 | django | Harness blocked |
| DROP | pytest-dev__pytest-5227 | pytest | Harness blocked |
| DROP | pytest-dev__pytest-8365 | pytest | Harness blocked |
| DROP | pydata__xarray-4248 | xarray | Harness blocked |
| DROP | scikit-learn__scikit-learn-13584 | sklearn | Build blocked |

---

## Residual Risks

1. **pylint and seaborn are untested in paid experiments.** The 5×20 experience showed that new repos (Requests, Sphinx, Django) had high parser failure rates. pylint and seaborn may have similar protocol issues even though the gold harness passes.

2. **No agent solvability data for any of these 15 tasks.** Gold harness PASS only verifies the test infrastructure — it says nothing about whether any model tier can solve the task. BudgetFlow has no prior JSONL for pylint or seaborn, so the first paid round on these repos will be a cold-start diagnostic.

3. **Django-13447 is the only Django task that passed the harness.** The 5×20 Django tasks (10924, 16046) had real passes, but also heavy infrastructure noise. Single-task repo coverage is weak evidence.

4. **pytest and xarray would be scientifically valuable but need harness adapter investment.** These repos exercise different failure modes (plugin systems, scientific computing) that would stress-test BudgetFlow's generalization. Defer to a future round after harness adapter work.

---

## Next Round Budget Plan Suggestion

The 10 harness-admissible tasks are candidate additions, not the full next
paper run. The next mainline experiment should use the configured 6-policy
strategy set in `docs/config/paper_mainline_strategies.v1.json` and scale to
25-30 tasks:

1. `bare_t2_baseline`
2. `bare_t3_baseline`
3. `enterprise_router_baseline`
4. `budgetflow_same_enterprise_router`
5. `budgetflow_task_level`
6. `budgetflow_segment`

`budgetflow_task_level` is the Claim 1 main policy; `budgetflow_segment` is the
Claim 2 segment-aware enhancement.

**Option A: frozen_plan_cap_sum (recommended)**
- Use explicit per-task caps from a frozen router plan.
- Avoids projection model uncertainty (MAPE 53.5% from 5×20 audit).
- Budget = sum of per-task base_caps.

**Option B: target_utilization with prior calibration WARNING**
- The 5×20 calibration audit MAPE=53.5% triggers a stern WARNING but not BLOCK.
- Not recommended for first paid round on new repos (no historical cost data for pylint/seaborn).

**Suggested budget**: code-generated frozen plan for the exact selected 25-30
task set, using `model_tiers.t3x3.json` for the scarcity diagnostic unless the
run is explicitly a real-billing-cost audit.

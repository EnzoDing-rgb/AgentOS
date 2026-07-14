# Mainline 20x25 Candidate Manifest

**2026-06-17** | 25 selected / 27 excluded | 6 repos | 0 new repos vs 6x30

## Selected (25)

| # | Task | Repo | Source | f2p | p2p |
|---|------|------|--------|-----|-----|
| 1 | sympy__sympy-22714 | sympy | 6x30 anchor | 20 | 205 |
| 2 | sympy__sympy-12171 | sympy | 6x30 anchor | 19 | 128 |
| 3 | sympy__sympy-17655 | sympy | 6x30 anchor | 30 | 175 |
| 4 | sympy__sympy-24102 | sympy | 6x30 anchor | 57 | 2 |
| 5 | sympy__sympy-11870 | sympy | new probe | 13 | 1093 |
| 6 | sympy__sympy-12236 | sympy | new probe | 12 | 2739 |
| 7 | sympy__sympy-12419 | sympy | new probe | 17 | 549 |
| 8 | sympy__sympy-12454 | sympy | new probe | 36 | 2666 |
| 9 | sympy__sympy-13031 | sympy | new probe | 22 | 153 |
| 10 | sympy__sympy-13437 | sympy | new probe | 13 | 326 |
| 11 | sympy__sympy-13773 | sympy | new probe | 15 | 1190 |
| 12 | sympy__sympy-13895 | sympy | new probe | 43 | 1743 |
| 13 | sympy__sympy-13915 | sympy | new probe | 39 | 1495 |
| 14 | django__django-13447 | django | 6x30 anchor | 72 | 367 |
| 15 | django__django-11179 | django | 6x30 anchor | 72 | 2280 |
| 16 | django__django-12908 | django | 6x30 anchor | 211 | 2177 |
| 17 | sphinx-doc__sphinx-8273 | sphinx | 6x30 anchor | 64 | 140 |
| 18 | sphinx-doc__sphinx-7686 | sphinx | 6x30 anchor | 166 | 938 |
| 19 | sphinx-doc__sphinx-7975 | sphinx | new probe | 68 | 473 |
| 20 | sphinx-doc__sphinx-8801 | sphinx | new probe | 70 | 537 |
| 21 | mwaskom__seaborn-3010 | seaborn | 6x30 anchor | 67 | 131 |
| 22 | mwaskom__seaborn-2848 | seaborn | 6x30 anchor | 64 | 3974 |
| 23 | pallets__flask-4045 | flask | 6x30 anchor | 134 | 3518 |
| 24 | pallets__flask-4992 | flask | 6x30 anchor | 52 | 955 |
| 25 | pylint-dev__pylint-6506 | pylint | 6x30 anchor | 120 | 335 |

**Repo counts**: sympy 13, django 3, sphinx 4, seaborn 2, flask 2, pylint 1

## Excluded (27)

### psf/requests — 6 tasks, all blocked
- **1963, 3362, 863**: `non_reproducible` — fail_before=False, bug does not manifest in Python 3.11 env
- **2148, 2317, 2674**: `network_dependent` — ConnectionResetError, real HTTP in tests

### sphinx-doc/sphinx — 8 tasks
- **10325, 8721, 10451, 8474, 8506, 8627**: `non_reproducible` — all f2p tests pass without fix
- **8713, 8435**: `p2p_regression` — f2p fixes but breaks pass_to_pass
- **11445**: `patch_apply_fail` — gold patch does not apply to Sphinx 7.1.0

### pylint-dev/pylint — 4 tasks
- **7080**: `p2p_regression`
- **7114, 7228**: `dependency_noise` — ImportError, needs PylintHAdapter with pip install
- **5859**: `dependency_noise` — astroid metadata, in 6x30 but flagged

### Other repos
- **matplotlib__matplotlib-23964**: `build_risk` — C extension build fails
- **django__django-16527**: `test_infra_gap` — non-standard test layout
- **pytest-dev__pytest-5227, pytest-8365**: `test_infra_gap` — conftest adaptation needed
- **pydata__xarray-4248**: `test_infra_gap` — netCDF4/numpy fixtures
- **scikit-learn__scikit-learn-13584**: `build_risk` — Cython/numpy/scipy build chain
- **pallets__flask-5063**: `p2p_regression`
- **sympy__sympy-11400**: `non_reproducible`

## Key Findings

- **0 new repos added** vs 6x30. psf/requests (6 tasks, best repo diversity candidate) is completely blocked in current env.
- **sympy dominance**: 13/25 are sympy. Reflects mature SymPyHAdapter, not selection bias.
- **11 new tasks** confirmed (9 sympy + 2 sphinx) via fresh June 17 gold harness probe.
- **Residual risk**: psf/requests and sphinx-10325 PASS on June 15 gate but FAIL on June 17 probe — environment skew suspected, do not trust without re-verification.

Full machine-readable data: `mainline_20x25_candidate_manifest_20260617.json`

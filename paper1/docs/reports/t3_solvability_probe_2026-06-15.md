# T3 Strongest-Model Solvability Probe — June 15, 2026

Paid `bare_t3_baseline` (GPT-5.4) probe on 15 harness-admissible tasks. Goal:
classify solvability before committing to the full 6×30 paid mainline.

## Summary

| Metric | Value |
|---|---|
| Tasks probed | 15 |
| **T3 Solved** | **7 (46.7%)** |
| Harness-verified model fail | 5 (33.3%) |
| Infra/dependency noise | 1 (6.7%) |
| Patch/protocol fail | 2 (13.3%) |
| Provider/Runtime Fail | 0 (all retried) |
| Total cost | ~$0.20 (diagnostic t3x3 catalog) |

## Classification

### T3 Solved (7)

| Task | Turns | Notes |
|---|---|---|
| `mwaskom__seaborn-3407` | 6 | Seaborn clean — first-task solve for this repo |
| `sphinx-doc__sphinx-8595` | 4 | Sphinx solve |
| `django__django-11179` | 3 | Django solve |
| `django__django-12908` | 3 | Django solve |
| `django__django-13964` | 3 | Django solve |
| `django__django-15814` | 4 | Django solve |
| `django__django-15851` | 5 | Django solve |

### Harness-Verified Model Fail (5)

These tasks passed the gold harness gate, the T3 run produced a patch/attempt, and local verification still failed. Treat these as strongest-model failures for this diagnostic, subject to normal SWE-bench stochasticity.

**Patch extracted but harness fail (4):**
| Task | Detail |
|---|---|
| `pallets__flask-4045` | f2p fail after patch |
| `pallets__flask-4992` | f2p fail after patch |
| `mwaskom__seaborn-3190` | f2p fail after patch |
| `matplotlib__matplotlib-25433` | f2p + p2p fail after patch |

**p2p regression (1):**
| Task | Detail |
|---|---|
| `sphinx-doc__sphinx-7738` | f2p=ok but p2p regression |

### Infra / Dependency Noise (1)

| Task | Detail |
|---|---|
| `pylint-dev__pylint-5859` | pip install fails (astroid metadata), then model_patch apply fail. Do not treat as clean model-capability evidence until the Pylint adapter/dependency path is hardened. |

### Patch / Protocol Fail (2)

| Task | Detail |
|---|---|
| `sphinx-doc__sphinx-8282` | Agent exited / patch did not fix; needs trace-level classification before calling pure capability. |
| `django__django-11049` | model_patch apply fail; likely patch/protocol quality rather than clean verification failure. |

## Repo Solvability

| Repo | Solved/Total | Solvability |
|---|---|---|
| django | 5/6 | HIGH — ideal signal repo |
| sphinx | 1/3 | MEDIUM — mixed |
| seaborn | 1/2 | MEDIUM — cold start, one solved |
| flask | 0/2 | LOW — both model fails |
| pylint | 0/1 | LOW — pip install issue |
| matplotlib | 0/1 | LOW — model fail |

## Caveats

1. **pylint-5859 pip install failure** — astroid build metadata error. This is a
   task dependency issue, not a model issue. Without `pip install -e .`, the
   agent runs in a degraded environment.

2. **matplotlib-25433 used cached pip skip** — the C extensions were built in a
   prior probe run. The cached install was used. Fresh install needs ~90s.

3. **Solvability is strongly repo-correlated.** Django (5/6) is dramatically
   easier than flask (0/2) and matplotlib (0/1). Task selection will dominate
   yield more than strategy differences.

4. **7/15 = 46.7% T3 solve rate** is plausible for a mixed SWE-bench Lite subset, but this report should not be used as a public benchmark comparison. The main use is task-pool triage and failure-owner classification.

## Bottom Line

The probe does not show that the expanded task pool is broken. It shows real repo variance: Django is comparatively easy for T3, Flask/Matplotlib are harder, and one Pylint task carries dependency/setup noise. For paper evidence, post-run analysis must separate model failure from adapter/dependency/protocol failure.

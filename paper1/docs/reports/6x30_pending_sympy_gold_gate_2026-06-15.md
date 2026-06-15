# 6x30 Pending SymPy Gold Harness Gate — June 15, 2026

No-paid verification for the 5 SymPy tasks that were pending in the worker's 6x30 manifest.

## Summary

| Metric | Value |
|---|---:|
| Tasks tested | 5 |
| Gold harness PASS | 5 |
| Gold harness FAIL | 0 |
| Raw local evidence | `data/runs/gold_harness_probe_6x30_pending_sympy.jsonl` |

Gold harness PASS means the local harness can reproduce the SWE-bench test spec with the gold patch: pre-patch f2p fails, post-patch f2p passes, and p2p passes. It does not mean the agent/model can solve the task.

## Results

| Task | Result | Detail |
|---|---|---|
| `sympy__sympy-24102` | PASS | fail_before=fail, fail_after=pass, p2p=pass |
| `sympy__sympy-15346` | PASS | fail_before=fail, fail_after=pass, p2p=pass |
| `sympy__sympy-18621` | PASS | fail_before=fail, fail_after=pass, p2p=pass |
| `sympy__sympy-13647` | PASS | fail_before=fail, fail_after=pass, p2p=pass |
| `sympy__sympy-13177` | PASS | fail_before=fail, fail_after=pass, p2p=pass |

## Verdict

These 5 tasks are now harness-admissible for the 6x30 staged paid run. The 6x30 manifest can be treated as 30/30 gold-gated, subject to the usual paid-run provider, budget, and runtime checks.

# 4x25 Partial Run Observability Slice

## Objective

Audit the latest partial paid run
`paper1/data/runs/mainline_4x25_glm51_rerun_after_billing_20260618-0.jsonl`
against the North Star evidence rules, without restarting paid work, and patch
the no-paid observability gaps that made the partial artifact easy to overread.

## Experiment Diagnosis

The run is a partial diagnostic, not paper evidence: 25 JSONL rows out of a
planned 100 completed.

Per-policy rows from the JSONL:

- `bare_t2_baseline`: 4 rows, 2 pass, Yield 1.61, cost 1.3653, Yield/$ 1.18.
- `bare_t3_baseline`: 12 rows, 4 pass, Yield 3.25, cost 6.3760, Yield/$ 0.51.
- `enterprise_router_baseline`: 4 rows, 2 pass, Yield 1.61, cost 1.5381, Yield/$ 1.05.
- `budgetflow_task_level`: 5 rows, 2 pass, Yield 1.61, cost 1.3247, Yield/$ 1.22.

The signal does not contradict Claim 1: on the shared completed slice,
BudgetFlow task-level matched the T2 and enterprise-router Yield with lower
scoreable cost. It also does not establish a paper conclusion because the run
is partial and uneven across policies.

No provider, billing, parser, or budget-exhaustion failure appears in the 25
rows. All rows use provider usage and `catalog_provider_usage`; all
`provider_error_kind` and parser-error fields are empty.

The main evidence caveat is two `budgetflow_task_level` rows with
`harness_trust=incomplete`, `score_status=true_fail`, and `no_patch_extracted`:

- `sympy__sympy-24102`: `StagnationExit`, `post_patch_stable_no_submit`,
  gold file edited but no submitted patch.
- `sympy__sympy-11870`: `StagnationExit`, `stagnation_repeat_command`,
  no gold file edited and no submitted patch.

Those are valid zero-Yield paid outcomes for a partial diagnostic, but they
must be called out as scoreable rows with incomplete harness trust so they are
not confused with fully verified harness failures.

## Files Changed

- `paper1/src/budgetflow/run_observability/checks.py`
  - Partial-run warnings now report `rows_done/total_expected` and per-policy
    progress such as `budgetflow_task_level=5/25`.
  - Partial detection also fires when heartbeat rows are incomplete even if the
    observed unique task count happens to match the planned task count.
- `paper1/src/budgetflow/run_observability/schema.py`
  - Adds `SCOREABLE_UNTRUSTED_HARNESS` warnings for pass/true_fail rows whose
    `harness_trust` is not `trusted`.
- `paper1/src/budgetflow/experiments/compare_summary.py`
  - Summary event JSON no longer duplicates heavyweight `turn_traces`,
    `budget_plan`, `budget_input`, or full `detail`; the canonical evidence
    remains the JSONL row.
  - Keeps `turn_trace_count` and a small `budget_plan_summary` for readability.
- `paper1/tests/test_run_observability_audit.py`
  - Regression coverage for partial row/policy progress and scoreable
    untrusted harness warnings.
- `paper1/tests/test_compare_record_schema.py`
  - Regression coverage for compact summary event payloads.

## Interface Decisions

- Did not rewrite historical JSONL or summary artifacts.
- Did not convert no-patch stagnation rows to `abort`. A paid strategy that
  spends and fails to produce a verifiable patch is still a zero-Yield outcome
  unless the owner is provider, parser, infra, or blocking harness failure.
- Did make incomplete harness trust visible in checker output so paper metrics
  and learning audits can separate scoreable zero-Yield outcomes from clean
  fully verified harness failures.

## Deleted Stale Paths Or Tests

None.

## Verification

- `PYTHONPATH=paper1/src pytest -q paper1/tests`
  - Result: `675 passed in 4.27s`.
- `PYTHONPATH=paper1/src python -m budgetflow.run_observability.cli --jsonl paper1/data/runs/mainline_4x25_glm51_rerun_after_billing_20260618-0.jsonl --heartbeat 600 --quiet`
  - Result: exit 0 in quiet mode while printing the expected issues. Non-quiet
    mode exits nonzero because the historical heartbeat is still
    `HEARTBEAT_DEAD_PID`.
  - New useful warnings include:
    - two `SCOREABLE_UNTRUSTED_HARNESS` rows for BudgetFlow task-level,
    - `PARTIAL_RUN ... rows_done=25/100 ... policy_progress={bare_t2_baseline=4/25, bare_t3_baseline=12/25, budgetflow_task_level=5/25, enterprise_router_baseline=4/25}`.

## Residual Risks

- The run stopped at 25/100 rows, so the artifact remains diagnostic only.
- The exact runner/session interruption cause is not proven by these changes;
  the patch only makes future partial evidence easier to classify.
- BudgetFlow task-level used only T2 in the completed rows. That is plausible
  for this diagnostic slice, but full Claim 2 mechanism diagnosis still needs a
  completed policy comparison.

## Next Recommended Slice

Before any new paid run, run the no-paid checker on the intended output stem
and confirm partial-run, scoreable-untrusted-harness, provider, parser, budget
mode, value source, and cost source warnings are clean or consciously accepted.

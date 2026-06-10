# 5x14 Final Pre-Paid Audit -- 2026-06-10

## Objective

Do one last independent audit before the paid 5x14 rerun, focusing on bugs that
could contaminate evidence rather than adding new routing mechanisms.

## Verdict

**GO after Worker review.** I found and fixed several evidence-chain bugs in the
parser/retry path. Focused no-paid checks pass. I still want Walker to review
this slice because these changes sit directly on the runtime path used by paid
experiments.

## Findings Fixed

| Finding | Risk | Fix |
|---|---|---|
| Real `mini-swe-agent` `FormatError` payload was read from the wrong place | Parser reason could be misclassified, so `found_2_actions` / `empty_response` thresholds were not trustworthy | `_classify_format_reason()` now reads both `exc.args[0]` and `exc.messages[0]["extra"]` |
| Empty text response with `n_actions=0` was classified as `found_0_actions` | Empty provider/model response should use the tighter empty-response threshold | Empty text content now classifies as `empty_response` |
| Per-reason thresholds could use stale retry reason | A current `found_2_actions` error could accidentally inherit the prior empty-response limit | `_parse_actions()` now computes reason + limit from the current `FormatError` |
| Protocol retry was effectively run-level, despite docs saying one retry per turn | After the first parser error in a task, later turns would not get the intended bounded retry | Runtime now keeps per-turn retry state and run-level aggregate counters separately |
| Retry reservation used original prompt length | Hard budget reserve could under-estimate retry prompt cost | Retry reserve now estimates tokens from `retry_messages` |
| Retry provider exception could leave an active reservation | Budget ledger could remain polluted after retry failure | Retry exception path releases `_last_reservation_id` |
| Audit collapsed retry outcomes into one top-level boolean | Multiple retry turns in one task could be hidden in reports | Audit now prefers per-turn retry fields from `turn_traces` |
| Turn traces lacked retry state | Parser/protocol debugging required inference | `protocol_retry_*` fields are now emitted in turn traces |

## Runtime Semantics After Fix

- Every strategy still has hard budget kill.
- BudgetFlow stop-loss/stagnation guard remains enabled only for BudgetFlow
  mechanism strategies.
- Baselines should not receive BudgetFlow stop-loss.
- Parser/protocol recovery is bounded:
  - `found_2_actions`: stop after 4 consecutive format errors.
  - `found_0_actions`: stop after 3 consecutive format errors.
  - `empty_response`: stop after 3 consecutive format errors.
  - unknown/default: stop after 4 consecutive format errors.
- One in-turn correction retry is allowed per turn, not once per whole task.
- The exact-one-action protocol is still enforced; we do not silently choose the
  first action.

## Verification

```bash
PYTHONPATH=paper1/src:external/mini-swe-agent/src python -m pytest \
  paper1/tests/test_protocol_retry.py \
  paper1/tests/test_stall_guard.py \
  paper1/tests/test_trace_fields.py \
  paper1/tests/test_runner_exit_status.py \
  paper1/tests/test_run_observability_audit.py \
  paper1/tests/test_failure_classification.py \
  paper1/tests/test_compare_readiness.py -q
# 133 passed, 2 skipped

python -m py_compile \
  paper1/src/budgetflow/adapter/mini_swe_proxy.py \
  paper1/src/budgetflow/adapter/turn_trace.py \
  paper1/src/budgetflow/run_observability/audit.py \
  paper1/tests/test_protocol_retry.py

git -C paper1 diff --check
# clean
```

Also checked the historical 5x14 audit still flags the old run as
baseline-contaminated forensic evidence:

```bash
PYTHONPATH=paper1/src python -m budgetflow.run_observability.cli \
  --jsonl paper1/data/runs/compare_14x5-0.jsonl
```

The old run remains diagnostic only. Do not edit historical JSONL.

## Walker Review Checklist

| Check | Why |
|---|---|
| Confirm baseline strategies cannot enter `check_stagnation()` | Prevent another contaminated paid baseline |
| Confirm retry reservation is released on every retry exception path | Protect hard budget evidence |
| Confirm `FormatError` classification works against real mini-swe-agent exceptions | Avoid false parser thresholds |
| Confirm `protocol_retry_*` top-level fields and turn trace fields have clear semantics | Avoid misleading reports |
| Confirm paid command still uses turn traces | Parser/debug observability depends on them |

## Residual Risks

- These fixes are runtime-path changes, so Walker should review them before paid
  rerun.
- Full suite was not rerun by me in this final audit slice; Worker previously
  reported full suite green before these small fixes. Run full suite again after
  review if time permits.
- The retry mechanism is still intentionally conservative: one correction retry
  per turn. This reduces protocol noise but should not become a hidden advantage
  over baselines, since all strategies share the same parser/retry surface.

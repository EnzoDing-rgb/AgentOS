# Metrics Observability Cleanup Report — 2026-06-25

## Summary

Renamed report/observability layer metrics from legacy "Yield" terminology to
North Star v1 terminology. Runtime schemas, historical JSONL, and experiment
strategies are unchanged.

## Old → New Mapping

| Legacy Display Name | North Star Display Name | North Star Field |
|---|---|---|
| Yield | Total Resolved Value | `total_resolved_value` |
| Yield/$ | Resolved Value/$ | `total_resolved_value_per_dollar` |
| Yield/total$ | Resolved Value/total$ | (supplementary diagnostic) |
| Yield/score$ | Resolved Value/score$ | (supplementary diagnostic) |
| yield/$ | ResVal/$ | (frontier diagnostic) |
| yield= | total_resolved_value= | (recost CLI) |
| yield/$= | resolved_value/$= | (recost CLI) |

## North Star Metric Set (v1)

Six standardized fields added to summary/audit dicts:

1. `resolved_count` — tasks whose patch satisfies verifier
2. `resolved_rate` — resolved_count / total_tasks
3. `total_spend` — total model spend (includes abort cost)
4. `cost_per_resolved_task` — total_spend / resolved_count
5. `total_resolved_value` — sum(pre-registered task value for resolved tasks)
6. `total_resolved_value_per_dollar` — total_resolved_value / total_spend

## Files Changed

### New

- `paper1/src/budgetflow/metrics_reporting.py` — Central helper: field constants,
  display headers, legacy alias map, `resolved_field()`, `build_standard_metrics()`,
  `enrich_strategy_summary()`, `display_name()`

### Modified — Source

- `paper1/src/budgetflow/value_efficiency.py` — `summary_for_strategy()`: added
  5 North Star fields alongside legacy aliases. Docstring updated.
- `paper1/src/budgetflow/run_observability/audit.py` — 4 edit sites:
  `strategy_metrics` dict, `_mechanism_isolation_delta`, `_task_set_metrics`,
  per-task comparison dict. All add North Star fields alongside legacy.
- `paper1/src/budgetflow/run_observability/report.py` — 4 display sections updated:
  PAPER METRICS, TASK SET METRICS, FRONTIER DIAGNOSTICS, MECHANISM ISOLATION DELTA.
  Column headers use North Star names; data reads try North Star field first with
  legacy fallback.
- `paper1/src/budgetflow/experiments/compare_summary.py` — VALUE SUMMARY section:
  "Yield" → "Total Resolved Value", "Yield/$" → "Resolved Value/$".
  `_strategy_pass_rate()` → `_strategy_resolved_rate()`.
- `paper1/src/budgetflow/recost.py` — `run_sensitivity()` output: added
  `total_resolved_value`, `total_resolved_value_per_dollar`, `resolved_rate`
  alongside legacy. CLI display updated. Default ranking metric updated.

### Modified — Tests

- `tests/test_value_efficiency.py` — Added North Star assertions alongside legacy.
- `tests/test_run_observability_audit.py` — Added North Star assertions;
  display assertions check "Total Resolved Value", "Resolved Value/total$",
  "Resolved Value/score$" instead of "Yield", "Yield/total$", "Yield/score$".
- `tests/test_compare_record_schema.py` — Display assertions check
  "Total Resolved Value", "Resolved Value/$" instead of "Yield", "Yield/$".

## Not Changed

- Runtime record schema (`enrich_record()` keeps `yield_per_dollar` as field name)
- Historical JSONL artifacts
- Experiment strategies / routing logic
- Budget Compiler, CostSource, ValueSource
- `marginal_yield_per_dollar` — distinct routing concept, not renamed

## Formula Preservation

- `total_resolved_value` = `yield_score` (same formula)
- `total_resolved_value_per_dollar` = total_resolved_value / total_spend (includes abort cost)
- `yield_per_dollar` = resolved_value / total_cost (scoreable cost only, kept as legacy diagnostic)
- Both remain in summary dicts; North Star is authoritative for reports.

## Verification

```
PYTHONPATH=src python -m pytest tests/test_value_efficiency.py \
  tests/test_run_observability_audit.py \
  tests/test_compare_record_schema.py \
  tests/test_recost.py -v
# 90 passed
```

## Residual Risks

- Report column widths widened for longer North Star names — verify visual fit
  on narrow terminals.
- `recost.py` ranking default changed to `total_resolved_value_per_dollar`;
  callers passing explicit metric name are unaffected.

"""Compatibility entrypoint for BudgetFlow run-observability checks.

Implementation lives in ``budgetflow.run_observability`` so schema, audit,
reporting, and CLI concerns stay separate.
"""

from __future__ import annotations

from budgetflow.run_observability.audit import (
    _count_tier,
    _has_invoice_accurate_cost,
    _pick_tier,
    build_compact_audit,
)
from budgetflow.run_observability.checker import check_jsonl
from budgetflow.run_observability.checks import (
    _check_cross_series_duplicates,
    _check_partial_run,
    _check_policy_parallel,
    _check_shared_cap_starvation,
    _check_value_profile_fallback,
    _is_per_task_budget_series,
)
from budgetflow.run_observability.cli import main
from budgetflow.run_observability.heartbeat import _pid_is_alive, _rows_stuck
from budgetflow.run_observability.report import format_compact_audit
from budgetflow.run_observability.schema import (
    OPTIONAL_BUT_DESIRED,
    REQUIRED_FIELDS,
    _check_desired_fields,
    _check_duplicates,
    _check_elapsed_sanity,
    _check_harness_trust,
    _check_missing_fields,
    _check_observability_schema,
    _check_pass_evidence,
    _check_trace_coverage,
    _routing_memory_source,
    _routing_memory_used,
    _routing_prior_task_seen,
)

__all__ = [
    "OPTIONAL_BUT_DESIRED",
    "REQUIRED_FIELDS",
    "_check_cross_series_duplicates",
    "_check_desired_fields",
    "_check_duplicates",
    "_check_elapsed_sanity",
    "_check_harness_trust",
    "_check_missing_fields",
    "_check_observability_schema",
    "_check_partial_run",
    "_check_pass_evidence",
    "_check_policy_parallel",
    "_check_shared_cap_starvation",
    "_check_trace_coverage",
    "_check_value_profile_fallback",
    "_count_tier",
    "_has_invoice_accurate_cost",
    "_is_per_task_budget_series",
    "_pick_tier",
    "_pid_is_alive",
    "_routing_memory_source",
    "_routing_memory_used",
    "_routing_prior_task_seen",
    "_rows_stuck",
    "build_compact_audit",
    "check_jsonl",
    "format_compact_audit",
    "main",
]

if __name__ == "__main__":
    main()

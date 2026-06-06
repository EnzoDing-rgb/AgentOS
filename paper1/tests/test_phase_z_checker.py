"""Phase Z checker regression tests — automated warnings for common experiment issues."""

import json
import tempfile
from pathlib import Path

from budgetflow.check_run_observability import (
    build_compact_audit,
    _check_cross_series_duplicates,
    _check_observability_schema,
    _check_partial_run,
    _check_shared_cap_starvation,
    _check_value_profile_fallback,
    _check_policy_parallel,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row(instance_id, strategy, run_series="test_series", **kwargs):
    return {
        "instance_id": instance_id,
        "strategy": strategy,
        "run_series": run_series,
        **kwargs,
    }


# ── (a) Cross-series duplicate inflation ─────────────────────────────────────

class TestCrossSeriesDuplicates:
    def test_clean_when_no_cross_series(self):
        rows = [
            _row("a", "bfv", "series_1"),
            _row("b", "bfv", "series_1"),
        ]
        assert _check_cross_series_duplicates(rows) == []

    def test_flags_same_pair_in_two_series(self):
        rows = [
            _row("a", "bfv", "series_1"),
            _row("a", "bfv", "series_2"),
        ]
        issues = _check_cross_series_duplicates(rows)
        assert len(issues) == 1
        assert "CROSS_SERIES_DUPLICATE" in issues[0]
        assert "series_1" in issues[0] and "series_2" in issues[0]

    def test_flags_multiple_pairs(self):
        rows = [
            _row("a", "bfv", "s1"),
            _row("a", "bfv", "s2"),
            _row("b", "bfc", "s1"),
            _row("b", "bfc", "s3"),
        ]
        issues = _check_cross_series_duplicates(rows)
        assert len(issues) == 2


# ── (b) Partial run detection ────────────────────────────────────────────────

class TestPartialRun:
    def test_clean_when_all_tasks_run(self):
        rows = [
            _row("t1", "bfv", task_order_index=1),
            _row("t2", "bfv", task_order_index=2),
            _row("t3", "bfv", task_order_index=3),
        ]
        assert _check_partial_run(rows) == []

    def test_flags_when_gap_in_indexes(self):
        rows = [
            _row("t1", "bfv", task_order_index=1),
            _row("t1", "bfc", task_order_index=1),
            _row("t3", "bfv", task_order_index=3),
            _row("t3", "bfc", task_order_index=3),
        ]
        issues = _check_partial_run(rows)
        assert len(issues) >= 1
        assert "PARTIAL_RUN" in issues[0]
        assert "3 planned" in issues[0] or "planned" in issues[0].lower()

    def test_heartbeat_cross_reference(self):
        rows = [
            _row("t1", "bfv", "partial_series", task_order_index=1),
            _row("t1", "bfc", "partial_series", task_order_index=1),
        ]
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td)
            hb = {"total_expected": 6, "status": "completed",
                  "rows_done": 2, "started_at": 1, "updated_at": 1, "current_pid": 0}
            (runs_dir / "partial_series.heartbeat.json").write_text(json.dumps(hb))
            issues = _check_partial_run(rows, runs_dir)
            # 6 expected rows / 2 strategies = 3 planned tasks, only 1 executed
            assert any("PARTIAL_RUN" in i and "heartbeat" in i for i in issues), issues


# ── (c) Shared-cap starvation ────────────────────────────────────────────────

class TestSharedCapStarvation:
    def test_clean_when_no_starvation(self):
        rows = [
            _row("t1", "bfv", exit_reason="success"),
            _row("t2", "bfv", exit_reason="repair_fail"),
        ]
        assert _check_shared_cap_starvation(rows) == []

    def test_flags_budget_exhausted_rows(self):
        rows = [
            _row("t1", "bfv", exit_reason="budget_exhausted"),
        ]
        issues = _check_shared_cap_starvation(rows)
        assert len(issues) == 1
        assert "SHARED_CAP_STARVATION" in issues[0]

    def test_ignores_other_exit_reasons(self):
        rows = [
            _row("t1", "bfv", exit_reason="protocol_fail"),
            _row("t2", "bfv", exit_reason="repair_fail"),
            _row("t3", "bfv", exit_reason="budget_exhausted_after_progress"),
        ]
        issues = _check_shared_cap_starvation(rows)
        # both "budget_exhausted" and "budget_exhausted_after_progress" match
        assert len(issues) == 1
        assert "t3/bfv" in issues[0]

    def test_per_task_cap_budget_exhaustion_is_not_shared_starvation(self):
        rows = [
            _row(
                "t1",
                "bfv",
                exit_reason="budget_exhausted",
                budget_mode="per_task_cap",
                per_task_cap=0.5,
            ),
            _row(
                "t2",
                "bfv",
                exit_reason="submitted",
                budget_mode="per_task_cap",
                per_task_cap=0.5,
            ),
        ]
        assert _check_shared_cap_starvation(rows) == []

    def test_infers_per_task_cap_from_repeated_batch_spent_resets(self):
        rows = [
            _row("t1", "bfv", exit_reason="budget_exhausted", batch_budget_cap=0.5, batch_spent=0.5),
            _row("t2", "bfv", exit_reason="budget_exhausted", batch_budget_cap=0.5, batch_spent=0.5),
        ]
        assert _check_shared_cap_starvation(rows) == []


# ── (d) Value profile fallback detection ─────────────────────────────────────

class TestValueProfileFallback:
    def test_clean_when_values_vary(self):
        rows = [
            _row("t1", "bfv", task_value=0.1, value_source="value_matrix"),
            _row("t2", "bfv", task_value=0.9, value_source="value_matrix"),
        ]
        assert _check_value_profile_fallback(rows) == []

    def test_flags_all_equal_values(self):
        rows = [
            _row("t1", "bfv", task_value=0.5, value_source="value_matrix"),
            _row("t2", "bfc", task_value=0.5, value_source="value_matrix"),
            _row("t3", "bo", task_value=0.5, value_source="value_matrix"),
        ]
        issues = _check_value_profile_fallback(rows)
        assert len(issues) >= 1
        assert "VALUE_FALLBACK" in issues[0]
        assert "0.5" in issues[0]

    def test_flags_equal_fallback_source(self):
        rows = [
            _row("t1", "bfv", task_value=1.0, value_source="fallback_equal"),
        ]
        issues = _check_value_profile_fallback(rows)
        assert len(issues) >= 1
        assert "VALUE_FALLBACK" in issues[0]

    def test_no_value_field_at_all(self):
        rows = [
            _row("t1", "bfv"),
        ]
        issues = _check_value_profile_fallback(rows)
        assert len(issues) >= 1
        assert "no task_value" in issues[0]


# ── (e) Policy-parallel detection ────────────────────────────────────────────

class TestPolicyParallel:
    def test_clean_when_overlapping(self):
        # All strategies start at same time → parallel
        t = 1000.0
        rows = [
            _row("t1", "bfv", row_started_at=t),
            _row("t1", "bfc", row_started_at=t),
            _row("t1", "bo", row_started_at=t),
        ]
        assert _check_policy_parallel(rows) == []


class TestCompactAuditRecomputesVerdict:
    def test_stale_billing_guard_verdict_is_recomputed(self):
        rows = [
            _row(
                "sympy__sympy-16988",
                "budgetflow_value_aware_tight",
                harness_resolved=False,
                exit_status="UpstreamExit",
                exit_reason="billing_guard backend=tier2 sample=litellm.BadRequestError",
                patch_extracted=False,
                agent_gold_edited=False,
                detail="no model patch extracted",
                turn_trace_count=1,
                turn_traces=[{"error_type": "BudgetFlowUpstreamError"}],
                failure_class="infra_fail",
                verdict_axis="protocol_fail",
                failure_owner="protocol",
                failure_subtype="extraction_protocol_fail",
            )
        ]

        audit = build_compact_audit(rows)

        assert audit["verdict_axes"] == {"infra_fail": 1}
        assert audit["verdict_owners"] == {"infra": 1}
        assert audit["fail_subtypes"] == {"provider_or_parser_error": 1}
        assert audit["stored_verdict_mismatches"] == 1

    def test_observability_schema_flags_missing_turns_alias_and_budget_mode(self):
        rows = [
            _row(
                "sympy__sympy-16988",
                "budgetflow_value_aware_tight",
                llm_turns=9,
                turns=None,
                harness_resolved=True,
                resolved=None,
                batch_budget_cap=0.5,
            )
        ]

        issues = _check_observability_schema(rows)

        assert any("TURN_ALIAS_MISMATCH" in issue for issue in issues)
        assert any("RESOLVED_ALIAS_MISMATCH" in issue for issue in issues)
        assert any("BUDGET_MODE_MISSING" in issue for issue in issues)

    def test_flags_sequential_strategies(self):
        # bfv runs first (0-100), bfc runs later (200-300) → sequential
        rows = [
            _row("t1", "bfv", row_started_at=0.0),
            _row("t2", "bfv", row_started_at=1.0),
            _row("t3", "bfv", row_started_at=2.0),
            _row("t1", "bfc", row_started_at=200.0),
            _row("t2", "bfc", row_started_at=201.0),
            _row("t3", "bfc", row_started_at=202.0),
        ]
        issues = _check_policy_parallel(rows)
        assert len(issues) >= 1
        assert "SEQUENTIAL_POLICY" in issues[0]

    def test_single_strategy_no_false_positive(self):
        rows = [
            _row("t1", "bfv", row_started_at=100.0),
            _row("t2", "bfv", row_started_at=200.0),
        ]
        assert _check_policy_parallel(rows) == []

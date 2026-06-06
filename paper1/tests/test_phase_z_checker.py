"""Phase Z checker regression tests — automated warnings for common experiment issues."""

import json
import tempfile
from pathlib import Path

from budgetflow.check_run_observability import (
    _check_cross_series_duplicates,
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

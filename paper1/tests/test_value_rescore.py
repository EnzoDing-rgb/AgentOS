"""Tests for budgetflow.value_rescore — value-aware offline rescore."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from budgetflow.value_rescore import (
    PROFILES,
    TaskRow,
    compute_results,
    equal_value,
    load_rows,
    make_custom_profile,
    _heuristic_value,
    _DIFFICULTY_COEFF,
)


# ── Value profile tests ──────────────────────────────────────────────────────


class TestEqualProfile:
    def test_all_tasks_value_one(self):
        assert equal_value("any-task-id") == 1.0
        assert equal_value("sympy__sympy-16988") == 1.0

    def test_profile_in_registry(self):
        assert "equal" in PROFILES
        assert PROFILES["equal"]("x") == 1.0


class TestHeuristicProfile:
    def test_known_task_returns_difficulty(self):
        val = _heuristic_value("sympy__sympy-16988")
        assert val == 6.58

    def test_django_boost(self):
        raw = _DIFFICULTY_COEFF["django__django-10924"]
        val = _heuristic_value("django__django-10924")
        assert val == round(raw * 1.1, 4)

    def test_unknown_task_defaults_to_one(self):
        assert _heuristic_value("pypi__some-package") == 1.0

    def test_profile_in_registry(self):
        assert "heuristic" in PROFILES
        assert PROFILES["heuristic"]("sympy__sympy-20212") == 1.0


class TestCustomProfile:
    def test_explicit_mapping(self):
        fn = make_custom_profile({"a": 5.0, "b": 0.5})
        assert fn("a") == 5.0
        assert fn("b") == 0.5

    def test_unknown_defaults_to_one(self):
        fn = make_custom_profile({"only-this": 3.0})
        assert fn("not-in-map") == 1.0


# ── Data loading tests ───────────────────────────────────────────────────────


class TestLoadRows:
    def _write_jsonl(self, lines: list[dict]) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        for obj in lines:
            tmp.write(json.dumps(obj) + "\n")
        tmp.close()
        return Path(tmp.name)

    def test_basic_load(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": True,
             "total_cost": 0.5, "exit_reason": "submitted", "llm_turns": 10,
             "budget_tier": "tight", "backend_picks": ["tier2"]},
        ])
        rows = load_rows(p)
        assert len(rows) == 1
        assert rows[0].instance_id == "a"
        assert rows[0].harness_resolved is True
        assert rows[0].total_cost == 0.5

    def test_missing_cost_defaults_to_zero(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": False,
             "exit_reason": "err", "llm_turns": 0}
        ])
        rows = load_rows(p)
        assert rows[0].total_cost == 0.0

    def test_none_cost_defaults_to_zero(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": False,
             "total_cost": None, "exit_reason": "err", "llm_turns": 0}
        ])
        rows = load_rows(p)
        assert rows[0].total_cost == 0.0

    def test_none_resolved_defaults_to_false(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": None,
             "total_cost": 0.1, "exit_reason": "err", "llm_turns": 0}
        ])
        rows = load_rows(p)
        assert rows[0].harness_resolved is False

    def test_missing_exit_reason_defaults_to_unknown(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": True,
             "total_cost": 0.1, "llm_turns": 1}
        ])
        rows = load_rows(p)
        assert rows[0].exit_reason == "unknown"

    def test_skips_invalid_json(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": True,
             "total_cost": 0.1, "llm_turns": 1},
        ])
        # Append bad line
        with open(p, "a") as f:
            f.write("not valid json\n")
        rows = load_rows(p)
        assert len(rows) == 1  # bad line skipped

    def test_task_cost_fallback(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": True,
             "task_cost": 0.33, "exit_reason": "ok", "llm_turns": 2}
        ])
        rows = load_rows(p)
        assert rows[0].total_cost == 0.33

    def test_multiple_rows(self):
        p = self._write_jsonl([
            {"instance_id": "a", "strategy": "s1", "harness_resolved": True,
             "total_cost": 0.1, "exit_reason": "ok", "llm_turns": 1},
            {"instance_id": "b", "strategy": "s2", "harness_resolved": False,
             "total_cost": 0.2, "exit_reason": "err", "llm_turns": 2},
        ])
        rows = load_rows(p)
        assert len(rows) == 2


# ── Metric aggregation tests ─────────────────────────────────────────────────


class TestComputeResults:
    def _make_rows(self) -> list[TaskRow]:
        return [
            TaskRow("task-a", "strat-x", True, 0.10, "submitted", 5, "tight", ["tier2"], {}),
            TaskRow("task-a", "strat-y", True, 0.20, "submitted", 8, "tight", ["tier2"], {}),
            TaskRow("task-b", "strat-x", False, 0.30, "budget_exhausted", 12, "tight", ["tier3"], {}),
            TaskRow("task-b", "strat-y", False, 0.15, "submitted", 6, "tight", ["tier3"], {}),
        ]

    def test_equal_value_aggregation(self):
        results = compute_results(self._make_rows(), equal_value)
        sx = results["strat-x"]
        sy = results["strat-y"]

        assert sx.total_count == 2
        assert sx.resolved_count == 1
        assert sx.total_cost == 0.40
        assert sx.resolved_value == 1.0
        assert sx.total_value == 2.0

        assert sy.total_count == 2
        assert sy.resolved_count == 1
        assert sy.total_cost == 0.35
        assert sy.resolved_value == 1.0

    def test_heuristic_value_aggregation(self):
        results = compute_results(self._make_rows(), _heuristic_value)
        sx = results["strat-x"]
        assert sx.resolved_value > 0  # task-a resolved
        assert sx.total_value > sx.resolved_value

    def test_cost_per_resolved(self):
        results = compute_results(self._make_rows(), equal_value)
        assert results["strat-x"].cost_per_resolved == 0.40  # 0.40 / 1

    def test_resolved_rate(self):
        results = compute_results(self._make_rows(), equal_value)
        assert results["strat-x"].resolved_rate == 0.5
        assert results["strat-y"].resolved_rate == 0.5

    def test_resolved_value_per_dollar(self):
        results = compute_results(self._make_rows(), equal_value)
        assert results["strat-x"].resolved_value_per_dollar == 1.0 / 0.40
        assert results["strat-y"].resolved_value_per_dollar == 1.0 / 0.35

    def test_budget_fail_detection(self):
        results = compute_results(self._make_rows(), equal_value)
        # strat-x task-b has "budget_exhausted"
        assert results["strat-x"].budget_fail_count == 1
        assert results["strat-y"].budget_fail_count == 0

    def test_value_weighted_budget_fail(self):
        results = compute_results(self._make_rows(), equal_value)
        # Only strat-x task-b is budget_fail, value=1.0
        assert results["strat-x"].value_weighted_budget_fail == 1.0
        assert results["strat-y"].value_weighted_budget_fail == 0.0

    def test_per_task_rows_included(self):
        results = compute_results(self._make_rows(), equal_value)
        assert len(results["strat-x"].per_task_rows) == 2
        assert results["strat-x"].per_task_rows[0]["instance_id"] == "task-a"
        assert results["strat-x"].per_task_rows[0]["value"] == 1.0

    def test_infinite_cost_per_resolved_when_zero_resolved(self):
        rows = [TaskRow("t", "s", False, 0.10, "fail", 1, "tight", [], {})]
        results = compute_results(rows, equal_value)
        assert results["s"].cost_per_resolved == float("inf")

    def test_single_row_empty_input(self):
        results = compute_results([], equal_value)
        assert len(results) == 0


# ── Real-data fixture tests ──────────────────────────────────────────────────


class TestRealDataFixtures:
    """Smoke tests against 031 sample data."""

    @pytest.fixture
    def sample_path(self):
        p = Path("/root/.dev/AgentOS/paper1/data/runs/postfix_031_loo_5x2.jsonl")
        if not p.is_file():
            pytest.skip("031 JSONL not available")
        return p

    def test_load_031_rows(self, sample_path):
        rows = load_rows(sample_path)
        assert len(rows) == 10
        strategies = {r.strategy for r in rows}
        assert strategies == {"budget_only_tight", "budgetflow_full_tight"}
        for r in rows:
            assert r.instance_id
            assert r.total_cost >= 0
            assert isinstance(r.harness_resolved, bool)

    def test_equal_profile_reproduces_031(self, sample_path):
        """Equal-value re-score should match 031 report: both 4/5, BO cheaper."""
        rows = load_rows(sample_path)
        results = compute_results(rows, equal_value)
        bo = results["budget_only_tight"]
        bf = results["budgetflow_full_tight"]
        assert bo.resolved_count == 4
        assert bf.resolved_count == 4
        assert bo.total_cost < bf.total_cost

    def test_heuristic_profile_on_031(self, sample_path):
        rows = load_rows(sample_path)
        results = compute_results(rows, _heuristic_value)
        bo = results["budget_only_tight"]
        bf = results["budgetflow_full_tight"]
        # Both resolve same tasks, so resolved_value should be equal
        assert bo.resolved_value == pytest.approx(bf.resolved_value, abs=0.01)
        # BO should have higher val/$ (cheaper for same value)
        assert bo.resolved_value_per_dollar > bf.resolved_value_per_dollar

    def test_value_weighted_budget_fail_031(self, sample_path):
        rows = load_rows(sample_path)
        results = compute_results(rows, equal_value)
        # 031 has budget_exhausted tasks
        for sr in results.values():
            if sr.budget_fail_count > 0:
                assert sr.value_weighted_budget_fail > 0


# ── Profile swap test ────────────────────────────────────────────────────────


class TestProfileSwap:
    """Verify pluggable interface: any Callable[[str], float] works."""

    def test_custom_function_direct(self):
        rows = [TaskRow("a", "s", True, 0.10, "ok", 1, "tight", [], {})]
        results = compute_results(rows, lambda iid: 42.0)
        assert results["s"].resolved_value == 42.0

    def test_custom_profile_via_make(self):
        mapping = {"a": 7.0, "b": 3.0}
        fn = make_custom_profile(mapping)
        rows = [
            TaskRow("a", "s", True, 0.10, "ok", 1, "tight", [], {}),
            TaskRow("b", "s", False, 0.20, "err", 2, "tight", [], {}),
        ]
        results = compute_results(rows, fn)
        assert results["s"].resolved_value == 7.0
        assert results["s"].total_value == 10.0  # 7 + 3

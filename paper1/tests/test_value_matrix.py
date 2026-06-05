"""Tests for budgetflow.value_matrix — Value Matrix and Progress Calibration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from budgetflow.value_matrix import (
    PROFILES,
    TaskRecord,
    build_value_matrix,
    calibrate_progress_table,
    make_custom_profile,
    profile_combined,
    profile_difficulty,
    profile_equal,
    profile_solve_rarity,
    scan_task_universe,
    sensitivity_variants,
)


# ── Test helpers ──────────────────────────────────────────────────────────────


def _make_rec(
    iid="a", total=4, resolved=3, cost=0.2,
    strategies=None, strategies_resolved=None,
) -> TaskRecord:
    rec = TaskRecord(instance_id=iid, repo="test/test")
    rec.total_rows = total
    rec.resolved_rows = resolved
    rec.total_cost = cost
    rec.strategies_seen = strategies if strategies is not None else {"s1", "s2"}
    rec.strategies_resolved = strategies_resolved if strategies_resolved is not None else {"s1", "s2"}
    return rec


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ── Profile tests ─────────────────────────────────────────────────────────────


class TestEqualProfile:
    def test_always_one(self):
        assert profile_equal("any", _make_rec()) == 1.0
        assert profile_equal("sympy-16988", _make_rec(cost=5.0)) == 1.0

    def test_in_registry(self):
        assert "equal" in PROFILES


class TestDifficultyProfile:
    def test_resolved_task_no_penalty(self):
        # total=1 so avg_cost = total_cost = 0.1
        rec = _make_rec(total=1, resolved=1, cost=0.1)
        assert profile_difficulty(rec) == 0.1

    def test_partially_resolved_has_penalty(self):
        # avg_cost = 0.1/4 = 0.025; rate=0.5; penalty = 1 + 0.5*0.5 = 1.25
        # value = 0.025 * 1.25 = 0.03125
        rec = _make_rec(total=4, resolved=2, cost=0.1)
        assert profile_difficulty(rec) == pytest.approx(0.03125)

    def test_never_resolved_max_penalty(self):
        # total=1 so avg_cost = 0.1; rate=0; penalty = 1 + 0.5*1.0 = 1.5
        # value = 0.1 * 1.5 = 0.15
        rec = _make_rec(total=1, resolved=0, cost=0.1)
        assert profile_difficulty(rec) == pytest.approx(0.15)

    def test_floor_at_001(self):
        rec = _make_rec(total=4, resolved=4, cost=0.0)
        assert profile_difficulty(rec) == 0.01

    def test_in_registry(self):
        assert "difficulty" in PROFILES


class TestSolveRarityProfile:
    def test_all_solved_value_one(self):
        rec = _make_rec(strategies={"a", "b"}, strategies_resolved={"a", "b"})
        assert profile_solve_rarity(rec) == pytest.approx(1.0)

    def test_none_solved_value_five(self):
        rec = _make_rec(strategies={"a", "b"}, strategies_resolved=set())
        # rarity = 0/2 = 0 → 1 + 4*(1-0)^2 = 5.0
        assert profile_solve_rarity(rec) == pytest.approx(5.0)

    def test_half_solved(self):
        rec = _make_rec(strategies={"a", "b"}, strategies_resolved={"a"})
        # rarity = 0.5 → 1 + 4*(0.5)^2 = 1 + 4*0.25 = 2.0
        assert profile_solve_rarity(rec) == pytest.approx(2.0)

    def test_in_registry(self):
        assert "solve_rarity" in PROFILES


class TestCombinedProfile:
    def test_positive(self):
        rec = _make_rec(cost=1.0, total=2, resolved=1)
        v = profile_combined(rec)
        assert v > 1.0

    def test_monotonic_with_difficulty(self):
        """More difficult tasks should have higher combined value."""
        easy = _make_rec(iid="easy", cost=0.01, total=4, resolved=4,
                         strategies={"a"}, strategies_resolved={"a"})
        hard = _make_rec(iid="hard", cost=1.0, total=4, resolved=0,
                         strategies={"a"}, strategies_resolved=set())
        assert profile_combined(hard) > profile_combined(easy)

    def test_in_registry(self):
        assert "combined" in PROFILES


class TestCustomProfile:
    def test_explicit_mapping(self):
        fn = make_custom_profile({"a": 5.0, "b": 0.3})
        assert fn("a", _make_rec(iid="a")) == 5.0
        assert fn("b", _make_rec(iid="b")) == 0.3

    def test_unknown_default(self):
        fn = make_custom_profile({})
        assert fn("x", _make_rec(iid="x")) == 1.0


# ── No BF-specific leakage tests ─────────────────────────────────────────────


class TestNoBFLeakage:
    """All profiles must be computable without BF-specific signals."""

    def test_profiles_only_use_cross_strategy_stats(self):
        """Verify profiles don't need BF-specific fields."""
        rec = _make_rec()
        # All built-in profiles should work
        for pname, pfn in PROFILES.items():
            val = pfn(rec.instance_id, rec)
            assert isinstance(val, (int, float))
            assert val >= 0

    def test_difficulty_uses_cross_strategy_cost(self):
        """Difficulty is based on avg_cost across ALL strategies, not BF only."""
        rec = _make_rec(cost=1.0)  # cross-strategy avg_cost
        assert profile_difficulty(rec) > 0

    def test_solve_rarity_is_cross_strategy(self):
        """Solve rarity counts how many strategies solve, not just BF."""
        rec = _make_rec(strategies={"bo", "bf", "all_pro"}, strategies_resolved={"bo"})
        # rarity = 1/3 ≈ 0.33 → 1 + 4*(0.67)^2 ≈ 2.78
        val = profile_solve_rarity(rec)
        assert val > 1.0

    def test_bf_solving_does_not_boost_value(self):
        """A task where only BF solves it should get higher rarity value (fewer solvers),
        but value should not be computed from 'did BF solve' as a binary flag."""
        # BF-only solve
        rec = _make_rec(strategies={"bo", "bf"}, strategies_resolved={"bf"})
        val_bf_only = profile_solve_rarity(rec)
        # Everyone solves
        rec2 = _make_rec(strategies={"bo", "bf"}, strategies_resolved={"bo", "bf"})
        val_all = profile_solve_rarity(rec2)
        # BF-only should have higher rarity value (fewer solvers = rarer)
        # But this is cross-strategy, not BF-specific — any strategy that solo-solves
        # creates the same signal
        assert val_bf_only > val_all


# ── Sensitivity tests ────────────────────────────────────────────────────────


class TestSensitivityVariants:
    def test_produces_five_variants(self):
        variants = sensitivity_variants(_make_rec())
        expected_keys = {"cost_only", "rate_only", "cost_heavy", "rate_heavy", "difficulty_default"}
        assert set(variants.keys()) == expected_keys

    def test_all_values_positive(self):
        variants = sensitivity_variants(_make_rec(cost=0.1, total=4, resolved=4))
        for k, v in variants.items():
            assert v >= 0.0, f"{k} should be non-negative"

    def test_ordering_preserved_for_different_difficulties(self):
        easy = _make_rec(cost=0.01, total=4, resolved=4)
        hard = _make_rec(cost=1.0, total=4, resolved=0)
        easy_v = sensitivity_variants(easy)
        hard_v = sensitivity_variants(hard)
        # For cost-based variants, hard > easy
        assert hard_v["cost_only"] > easy_v["cost_only"]
        assert hard_v["cost_heavy"] > easy_v["cost_heavy"]
        # For rate-based variants, hard > easy
        assert hard_v["rate_only"] > easy_v["rate_only"]


# ── Determinism tests ─────────────────────────────────────────────────────────


class TestDeterminism:
    def test_profiles_deterministic(self):
        rec = _make_rec()
        for pname, pfn in PROFILES.items():
            v1 = pfn(rec.instance_id, rec)
            v2 = pfn(rec.instance_id, rec)
            assert v1 == v2, f"{pname} should be deterministic"

    def test_sensitivity_deterministic(self):
        rec = _make_rec()
        v1 = sensitivity_variants(rec)
        v2 = sensitivity_variants(rec)
        assert v1 == v2


# ── TaskRecord tests ──────────────────────────────────────────────────────────


class TestTaskRecord:
    def test_resolve_rate(self):
        rec = _make_rec(total=10, resolved=7)
        assert rec.resolve_rate == 0.7

    def test_resolve_rate_zero_rows(self):
        rec = _make_rec(total=0, resolved=0)
        assert rec.resolve_rate == 0.0

    def test_avg_cost(self):
        rec = _make_rec(total=5, cost=1.0)
        assert rec.avg_cost == 0.2

    def test_solve_rarity(self):
        rec = _make_rec(strategies={"a", "b", "c"}, strategies_resolved={"a"})
        assert rec.solve_rarity == pytest.approx(1.0 / 3.0)

    def test_solve_rarity_no_strategies(self):
        rec = _make_rec(strategies=set(), strategies_resolved=set())
        assert rec.solve_rarity == 0.0

    def test_repo_name(self):
        rec = TaskRecord(instance_id="sympy__sympy-14774", repo="sympy/sympy")
        assert rec.repo_name == "sympy"


# ── Build value matrix tests ──────────────────────────────────────────────────


class TestBuildValueMatrix:
    def test_empty_records(self):
        matrix = build_value_matrix({}, PROFILES)
        assert len(matrix["tasks"]) == 0

    def test_single_task_all_profiles(self):
        records = {"a": _make_rec(iid="a")}
        matrix = build_value_matrix(records, PROFILES)
        assert "a" in matrix["tasks"]
        t = matrix["tasks"]["a"]
        for pname in PROFILES:
            assert pname in t["values"]
            assert isinstance(t["values"][pname], (int, float))

    def test_rankings_present(self):
        records = {f"task_{i}": _make_rec(iid=f"task_{i}", cost=float(i)) for i in range(1, 4)}
        matrix = build_value_matrix(records, PROFILES)
        for pname in PROFILES:
            assert pname in matrix["rankings"]
            assert len(matrix["rankings"][pname]) == 3

    def test_rank_correlations_present(self):
        records = {f"task_{i}": _make_rec(iid=f"task_{i}", cost=float(i)) for i in range(1, 4)}
        matrix = build_value_matrix(records, PROFILES)
        assert "rank_correlations" in matrix
        for p1 in PROFILES:
            for p2 in PROFILES:
                assert matrix["rank_correlations"][p1][p2] is not None

    def test_sensitivity_per_task(self):
        records = {"a": _make_rec(iid="a")}
        matrix = build_value_matrix(records, PROFILES)
        t = matrix["tasks"]["a"]
        assert "sensitivity" in t
        assert len(t["sensitivity"]) == 5

    def test_meta_includes_profiles(self):
        records = {"a": _make_rec()}
        matrix = build_value_matrix(records, {"equal": PROFILES["equal"]})
        assert matrix["meta"]["profiles"] == ["equal"]
        assert matrix["meta"]["task_count"] == 1


# ── Scan task universe tests ──────────────────────────────────────────────────


class TestScanTaskUniverse:
    def test_basic_scan(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            _write_jsonl(data_dir / "test.jsonl", [
                {"instance_id": "a", "strategy": "s1", "harness_resolved": True,
                 "total_cost": 0.1, "task_cost": 0.0},
                {"instance_id": "b", "strategy": "s1", "harness_resolved": False,
                 "total_cost": 0.2, "task_cost": 0.0},
                {"instance_id": "a", "strategy": "s2", "harness_resolved": True,
                 "total_cost": 0.3, "task_cost": 0.0},
            ])
            records = scan_task_universe(data_dir)
            assert len(records) == 2
            assert records["a"].total_rows == 2
            assert records["a"].resolved_rows == 2
            assert records["a"].strategies_seen == {"s1", "s2"}
            assert records["b"].total_rows == 1
            assert records["b"].resolved_rows == 0

    def test_skips_auto_budget_files(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            _write_jsonl(data_dir / "auto_budget_memory.jsonl", [
                {"instance_id": "x", "strategy": "s", "harness_resolved": True,
                 "total_cost": 1.0},
            ])
            _write_jsonl(data_dir / "real.jsonl", [
                {"instance_id": "y", "strategy": "s", "harness_resolved": False,
                 "total_cost": 0.5},
            ])
            records = scan_task_universe(data_dir)
            assert "y" in records
            assert "x" not in records

    def test_handles_bad_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            bad_path = data_dir / "bad.jsonl"
            bad_path.write_text("not valid json\n")
            records = scan_task_universe(data_dir)
            assert len(records) == 0  # skipped silently

    def test_task_cost_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            _write_jsonl(data_dir / "test.jsonl", [
                {"instance_id": "a", "strategy": "s1", "harness_resolved": True,
                 "task_cost": 0.55},
            ])
            records = scan_task_universe(data_dir)
            assert records["a"].avg_cost == pytest.approx(0.55)

    def test_missing_task_id_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            _write_jsonl(data_dir / "test.jsonl", [
                {"strategy": "s", "harness_resolved": True, "total_cost": 0.1},
                {"instance_id": "valid", "strategy": "s", "harness_resolved": True,
                 "total_cost": 0.2},
            ])
            records = scan_task_universe(data_dir)
            assert len(records) == 1
            assert "valid" in records


# ── Progress calibration tests ────────────────────────────────────────────────


class TestProgressCalibration:
    def _make_trace_jsonl(self, data_dir: Path, rows: list[dict]) -> None:
        _write_jsonl(data_dir / "test_run.jsonl", rows)

    def test_basic_calibration(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            self._make_trace_jsonl(data_dir, [
                {"instance_id": "a", "strategy": "bf", "turn_traces": [
                    {"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": False,
                     "billable_cost": 0.01},
                    {"stage": "REPAIR", "backend_tier": 2, "has_progress": True,
                     "billable_cost": 0.005},
                    {"stage": "REPAIR", "backend_tier": 3, "has_progress": True,
                     "billable_cost": 0.02},
                ]},
            ])
            result = calibrate_progress_table(data_dir)
            assert result["meta"]["total_turns"] == 3
            assert result["meta"]["total_progress_turns"] == 2
            st = result["stage_tier"]
            assert st["LOCALIZATION_T2"]["turns"] == 1
            assert st["LOCALIZATION_T2"]["progress_rate"] == 0.0
            assert st["REPAIR_T2"]["turns"] == 1
            assert st["REPAIR_T2"]["progress_rate"] == 1.0
            assert st["REPAIR_T3"]["turns"] == 1
            assert st["REPAIR_T3"]["progress_rate"] == 1.0

    def test_low_sample_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            traces = []
            for i in range(5):  # Only 5 turns
                traces.append({
                    "instance_id": f"a{i}", "strategy": "bf",
                    "turn_traces": [
                        {"stage": "LOCALIZATION", "backend_tier": 2,
                         "has_progress": False, "billable_cost": 0.01}
                    ],
                })
            self._make_trace_jsonl(data_dir, traces)
            result = calibrate_progress_table(data_dir)
            st = result["stage_tier"]["LOCALIZATION_T2"]
            assert st["confidence"] == "INSUFFICIENT"

    def test_medium_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            traces = []
            for i in range(15):  # 15 turns = LOW
                traces.append({
                    "instance_id": f"a{i}", "strategy": "bf",
                    "turn_traces": [
                        {"stage": "LOCALIZATION", "backend_tier": 2,
                         "has_progress": True, "billable_cost": 0.01}
                    ],
                })
            self._make_trace_jsonl(data_dir, traces)
            result = calibrate_progress_table(data_dir)
            st = result["stage_tier"]["LOCALIZATION_T2"]
            assert st["confidence"] == "LOW"
            assert st["turns"] == 15

    def test_high_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            traces = []
            for i in range(100):
                traces.append({
                    "instance_id": f"a{i}", "strategy": "bf",
                    "turn_traces": [
                        {"stage": "REPAIR", "backend_tier": 2,
                         "has_progress": True, "billable_cost": 0.01}
                    ],
                })
            self._make_trace_jsonl(data_dir, traces)
            result = calibrate_progress_table(data_dir)
            st = result["stage_tier"]["REPAIR_T2"]
            assert st["confidence"] == "HIGH"

    def test_missing_traces_handled(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            self._make_trace_jsonl(data_dir, [
                {"instance_id": "a", "strategy": "bf", "turn_traces": []},
                {"instance_id": "b", "strategy": "bo"},  # no turn_traces key
            ])
            result = calibrate_progress_table(data_dir)
            assert result["meta"]["total_turns"] == 0  # nothing to aggregate

    def test_none_cost_handled(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            self._make_trace_jsonl(data_dir, [
                {"instance_id": "a", "strategy": "bf", "turn_traces": [
                    {"stage": "REPAIR", "backend_tier": 2, "has_progress": True,
                     "billable_cost": None, "actual_cost": None}
                ]},
            ])
            result = calibrate_progress_table(data_dir)
            st = result["stage_tier"]["REPAIR_T2"]
            assert st["avg_cost"] == 0.0

    def test_deltas_computed_when_data_sufficient(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            traces = []
            for i in range(10):
                traces.append({
                    "instance_id": f"a{i}", "strategy": "bf",
                    "turn_traces": [
                        {"stage": "REPAIR", "backend_tier": 2, "has_progress": True,
                         "billable_cost": 0.01},
                        {"stage": "REPAIR", "backend_tier": 3, "has_progress": False,
                         "billable_cost": 0.02},
                    ],
                })
            self._make_trace_jsonl(data_dir, traces)
            result = calibrate_progress_table(data_dir)
            # Both have >= 5 turns, so delta should be computed
            deltas = [d for d in result["deltas"] if d["stage"] == "REPAIR"]
            assert len(deltas) == 1
            assert "selected" in str(deltas[0]["caveat"]).lower()

    def test_cost_stats(self):
        """Verify median, p10, p90 cost stats."""
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            # Create 10 turns with different costs
            traces = []
            for i in range(10):
                traces.append({
                    "instance_id": f"a{i}", "strategy": "bf",
                    "turn_traces": [
                        {"stage": "REPAIR", "backend_tier": 2, "has_progress": True,
                         "billable_cost": float(i + 1) * 0.01}
                    ],
                })
            self._make_trace_jsonl(data_dir, traces)
            result = calibrate_progress_table(data_dir)
            st = result["stage_tier"]["REPAIR_T2"]
            assert st["median_cost"] > 0
            assert st["p10_cost"] >= 0
            assert st["p90_cost"] >= st["p10_cost"]
            # With 10 costs 0.01 to 0.10: p10 ≈ 0.01, p90 ≈ 0.09
            assert st["p10_cost"] <= st["median_cost"] <= st["p90_cost"]

    def test_strategies_tracked(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            self._make_trace_jsonl(data_dir, [
                {"instance_id": "a", "strategy": "budget_only_tight", "turn_traces": [
                    {"stage": "REPAIR", "backend_tier": 2, "has_progress": True,
                     "billable_cost": 0.01}
                ]},
                {"instance_id": "b", "strategy": "budgetflow_full_tight", "turn_traces": [
                    {"stage": "REPAIR", "backend_tier": 2, "has_progress": False,
                     "billable_cost": 0.01}
                ]},
            ])
            result = calibrate_progress_table(data_dir)
            st = result["stage_tier"]["REPAIR_T2"]
            assert "budget_only_tight" in st["strategies_seen"]
            assert "budgetflow_full_tight" in st["strategies_seen"]

    def test_skips_auto_budget(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            _write_jsonl(data_dir / "auto_budget_memory.jsonl", [
                {"instance_id": "x", "strategy": "s", "turn_traces": [
                    {"stage": "REPAIR", "backend_tier": 2, "has_progress": True,
                     "billable_cost": 0.01}
                ]},
            ])
            result = calibrate_progress_table(data_dir)
            assert result["meta"]["total_turns"] == 0


# ── Missing task handling tests ────────────────────────────────────────────────


class TestMissingTaskHandling:
    def test_unknown_task_in_matrix(self):
        """Tasks not in record set should be handled gracefully by profiles."""
        # custom profile with explicit mapping handles unknown tasks
        fn = make_custom_profile({"known": 5.0})
        assert fn("unknown", _make_rec(iid="unknown")) == 1.0

    def test_empty_universe_build(self):
        matrix = build_value_matrix({}, PROFILES)
        assert len(matrix["tasks"]) == 0
        assert matrix["meta"]["task_count"] == 0
        # Rankings should be empty
        for pname in PROFILES:
            assert len(matrix["rankings"][pname]) == 0

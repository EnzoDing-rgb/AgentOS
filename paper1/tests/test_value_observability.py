"""Tests for Phase R value observability (Task C)."""

import json
import tempfile
from pathlib import Path

import pytest

# Import the helper functions from run_mini_swe_compare
from budgetflow.run_mini_swe_compare import (
    _VALUE_LOOKUP,
    _VALUE_MATRIX_PATH,
    _VALUE_PROFILE,
    _enrich_record_with_value,
    _init_value_observability,
    _value_summary_for_strategy,
)


class TestEnrichRecord:
    def test_value_fields_present(self):
        _init_value_observability(value_profile="equal")
        record = _enrich_record_with_value({
            "instance_id": "test_task",
            "harness_resolved": True,
            "task_cost": 0.5,
            "total_cost": 0.5,
        })
        assert record["task_value_profile"] == "equal"
        assert record["task_value"] == 1.0
        assert record["resolved_value"] == 1.0
        assert record["value_source"] == "default_equal"
        assert record["value_matrix_artifact"] is None
        assert "resolved_value_per_dollar" in record

    def test_equal_profile_resolved_value_equals_resolved_count(self):
        _init_value_observability(value_profile="equal")
        r1 = _enrich_record_with_value({
            "instance_id": "a", "harness_resolved": True, "task_cost": 0.5,
        })
        r2 = _enrich_record_with_value({
            "instance_id": "b", "harness_resolved": False, "task_cost": 0.3,
        })
        assert r1["resolved_value"] == 1.0  # resolved, value=1
        assert r2["resolved_value"] == 0.0  # not resolved
        summary = _value_summary_for_strategy([r1, r2])
        assert summary["resolved_count"] == 1
        # Under equal profile, resolved_value == resolved_count
        assert summary["resolved_value"] == 1.0

    def test_non_equal_profile_reads_matrix(self):
        artifact = {
            "matrix": {
                "difficulty": {
                    "task_a": {"value": 2.0},
                    "task_b": {"value": 0.5},
                }
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            _init_value_observability(value_profile="difficulty", value_matrix_path=tmp)
            r = _enrich_record_with_value({
                "instance_id": "task_a", "harness_resolved": True, "task_cost": 0.5,
            })
            assert r["task_value_profile"] == "difficulty"
            assert r["task_value"] == 2.0
            assert r["resolved_value"] == 2.0  # resolved × value
            assert r["value_source"] == "value_matrix"
            assert r["value_matrix_artifact"] == tmp
        finally:
            Path(tmp).unlink()

    def test_missing_matrix_file_raises(self):
        # Phase X fail-fast: nonexistent matrix file raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            _init_value_observability(value_profile="difficulty", value_matrix_path="/nonexistent/path.json")

    def test_resolved_value_zero_when_not_resolved(self):
        _init_value_observability(value_profile="equal")
        r = _enrich_record_with_value({
            "instance_id": "x", "harness_resolved": False, "task_cost": 0.5,
        })
        assert r["resolved_value"] == 0.0

    def test_resolved_value_per_dollar_zero_cost_handled(self):
        _init_value_observability(value_profile="equal")
        r = _enrich_record_with_value({
            "instance_id": "x", "harness_resolved": True, "task_cost": 0.0,
        })
        assert r["resolved_value_per_dollar"] == 0.0


class TestValueSummary:
    def test_summary_aggregation(self):
        _init_value_observability(value_profile="equal")
        records = [
            {"instance_id": "a", "harness_resolved": True, "task_cost": 0.5,
             "task_value": 1.0, "resolved_value": 1.0},
            {"instance_id": "b", "harness_resolved": True, "task_cost": 0.3,
             "task_value": 1.0, "resolved_value": 1.0},
            {"instance_id": "c", "harness_resolved": False, "task_cost": 0.2,
             "task_value": 1.0, "resolved_value": 0.0},
        ]
        s = _value_summary_for_strategy(records)
        assert s["resolved_count"] == 2
        assert s["total_cost"] == 1.0
        assert s["resolved_value"] == 2.0
        assert s["total_task_value"] == 3.0
        assert s["resolved_value_per_dollar"] == 2.0  # 2 value / $1.00

    def test_summary_with_zero_cost_no_crash(self):
        _init_value_observability(value_profile="equal")
        s = _value_summary_for_strategy([])
        assert s["resolved_count"] == 0
        assert s["total_cost"] == 0.0
        assert s["resolved_value_per_dollar"] == 0.0


class TestCurrentSchema:
    """Tests for the current artifact schema (tasks[id].values[profile])."""

    def test_current_schema_loads_values(self):
        artifact = {
            "tasks": {
                "sympy__sympy-13480": {"values": {"difficulty": 0.0662, "equal": 1.0}},
                "sympy__sympy-13647": {"values": {"difficulty": 0.0970, "equal": 1.0}},
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            _init_value_observability(value_profile="difficulty", value_matrix_path=tmp)
            r = _enrich_record_with_value({
                "instance_id": "sympy__sympy-13480", "harness_resolved": True, "task_cost": 0.1,
            })
            assert r["task_value_profile"] == "difficulty"
            assert r["task_value"] == 0.0662
            assert r["resolved_value"] == 0.0662
            assert r["value_source"] == "value_matrix"
            assert r["value_matrix_artifact"] == tmp
        finally:
            Path(tmp).unlink()

    def test_missing_profile_fails_enrich(self):
        # Phase X fail-fast: profile not in matrix + non-equal → SystemExit on enrich
        artifact = {"tasks": {"x": {"values": {"difficulty": 0.5}}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            _init_value_observability(value_profile="nonexistent", value_matrix_path=tmp)
            with pytest.raises(SystemExit, match="FATAL"):
                _enrich_record_with_value({
                    "instance_id": "x", "harness_resolved": True, "task_cost": 0.1,
                })
        finally:
            Path(tmp).unlink()

    def test_backward_compat_legacy_schema(self):
        artifact = {"matrix": {"difficulty": {"task_a": {"value": 2.0}}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            _init_value_observability(value_profile="difficulty", value_matrix_path=tmp)
            r = _enrich_record_with_value({
                "instance_id": "task_a", "harness_resolved": True, "task_cost": 0.5,
            })
            assert r["task_value"] == 2.0
            assert r["value_source"] == "value_matrix"
        finally:
            Path(tmp).unlink()


class TestNoSecretLeak:
    def test_api_key_not_in_record_fields(self):
        _init_value_observability(value_profile="equal")
        r = _enrich_record_with_value({
            "instance_id": "x", "harness_resolved": True, "task_cost": 0.5,
        })
        record_str = json.dumps(r)
        # No API key patterns in the record
        assert "DASHSCOPE_API_KEY" not in record_str
        assert "AICODE007_API_KEY" not in record_str
        assert "sk-" not in record_str.lower()

    def test_value_matrix_path_not_leaking_key(self):
        # Phase X: must use valid matrix file (fail-fast prevents fake paths)
        artifact = {"tasks": {"x": {"values": {"equal": 1.0}}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            _init_value_observability(value_profile="equal", value_matrix_path=tmp)
            r = _enrich_record_with_value({
                "instance_id": "x", "harness_resolved": True, "task_cost": 0.5,
            })
            assert r["value_matrix_artifact"] == tmp
            assert "key" not in str(r["value_matrix_artifact"]).lower()
        finally:
            Path(tmp).unlink()

import json

import pytest

from budgetflow.value_efficiency import ValueEfficiencyContext


def test_equal_profile_is_t2_equal_value_ablation() -> None:
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="equal")

    record = ctx.enrich_record({
        "instance_id": "task-a",
        "routing": "budgetflow_conservative",
        "harness_resolved": True,
        "task_cost": 0.25,
    })

    assert record["value_objective"] == "t2_equal_value_ablation"
    assert record["task_value"] == 1.0
    assert record["resolved_value"] == 1.0
    assert record["resolved_value_per_dollar"] == 4.0
    assert record["task_value_multiplier"] is None


def test_non_equal_profile_is_t1_value_efficiency(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(json.dumps({
        "tasks": {
            "low": {"values": {"difficulty": 0.1}},
            "high": {"values": {"difficulty": 0.5}},
        }
    }))
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="difficulty", value_matrix_path=str(matrix))

    record = ctx.enrich_record({
        "instance_id": "high",
        "routing": "budgetflow_value_aware",
        "harness_resolved": True,
        "task_cost": 0.25,
    })

    assert record["value_objective"] == "t1_value_efficiency"
    assert record["task_value"] == 0.5
    assert record["resolved_value"] == 0.5
    assert record["resolved_value_per_dollar"] == 2.0
    assert record["task_value_multiplier"] == pytest.approx(1.6667, abs=0.0001)


def test_missing_non_equal_task_fails_fast(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(json.dumps({"tasks": {"x": {"values": {"difficulty": 0.1}}}}))
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="difficulty", value_matrix_path=str(matrix))

    with pytest.raises(SystemExit, match="FATAL"):
        ctx.enrich_record({
            "instance_id": "missing",
            "routing": "budgetflow_value_aware",
            "harness_resolved": True,
            "task_cost": 0.1,
        })

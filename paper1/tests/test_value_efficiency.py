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
    assert record["task_value_source_class"] == "default_equal"
    assert record["task_value"] == 1.0
    assert record["resolved_value"] == 1.0
    assert record["yield_per_dollar"] == 4.0
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
    assert record["task_value_source_class"] == "historical_cross_strategy"
    assert record["task_value"] == 0.5
    assert record["resolved_value"] == 0.5
    assert record["yield_per_dollar"] == 2.0
    assert record["task_value_multiplier"] == pytest.approx(1.6667, abs=0.0001)


def test_cold_start_profile_is_separate_t1_diagnostic(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(json.dumps({
        "tasks": {
            "task-a": {"values": {"cold_start_difficulty": 4.0}},
            "task-b": {"values": {"cold_start_difficulty": 2.0}},
        }
    }))
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="cold_start_difficulty", value_matrix_path=str(matrix))

    record = ctx.enrich_record({
        "instance_id": "task-a",
        "routing": "budgetflow_value_aware",
        "harness_resolved": True,
        "task_cost": 0.5,
    })

    assert record["value_objective"] == "t1_cold_start_value_diagnostic"
    assert record["task_value_source_class"] == "cold_start_ex_ante_metadata"
    assert record["resolved_value"] == 4.0


def test_summary_reports_primary_fixed_budget_value_metric() -> None:
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="difficulty")

    summary = ctx.summary_for_strategy([
        {"harness_resolved": True, "task_cost": 0.20, "resolved_value": 0.6, "task_value": 0.6},
        {"harness_resolved": False, "task_cost": 0.10, "resolved_value": 0.0, "task_value": 0.4},
    ])

    assert summary["resolved_value"] == 0.6
    assert summary["total_task_value"] == 1.0
    assert summary["yield_score"] == 0.6
    assert summary["yield_per_dollar"] == 2.0


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


def test_value_matrix_coverage_lists_missing_tasks_before_provider_preflight(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(json.dumps({"tasks": {"covered": {"values": {"difficulty": 0.1}}}}))
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="difficulty", value_matrix_path=str(matrix))

    assert ctx.missing_task_values(["covered", "missing"]) == ["missing"]

    equal_ctx = ValueEfficiencyContext()
    equal_ctx.init(value_profile="equal")
    assert equal_ctx.missing_task_values(["anything"]) == []

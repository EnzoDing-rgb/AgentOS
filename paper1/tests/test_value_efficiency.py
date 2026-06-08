import json

import pytest

from budgetflow.value_efficiency import ValueEfficiencyContext


def test_equal_profile_is_sanity_fallback_not_t1_evidence() -> None:
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="equal")

    record = ctx.enrich_record({
            "instance_id": "task-a",
            "routing": "budgetflow_conservative",
            "harness_resolved": True,
            "total_cost": 0.25,
    })

    assert record["value_objective"] == "t2_value_source_diagnostic"
    assert record["task_value_source_class"] == "equal_sanity"
    assert record["task_value_evidence_role"] == "sanity_fallback"
    assert record["task_value_primary_t1"] is False
    assert record["task_value"] == 1.0
    assert record["resolved_value"] == 1.0
    assert record["yield_per_dollar"] == 4.0
    assert record["task_value_multiplier"] is None


def test_non_equal_profile_without_explicit_source_is_value_matrix_diagnostic(tmp_path) -> None:
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
            "total_cost": 0.25,
    })

    assert record["value_objective"] == "t2_value_source_diagnostic"
    assert record["task_value_source_class"] == "value_matrix_diagnostic"
    assert record["task_value_evidence_role"] == "value_matrix_diagnostic"
    assert record["task_value_primary_t1"] is False
    assert record["task_value"] == 0.5
    assert record["resolved_value"] == 0.5
    assert record["yield_per_dollar"] == 2.0
    assert record["task_value_multiplier"] == pytest.approx(1.6667, abs=0.0001)


def test_pre_registered_manual_value_source_is_primary_t1_evidence(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(json.dumps({
        "tasks": {
            "low": {"values": {"difficulty": 0.1}},
            "high": {"values": {"difficulty": 0.5}},
        }
    }))
    ctx = ValueEfficiencyContext()
    ctx.init(
        value_profile="difficulty",
        value_matrix_path=str(matrix),
        value_source_kind="pre_registered_manual",
    )

    record = ctx.enrich_record({
            "instance_id": "high",
            "routing": "budgetflow_value_aware",
            "harness_resolved": True,
            "total_cost": 0.25,
    })

    assert record["value_objective"] == "t1_value_efficiency"
    assert record["task_value_source_class"] == "pre_registered_manual"
    assert record["task_value_evidence_role"] == "primary_t1"
    assert record["task_value_confidence"] == "manual"
    assert record["task_value_primary_t1"] is True


def test_bootstrap_profile_is_separate_diagnostic(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(json.dumps({
        "tasks": {
            "task-a": {"values": {"bootstrap_difficulty": 4.0}},
            "task-b": {"values": {"bootstrap_difficulty": 2.0}},
        }
    }))
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="bootstrap_difficulty", value_matrix_path=str(matrix))

    record = ctx.enrich_record({
            "instance_id": "task-a",
            "routing": "budgetflow_value_aware",
            "harness_resolved": True,
            "total_cost": 0.5,
    })

    assert record["value_objective"] == "t2_value_source_diagnostic"
    assert record["task_value_source_class"] == "bootstrap_heuristic"
    assert record["task_value_evidence_role"] == "heuristic_bootstrap"
    assert record["task_value_primary_t1"] is False
    assert record["resolved_value"] == 4.0


def test_matrix_metadata_can_mark_pre_registered_manual_value_source(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(json.dumps({
        "meta": {"value_source_kind": "pre_registered_manual"},
        "tasks": {
            "task-a": {"values": {"difficulty": 3.0}},
        }
    }))
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="difficulty", value_matrix_path=str(matrix))

    assert ctx.source_class == "pre_registered_manual"
    assert ctx.is_primary_value_evidence is True


def test_summary_reports_primary_fixed_budget_value_metric() -> None:
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="equal")

    summary = ctx.summary_for_strategy([
        {"harness_resolved": True, "total_cost": 0.20, "resolved_value": 3.0, "task_value": 3.0},
        {"harness_resolved": False, "total_cost": 0.10, "resolved_value": 0.0, "task_value": 1.0},
    ])

    assert summary["resolved_value"] == 3.0
    assert summary["total_task_value"] == 4.0
    assert summary["yield_score"] == 3.0
    assert summary["yield_coverage"] == 0.75
    assert summary["yield_per_dollar"] == 10.0
    assert summary["task_value_primary_t1"] is False


def test_abort_rows_are_reported_but_excluded_from_paper_metrics() -> None:
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="equal")

    pass_record = ctx.enrich_record({
        "instance_id": "task-a",
        "routing": "budgetflow_same_router",
        "harness_resolved": True,
        "score_status": "pass",
        "total_cost": 0.25,
    })
    abort_record = ctx.enrich_record({
        "instance_id": "task-b",
        "routing": "budgetflow_same_router",
        "harness_resolved": False,
        "score_status": "abort",
        "abort_reason": "provider_or_infra_error",
        "total_cost": 0.75,
    })

    summary = ctx.summary_for_strategy([pass_record, abort_record])

    assert abort_record["resolved_value"] == 0.0
    assert abort_record["scoreable_cost"] == 0.0
    assert summary["resolved_count"] == 1
    assert summary["true_fail_count"] == 0
    assert summary["abort_count"] == 1
    assert summary["total_cost"] == 0.25
    assert summary["abort_cost"] == 0.75
    assert summary["yield_per_dollar"] == 4.0


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
            "total_cost": 0.1,
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

from budgetflow.run_observability.audit import build_compact_audit
from budgetflow.observability import build_harness_trust
from budgetflow.run_observability.checks import _check_value_profile_fallback
from budgetflow.run_observability.report import format_compact_audit
import pytest


def test_compact_audit_preserves_generic_tier_counts() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_value_aware_tight",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.25,
            "llm_turns": 4,
            "turn_trace_count": 4,
            "backend_picks": ["tier2_balanced", "tier4", "tier5", "tier5"],
        }
    ])

    stats = audit["by_strategy"]["budgetflow_value_aware_tight"]

    assert stats["tier_turns"] == {2: 1, 4: 1, 5: 2}
    assert stats["t3_turns"] == 0


def test_compact_audit_reports_value_metrics() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_value_aware_tight",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.20,
            "llm_turns": 4,
            "turn_trace_count": 4,
            "backend_picks": ["tier2"],
            "task_value": 0.6,
            "resolved_value": 0.6,
            "task_value_profile": "difficulty",
            "value_objective": "t1_value_efficiency",
        },
        {
            "instance_id": "repo__task-b",
            "strategy": "budgetflow_value_aware_tight",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.10,
            "llm_turns": 2,
            "turn_trace_count": 2,
            "backend_picks": ["tier3"],
            "task_value": 0.4,
            "resolved_value": 0.0,
            "task_value_profile": "difficulty",
            "value_objective": "t1_value_efficiency",
        },
    ])

    stats = audit["by_strategy"]["budgetflow_value_aware_tight"]

    assert audit["value_profile"] == "difficulty"
    assert stats["normalized_verified_resolved_value"] == 0.6
    assert stats["resolved_value_per_dollar"] == pytest.approx(2.0)
    assert "T1 VALUE METRICS" in format_compact_audit(audit)


def test_compact_audit_reports_repo_memory_evidence_for_new_tasks() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__new-task",
            "strategy": "budgetflow_value_aware_tight",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.10,
            "llm_turns": 2,
            "turn_trace_count": 2,
            "backend_picks": ["tier2"],
            "policy_memory_enabled": True,
            "routing_prior_summary": {
                "task_seen": 0,
                "repo_evidence_weight": 25.25,
                "policy_memory_effective_weight": 26.14,
                "policy_memory_source": "runs/recent.jsonl",
            },
        },
    ])

    assert audit["policy_memory_used"] is True
    assert audit["prior_records"] == pytest.approx(26.14)
    assert "prior_records=26.14" in format_compact_audit(audit)


def test_compact_audit_reports_t3_productivity() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_conservative_tight",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.07,
            "llm_turns": 2,
            "turn_trace_count": 2,
            "backend_picks": ["tier5", "tier5"],
            "turn_traces": [
                {
                    "backend_tier": 5,
                    "final_backend": "tier5",
                    "has_progress": True,
                    "billable_cost": 0.03,
                    "rescue_window_opened": True,
                },
                {
                    "backend_tier": 5,
                    "final_backend": "tier5",
                    "has_progress": False,
                    "billable_cost": 0.04,
                    "parser_error_type": "FormatError",
                    "value_triggered_escalation_opened": True,
                },
            ],
        }
    ])

    stats = audit["t3_productivity"]["budgetflow_conservative_tight"]

    assert audit["t3_tier"] == 5
    assert stats["t3_turns"] == 2
    assert stats["t3_productive_turns"] == 1
    assert stats["t3_no_progress_turns"] == 1
    assert stats["t3_productive_rate"] == 0.5
    assert stats["t3_no_progress_cost"] == 0.04
    assert audit["t3_source_breakdown"]["budgetflow_conservative_tight"]["evidence_triggered"]["t3_turns"] == 1
    value_triggered = audit["t3_source_breakdown"]["budgetflow_conservative_tight"]["value_triggered"]
    assert value_triggered["t3_turns"] == 1
    assert value_triggered["t3_no_progress_cost"] == 0.04

    text = format_compact_audit(audit)
    assert "T2 T3 PRODUCTIVITY" in text
    assert "strongest_model=T5" in text
    assert "T3 SOURCE BREAKDOWN" in text
    assert "value_triggered" in text


def test_compact_audit_reports_t2_frontier_and_stage_split_control() -> None:
    records = [
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_value_aware_tight",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.30,
            "llm_turns": 3,
            "turn_trace_count": 3,
            "backend_picks": ["tier2"],
            "task_value": 2.0,
            "resolved_value": 2.0,
        },
        {
            "instance_id": "repo__task-b",
            "strategy": "budgetflow_value_aware_tight",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.20,
            "llm_turns": 2,
            "turn_trace_count": 2,
            "backend_picks": ["tier3"],
            "task_value": 1.0,
            "resolved_value": 0.0,
        },
        {
            "instance_id": "repo__task-a",
            "strategy": "value_aware_task_level_tight",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.10,
            "llm_turns": 1,
            "turn_trace_count": 1,
            "backend_picks": ["tier2"],
            "task_value": 2.0,
            "resolved_value": 0.0,
        },
        {
            "instance_id": "repo__task-b",
            "strategy": "value_aware_task_level_tight",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.10,
            "llm_turns": 1,
            "turn_trace_count": 1,
            "backend_picks": ["tier2"],
            "task_value": 1.0,
            "resolved_value": 0.0,
        },
    ]

    audit = build_compact_audit(records)
    delta = audit["stage_split_control_delta"]
    text = format_compact_audit(audit)

    assert audit["common_task_count"] == 2
    assert delta["delta_pass"] == 1
    assert delta["delta_normalized_verified_resolved_value"] == pytest.approx(2 / 3)
    assert "T2 FRONTIER COMMON-TASK" in text
    assert "STAGE-AWARE VS TASK-LEVEL CONTROL" in text


def test_value_fallback_check_allows_explicit_equal_value_t2_runs() -> None:
    issues = _check_value_profile_fallback([
        {
            "run_series": "equal_t2",
            "task_value_profile": "equal",
            "task_value": 1.0,
            "value_source": "default_equal",
        },
        {
            "run_series": "equal_t2",
            "task_value_profile": "equal",
            "task_value": 1.0,
            "value_source": "default_equal",
        },
    ])

    assert issues == []


def test_value_fallback_check_flags_equal_values_for_non_equal_profiles() -> None:
    issues = _check_value_profile_fallback([
        {
            "run_series": "bad_t1",
            "task_value_profile": "difficulty",
            "task_value": 1.0,
            "value_source": "value_matrix",
        },
        {
            "run_series": "bad_t1",
            "task_value_profile": "difficulty",
            "task_value": 1.0,
            "value_source": "value_matrix",
        },
    ])

    assert any(issue.startswith("VALUE_FALLBACK bad_t1") for issue in issues)


def test_harness_trust_treats_no_patch_fail_as_non_blocking() -> None:
    trust = build_harness_trust({
        "harness_resolved": False,
        "patch_extracted": False,
        "detail": "",
    })

    assert trust["harness_trust"] == "incomplete"
    assert trust["severity"] == "warn"


def test_harness_trust_treats_failed_patch_as_trusted_failure() -> None:
    trust = build_harness_trust({
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/submitted.patch",
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
    })

    assert trust["harness_trust"] == "trusted"
    assert trust["severity"] == "none"


def test_harness_trust_blocks_resolved_rows_with_missing_pass_evidence() -> None:
    trust = build_harness_trust({
        "harness_resolved": True,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/submitted.patch",
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
    })

    assert trust["harness_trust"] == "invalid"
    assert trust["severity"] == "blocking"

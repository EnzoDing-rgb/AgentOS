from budgetflow.run_observability.audit import build_compact_audit
from budgetflow.run_observability.checker import check_jsonl
from budgetflow.observability import HeartbeatWriter, build_harness_trust
from budgetflow.run_observability.checks import (
    _check_cost_accounting,
    _check_partial_run,
    _check_shared_cap_starvation,
    _check_value_profile_fallback,
)
from budgetflow.run_observability.schema import _check_desired_fields, _check_observability_schema
from budgetflow.run_observability.report import format_compact_audit
from budgetflow.run_observability.schema import _check_trace_coverage
import pytest
import json


def test_compact_audit_preserves_generic_tier_counts() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_segment",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.25,
            "llm_turns": 4,
            "turn_trace_count": 4,
            "backend_picks": ["tier2_balanced", "tier4", "tier5", "tier5"],
        }
    ])

    stats = audit["by_strategy"]["budgetflow_segment"]

    assert stats["tier_turns"] == {2: 1, 4: 1, 5: 2}
    assert stats["t3_turns"] == 0


def test_heartbeat_mark_done_preserves_partial_run_status(tmp_path) -> None:
    hb_path = tmp_path / "partial.heartbeat.json"
    writer = HeartbeatWriter(hb_path, run_series="partial", total_expected=100)
    writer.pulse(rows_done=31, active_strategy="s1", active_instance="task-a")

    writer.mark_done()

    heartbeat = json.loads(hb_path.read_text())
    assert heartbeat["rows_done"] == 31
    assert heartbeat["total_expected"] == 100
    assert heartbeat["status"].startswith("aborted")


def test_trace_coverage_allows_pre_provider_budget_exhaustion() -> None:
    issues = _check_trace_coverage([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_task_level",
            "harness_resolved": False,
            "exit_status": "BudgetFlowBudgetError",
            "exit_reason": "budget_exhausted",
            "patch_extracted": False,
            "agent_gold_edited": False,
            "turn_trace_count": 0,
        }
    ])

    assert issues == []


def test_trace_coverage_still_flags_non_budget_missing_trace() -> None:
    issues = _check_trace_coverage([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_task_level",
            "harness_resolved": False,
            "exit_status": "HarnessFailed",
            "exit_reason": "harness_failed",
            "patch_extracted": False,
            "agent_gold_edited": False,
            "turn_trace_count": 0,
        }
    ])

    assert issues
    assert issues[0].startswith("NO_TRACE")


def test_shared_cap_starvation_uses_agent_exit_reason() -> None:
    issues = _check_shared_cap_starvation([
        {
            "run_series": "small_check",
            "instance_id": "repo__task",
            "strategy": "budgetflow_task_level",
            "budget_mode": "shared",
            "exit_status": "HarnessFailed",
            "exit_reason": "harness_failed",
            "agent_exit_status": "BudgetFlowBudgetError",
            "agent_exit_reason": "budget_exhausted",
        }
    ])

    assert issues
    assert "1 rows exited" in issues[0]


def test_shared_cap_starvation_ignores_resolved_agent_budget_exit() -> None:
    issues = _check_shared_cap_starvation([
        {
            "run_series": "small_check",
            "instance_id": "repo__task",
            "strategy": "budgetflow_task_level",
            "budget_mode": "shared",
            "harness_resolved": True,
            "score_status": "pass",
            "exit_status": "HarnessResolved",
            "exit_reason": "harness_resolved",
            "agent_exit_status": "BudgetFlowBudgetError",
            "agent_exit_reason": "budget_exhausted",
        }
    ])

    assert issues == []


def test_compact_audit_reports_value_metrics() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_segment",
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
            "strategy": "budgetflow_segment",
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
        {
            "instance_id": "repo__task-c",
            "strategy": "budgetflow_segment",
            "harness_resolved": False,
            "score_status": "abort",
            "abort_reason": "extract_fail",
            "harness_evidence": {"evidence_complete": False},
            "total_cost": 0.30,
            "llm_turns": 2,
            "turn_trace_count": 2,
            "backend_picks": ["tier3"],
            "task_value": 0.5,
            "resolved_value": 0.0,
            "task_value_profile": "difficulty",
            "value_objective": "t1_value_efficiency",
        },
    ])

    stats = audit["by_strategy"]["budgetflow_segment"]

    assert audit["value_profile"] == "difficulty"
    assert stats["yield_score"] == 0.6
    assert stats["yield_coverage"] == 0.6
    assert stats["yield_per_dollar"] == pytest.approx(2.0)
    assert stats["yield_per_scoreable_dollar"] == pytest.approx(2.0)
    assert stats["yield_per_total_dollar"] == pytest.approx(1.0)
    assert stats["total_spend"] == pytest.approx(0.6)
    assert stats["scoreable_cost"] == pytest.approx(0.3)
    assert stats["abort_cost"] == pytest.approx(0.3)
    assert "PAPER METRICS" in format_compact_audit(audit)
    assert "Yield/total$" in format_compact_audit(audit)
    assert "Yield/score$" in format_compact_audit(audit)


def test_compact_audit_counts_actionable_decision_issues() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_segment",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": False},
            "patch_extracted": True,
            "patch_source": "submission",
            "submitted_patch": "/tmp/p.patch",
            "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
            "total_cost": 0.1,
            "llm_turns": 1,
            "turn_trace_count": 1,
            "turn_traces": [
                {"backend_tier": 2, "provider_status_code": 503},
            ],
            "policy_memory_enabled": True,
        }
    ])

    issues = audit["decision_issue_counts"]

    assert issues["missing_value"] == 1
    assert issues["missing_value_source"] == 1
    assert issues["missing_cost_confidence"] == 1
    assert issues["missing_policy_decision"] == 1
    assert issues["provider_error"] == 1
    assert issues["memory_enabled_missing_source"] == 1
    assert issues["harness_blocking"] == 1
    assert audit["decision_area_counts"]["value"] == 2
    assert audit["decision_area_counts"]["cost"] == 1
    assert audit["decision_area_counts"]["routing"] == 1
    assert "DECISION ISSUE AREAS" in format_compact_audit(audit)
    assert "DECISION ISSUES" in format_compact_audit(audit)


def test_compact_audit_accepts_trace_cost_confidence() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_segment",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "task_value": 1.0,
            "value_source": "equal_sanity",
            "total_cost": 0.1,
            "llm_turns": 1,
            "turn_trace_count": 1,
            "turn_traces": [
                {
                    "backend_tier": 2,
                    "policy_decision": {"backend": "tier2"},
                    "cost_estimate_confidence": {"backend": "tier2"},
                },
            ],
        }
    ])

    assert "missing_cost_confidence" not in audit["decision_issue_counts"]


def test_compact_audit_accepts_pre_provider_budget_block_cost_confidence() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_task_level",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": False},
            "task_value": 1.0,
            "value_source": "manual_value",
            "total_cost": 0.0,
            "usage_source": "none",
            "cost_mode": "no_provider_call",
            "llm_turns": 1,
            "turn_trace_count": 0,
            "exit_status": "BudgetFlowBudgetError",
            "exit_reason": "budget_exhausted",
            "agent_exit_status": "BudgetFlowBudgetError",
            "agent_exit_reason": "budget_exhausted",
        }
    ])

    assert "missing_cost_confidence" not in audit["decision_issue_counts"]


def test_compact_audit_reports_repo_memory_evidence_for_new_tasks() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__new-task",
            "strategy": "budgetflow_segment",
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
                "routing_policy_memory_source": "runs/recent.jsonl",
            },
        ])

    assert audit["policy_memory_used"] is True
    assert audit["prior_records"] == pytest.approx(26.14)
    assert "prior_records=26.14" in format_compact_audit(audit)


def test_compact_audit_reports_t3_productivity() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "bootstrap_conservative_diagnostic",
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
                    "action_has_progress": False,
                    "billable_cost": 0.04,
                    "parser_error_type": "FormatError",
                    "value_triggered_escalation_opened": True,
                },
            ],
        }
    ])

    stats = audit["t3_productivity"]["bootstrap_conservative_diagnostic"]

    assert audit["t3_tier"] == 5
    assert stats["t3_turns"] == 2
    assert stats["t3_productive_turns"] == 1
    assert stats["t3_no_progress_turns"] == 1
    assert stats["t3_productive_rate"] == 0.5
    assert stats["t3_no_progress_cost"] == 0.04
    assert audit["t3_source_breakdown"]["bootstrap_conservative_diagnostic"]["evidence_triggered"]["t3_turns"] == 1
    value_triggered = audit["t3_source_breakdown"]["bootstrap_conservative_diagnostic"]["value_triggered"]
    assert value_triggered["t3_turns"] == 1
    assert value_triggered["t3_no_progress_cost"] == 0.04

    text = format_compact_audit(audit)
    assert "STRONGEST MODEL PRODUCTIVITY" in text
    assert "strongest_model=T5" in text
    assert "T3 SOURCE BREAKDOWN" in text
    assert "value_triggered" in text


def test_compact_audit_uses_current_action_progress_for_t3_productivity() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_segment",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.07,
            "llm_turns": 1,
            "turn_trace_count": 1,
            "backend_picks": ["tier5"],
            "turn_traces": [
                {
                    "backend_tier": 5,
                    "final_backend": "tier5",
                    "has_progress": False,
                    "progress_reason": "none",
                    "action_has_progress": True,
                    "action_progress_reason": "action_repair_pattern",
                    "action_digest": "apply_patch <<'PATCH'",
                    "billable_cost": 0.03,
                    "strongest_starter_applied": True,
                },
            ],
        }
    ])

    stats = audit["t3_productivity"]["budgetflow_segment"]

    assert stats["t3_productive_turns"] == 1
    assert stats["t3_no_progress_turns"] == 0
    assert stats["t3_no_progress_cost"] == 0.0


def test_compact_audit_uses_backend_tier_before_final_backend_for_t3_productivity() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_segment",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.07,
            "llm_turns": 2,
            "turn_trace_count": 2,
            "backend_picks": ["tier3", "tier2"],
            "turn_traces": [
                {
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "action_has_progress": True,
                    "billable_cost": 0.03,
                },
                {
                    "backend_tier": 2,
                    "final_backend": "tier3",
                    "action_has_progress": True,
                    "billable_cost": 0.04,
                },
            ],
        }
    ])

    stats = audit["t3_productivity"]["budgetflow_segment"]

    assert stats["t3_turns"] == 1
    assert stats["t3_productive_turns"] == 1
    assert stats["t3_cost"] == pytest.approx(0.03)


def test_checker_ignores_unrelated_stale_heartbeat_files(tmp_path) -> None:
    path = tmp_path / "current.jsonl"
    path.write_text(
        '{"instance_id":"task-a","strategy":"budgetflow_same_router","routing":"budgetflow_same_router",'
        '"harness_resolved":false,"exit_status":"failed","exit_reason":"stagnation","total_cost":0.1,'
        '"llm_turns":1,"elapsed_s":1,"detail":"test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",'
        '"turn_trace_count":1,"run_series":"current","policy_lane":"budgetflow_same_router","task_order_index":1,'
        '"row_started_at":1,"row_finished_at":2,"harness_evidence":{"evidence_complete":true},'
        '"observability_status":{},"score_status":"true_fail","scoreable":true,'
        '"turn_traces":[{"response_ok":true,"protocol":"tool_call","action_progress_state":"progress","action_digest":"edit"}]}\n'
    )
    (tmp_path / "current.heartbeat.json").write_text(
        '{"run_series":"current","rows_done":1,"total_expected":1,"status":"completed","current_pid":0}\n'
    )
    (tmp_path / "old_run.heartbeat.json").write_text(
        '{"run_series":"old_run","rows_done":0,"total_expected":10,"status":"running","current_pid":99999999,'
        '"updated_at":1,"started_at":1}\n'
    )

    result = check_jsonl(path, heartbeat_stale_s=1)

    assert "old_run" not in result["heartbeat_summary"]
    assert not any("old_run" in issue for issue in result["issues"])
    assert result["heartbeat_suspicious"] is False


def test_compact_audit_does_not_count_unknown_progress_as_no_progress() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_segment",
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
                    "progress_state": "unknown",
                    "action_progress_state": "unknown",
                    "billable_cost": 0.03,
                },
                {
                    "backend_tier": 5,
                    "final_backend": "tier5",
                    "has_progress": None,
                    "action_has_progress": None,
                    "billable_cost": 0.04,
                },
            ],
        }
    ])

    stats = audit["t3_productivity"]["budgetflow_segment"]
    row = audit["per_task_comparison"][0]

    assert stats["t3_turns"] == 2
    assert stats["t3_productive_turns"] == 0
    assert stats["t3_no_progress_turns"] == 0
    assert stats["t3_unknown_progress_turns"] == 2
    assert stats["t3_no_progress_cost"] == 0.0
    assert stats["t3_unknown_progress_cost"] == pytest.approx(0.07)
    assert row["first_useful_action"] is None
    assert row["max_no_progress_streak"] == 0
    text = format_compact_audit(audit)
    assert "unknown" in text


def test_compact_audit_treats_any_progress_channel_as_productive() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_segment",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.05,
            "llm_turns": 1,
            "turn_trace_count": 1,
            "backend_picks": ["tier3"],
            "turn_traces": [
                {
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "progress_state": "progress",
                    "action_progress_state": "no_progress",
                    "billable_cost": 0.05,
                },
            ],
        }
    ])

    stats = audit["t3_productivity"]["budgetflow_segment"]

    assert stats["t3_turns"] == 1
    assert stats["t3_productive_turns"] == 1
    assert stats["t3_no_progress_turns"] == 0
    assert stats["t3_no_progress_cost"] == 0.0


def test_compact_audit_reports_mechanism_isolation_delta() -> None:
    records = [
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_same_enterprise_router",
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
            "strategy": "budgetflow_same_enterprise_router",
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
            "strategy": "enterprise_router_baseline",
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
            "strategy": "enterprise_router_baseline",
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
    delta = audit["mechanism_isolation_delta"]
    text = format_compact_audit(audit)

    assert audit["common_task_count"] == 2
    assert delta["delta_pass"] == 1
    assert delta["delta_yield"] == pytest.approx(2.0)
    assert delta["delta_yield_coverage"] == pytest.approx(2 / 3)
    assert "COMMON-TASK POLICY COMPARISON" in text
    assert "MECHANISM ISOLATION DELTA" in text


def test_compact_audit_reports_task_set_metrics() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_segment",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.50,
            "llm_turns": 2,
            "turn_trace_count": 2,
            "backend_picks": ["tier2"],
            "task_value": 3.0,
            "resolved_value": 3.0,
            "task_set": "easy",
            "task_set_kind": "familiar",
        },
        {
            "instance_id": "repo__task-b",
            "strategy": "budgetflow_segment",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.25,
            "llm_turns": 1,
            "turn_trace_count": 1,
            "backend_picks": ["tier2"],
            "task_value": 1.0,
            "resolved_value": 0.0,
            "task_set": "medium",
            "task_set_kind": "unseen",
        },
    ])

    familiar = audit["task_set_metrics"]["familiar"]["easy"]["budgetflow_segment"]
    unseen = audit["task_set_metrics"]["unseen"]["medium"]["budgetflow_segment"]

    assert familiar["yield_score"] == pytest.approx(3.0)
    assert familiar["yield_per_dollar"] == pytest.approx(6.0)
    assert unseen["pass"] == 0
    assert "TASK SET METRICS" in format_compact_audit(audit)


def test_value_fallback_check_allows_explicit_equal_value_t2_runs() -> None:
    issues = _check_value_profile_fallback([
        {
            "run_series": "equal_t2",
            "task_value_profile": "equal",
            "task_value": 1.0,
            "value_source": "equal_sanity",
        },
        {
            "run_series": "equal_t2",
            "task_value_profile": "equal",
            "task_value": 1.0,
            "value_source": "equal_sanity",
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


def test_harness_trust_allows_runtime_worktree_pytest_rootdir() -> None:
    trust = build_harness_trust({
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/submitted.patch",
        "detail": (
            "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; "
            "rootdir: /tmp/budgetflow-runtime/worktrees/sympy__sympy/"
            "bare_t3_baseline_sympy__sympy-12171"
        ),
    })

    assert trust["harness_trust"] == "trusted"
    assert trust["severity"] == "none"


def test_harness_trust_blocks_host_dependency_contamination() -> None:
    trust = build_harness_trust({
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/submitted.patch",
        "detail": (
            "test_patch=ok; fail_before=fail; model_patch=ok; "
            "fail_after=fail; ValueError: numpy.dtype size changed"
        ),
    })

    assert trust["harness_trust"] == "invalid"
    assert trust["severity"] == "blocking"
    assert trust["harness_owner"] == "infra"


def test_harness_trust_blocks_foreign_runtime_worktree_log() -> None:
    trust = build_harness_trust({
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/submitted.patch",
        "detail": (
            "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; "
            "/tmp/budgetflow-task-scout/runtime/worktrees/psf__requests/"
            "scout_requests/requests/utils.py:12: DeprecationWarning; "
            "pass_to_pass=fail"
        ),
    })

    assert trust["harness_trust"] == "invalid"
    assert trust["severity"] == "blocking"
    assert trust["harness_owner"] == "infra"


def test_checker_counts_invalid_harness_as_error(tmp_path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(
        '{"instance_id":"sympy__sympy-1","strategy":"budgetflow_segment",'
        '"routing":"segment_value_aware","harness_resolved":false,'
        '"patch_extracted":true,"patch_source":"submission","submitted_patch":"/tmp/p.patch",'
        '"exit_status":"Submitted","exit_reason":"submitted","total_cost":0.1,'
        '"llm_turns":1,"turns":1,"elapsed_s":1,"turn_trace_count":1,'
        '"run_series":"unit","policy_lane":"budgetflow_segment",'
        '"task_order_index":1,"row_started_at":1,"row_finished_at":2,'
        '"harness_evidence":{"evidence_complete":false},'
        '"observability_status":{"trace_available":true},'
        '"detail":"test_patch=ok; fail_before=fail; model_patch=ok; '
        'fail_after=fail; ValueError: numpy.dtype size changed"}\n'
    )

    result = check_jsonl(path)

    assert result["errors"] >= 1
    assert any(issue.startswith("HARNESS_INVALID") for issue in result["issues"])


def test_partial_run_warning_reports_rows_and_policy_progress(tmp_path) -> None:
    hb_path = tmp_path / "partial.heartbeat.json"
    hb_path.write_text(
        json.dumps(
            {
                "run_series": "partial",
                "rows_done": 5,
                "total_expected": 8,
                "status": "running",
                "current_pid": 0,
            }
        )
    )
    records = [
        {
            "run_series": "partial",
            "instance_id": "task-a",
            "strategy": "bare_t2_baseline",
            "task_order_index": 1,
        },
        {
            "run_series": "partial",
            "instance_id": "task-a",
            "strategy": "bare_t3_baseline",
            "task_order_index": 1,
        },
        {
            "run_series": "partial",
            "instance_id": "task-a",
            "strategy": "enterprise_router_baseline",
            "task_order_index": 1,
        },
        {
            "run_series": "partial",
            "instance_id": "task-a",
            "strategy": "budgetflow_task_level",
            "task_order_index": 1,
        },
        {
            "run_series": "partial",
            "instance_id": "task-b",
            "strategy": "budgetflow_task_level",
            "task_order_index": 2,
        },
    ]

    issues = _check_partial_run(records, tmp_path)

    assert any("rows_done=5/8" in issue for issue in issues)
    assert any("bare_t2_baseline=1/2" in issue for issue in issues)
    assert any("budgetflow_task_level=2/2" in issue for issue in issues)


def test_observability_schema_warns_on_scoreable_untrusted_harness() -> None:
    issues = _check_observability_schema([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_task_level",
            "score_status": "true_fail",
            "scoreable": True,
            "harness_trust": "incomplete",
            "harness_issues": ["no_patch_extracted"],
            "harness_owner": "protocol",
            "harness_severity": "warn",
            "harness_resolved": False,
            "patch_source": "none",
        }
    ])

    assert any(issue.startswith("SCOREABLE_UNTRUSTED_HARNESS") for issue in issues)


def test_desired_fields_do_not_require_workspace_patch_for_submission_rows() -> None:
    issues = _check_desired_fields([
        {
            "instance_id": "repo__task",
            "strategy": "bare_t3_baseline",
            "patch_source": "submission",
            "submitted_patch": "/tmp/submitted.patch",
            "failure_class": "pass",
            "forensic_summary": {},
            "backend_picks": ["tier3"],
            "attempt_id": "unit",
            "frozen_plan_name": None,
            "frozen_plan_preferred_model": None,
            "frozen_plan_priority": None,
            "abort_reason": "",
            "abort_owner": "",
            "abort_stage": "",
            "true_fail_reason": "",
        }
    ])

    assert issues == []


def test_observability_schema_requires_workspace_patch_only_for_workspace_diff_rows() -> None:
    issues = _check_observability_schema([
        {
            "instance_id": "repo__task-a",
            "strategy": "budgetflow_task_level",
            "score_status": "true_fail",
            "harness_resolved": False,
            "harness_trust": "trusted",
            "patch_extracted": True,
            "patch_source": "submission",
        },
        {
            "instance_id": "repo__task-b",
            "strategy": "budgetflow_task_level",
            "score_status": "true_fail",
            "harness_resolved": False,
            "harness_trust": "trusted",
            "patch_extracted": True,
            "patch_source": "workspace_diff",
        },
        {
            "instance_id": "repo__task-c",
            "strategy": "budgetflow_task_level",
            "score_status": "true_fail",
            "harness_resolved": False,
            "harness_trust": "trusted",
            "patch_extracted": True,
            "patch_source": "workspace_diff",
            "workspace_patch": "/tmp/workspace.patch",
        },
    ])

    assert any(issue.startswith("WORKSPACE_PATCH_MISSING") and "repo__task-b" in issue for issue in issues)
    assert not any("repo__task-a" in issue for issue in issues)
    assert not any("repo__task-c" in issue for issue in issues)


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


def test_per_task_comparison_includes_cross_policy_rows() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task-a",
            "strategy": "budget_only_baseline",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.30,
            "llm_turns": 3,
            "turn_trace_count": 3,
            "backend_picks": ["tier3", "tier3", "tier2"],
            "task_value": 2.0,
            "resolved_value": 2.0,
            "turn_traces": [
                {"workflow_segment": "Context", "backend_tier": 3, "has_progress": True},
                {"workflow_segment": "Action", "backend_tier": 3, "has_progress": True},
                {"workflow_segment": "Action", "backend_tier": 2, "has_progress": False},
            ],
            "patch_extracted": True,
        },
        {
            "instance_id": "repo__task-a",
            "strategy": "bootstrap_conservative_diagnostic",
            "harness_resolved": False,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.50,
            "llm_turns": 5,
            "turn_trace_count": 5,
            "backend_picks": ["tier2", "tier2", "tier2", "tier2", "tier3"],
            "task_value": 2.0,
            "resolved_value": 0.0,
            "frozen_plan_name": "unit_plan",
            "frozen_plan_preferred_model": "tier3",
            "frozen_plan_priority": 2,
            "turn_traces": [
                {"workflow_segment": "Context", "backend_tier": 2, "has_progress": False},
                {
                    "workflow_segment": "Action",
                    "backend_tier": 2,
                    "has_progress": False,
                    "router_branch": "segment_value_aware",
                    "router_reason": "bootstrap:budget_pressure",
                    "policy_type": "bootstrap",
                    "policy_name": "budgetflow_segment",
                    "memory_mode": "built_in",
                    "policy_decision": {
                        "backend": "tier2",
                        "reason": "bootstrap:budget_pressure",
                    },
                    "cost_estimate_source": "tier_catalog:test",
                    "provider": "openai_compatible",
                    "protocol": "tool_call",
                    "parser": "parse_tool_actions",
                },
                {"workflow_segment": "Action", "backend_tier": 2, "has_progress": False},
                {"workflow_segment": "Action", "backend_tier": 2, "has_progress": False},
                {"workflow_segment": "Action", "backend_tier": 3, "has_progress": False},
            ],
            "patch_extracted": False,
            "failure_class": "repair_fail",
            "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
        },
    ])

    per_task = audit["per_task_comparison"]

    assert len(per_task) == 2
    bo_row = per_task[0]
    bf_row = per_task[1]

    assert bo_row["instance_id"] == "repo__task-a"
    assert bo_row["strategy"] == "budget_only_baseline"
    assert bo_row["resolved"] is True
    assert bo_row["first_tier"] == 3
    assert bo_row["first_t3_turn"] == 0
    assert bo_row["first_useful_action"] == 0
    assert bo_row["max_no_progress_streak"] == 1

    assert bf_row["strategy"] == "bootstrap_conservative_diagnostic"
    assert bf_row["resolved"] is False
    assert bf_row["first_tier"] == 2
    assert bf_row["first_t3_turn"] == 4
    assert bf_row["first_useful_action"] is None
    assert bf_row["max_no_progress_streak"] == 5
    assert bf_row["no_patch"] is True
    assert bf_row["failure_class"] == "repair_fail"
    assert bf_row["harness_trust"] == "incomplete"
    assert bf_row["harness_evidence_complete"] is True
    assert bf_row["policy_name"] == "budgetflow_segment"
    assert bf_row["memory_mode"] == "built_in"
    assert bf_row["cost_estimate_source"] == "tier_catalog:test"
    assert bf_row["frozen_plan_name"] == "unit_plan"
    assert bf_row["frozen_plan_preferred_model"] == "tier3"
    assert bf_row["frozen_plan_priority"] == 2

    text = format_compact_audit(audit)
    assert "PER-TASK POLICY COMPARISON" in text
    assert "repo__task-a" in text
    assert "budget_only_baseline" in text
    assert "bootstrap_conservative_diagnostic" in text
    assert "decision:" in text
    assert "tier3" in text
    assert "pri=frozen_plan_priority" in text
    assert "frozen=unit_plan/tier3/2" in text
    assert "memory=built_in" in text
    assert "cost=tier_catalog:test" in text


# ── Cost accounting ─────────────────────────────────────────────────────


def test_cost_accounting_no_duplicates() -> None:
    records = [
        {"instance_id": "task-a", "strategy": "bare_t2_baseline", "total_cost": 0.5, "score_status": "pass"},
        {"instance_id": "task-b", "strategy": "bare_t2_baseline", "total_cost": 0.3, "score_status": "true_fail"},
    ]
    issues = _check_cost_accounting(records)
    assert any("raw_paid_cost=$0.8000" in i for i in issues)
    assert any("dedup_scored_cost=$0.8000" in i for i in issues)
    assert any("duplicate_retry_overhead=$0.0000" in i for i in issues)


def test_cost_accounting_detects_duplicate_overhead() -> None:
    records = [
        {"instance_id": "task-a", "strategy": "bare_t2_baseline", "total_cost": 0.5, "score_status": "pass", "row_finished_at": 100},
        {"instance_id": "task-a", "strategy": "bare_t2_baseline", "total_cost": 0.3, "score_status": "pass", "row_finished_at": 200},
        {"instance_id": "task-b", "strategy": "bare_t2_baseline", "total_cost": 0.4, "score_status": "true_fail", "row_finished_at": 300},
    ]
    issues = _check_cost_accounting(records)
    assert any("raw_paid_cost=$1.2000" in i for i in issues)
    assert any("duplicate_retry_overhead=$0.5000" in i for i in issues)
    assert any("dedup_scored_cost=$0.7000" in i for i in issues)
    assert any("1 duplicate rows" in i for i in issues)


def test_cost_accounting_handles_abort_rows() -> None:
    records = [
        {"instance_id": "task-a", "strategy": "budgetflow_segment", "total_cost": 0.1, "score_status": "abort", "abort_reason": "provider_error"},
        {"instance_id": "task-a", "strategy": "budgetflow_segment", "total_cost": 0.5, "score_status": "pass", "row_finished_at": 200},
    ]
    issues = _check_cost_accounting(records)
    # raw = 0.6, dedup = 0.5 (abort row excluded from scored set, pass row kept)
    assert any("raw_paid_cost=$0.6000" in i for i in issues)
    assert any("duplicate_retry_overhead=$0.1000" in i for i in issues)

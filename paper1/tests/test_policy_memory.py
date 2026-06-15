from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from budgetflow.adaptive_routing import AdaptiveRoutingState, rescue_state_for_strategy
from budgetflow.learning_context import looks_like_policy_memory_source
from budgetflow.policy_memory import PolicyMemory
from budgetflow.types import WorkflowSegment

ROOT = Path(__file__).resolve().parents[1]


def _record(**overrides) -> dict:
    record = {
        "instance_id": "sympy__sympy-10001",
        "strategy": "budgetflow_segment",
        "routing": "segment_value_aware",
        "harness_resolved": False,
        "score_status": "true_fail",
        "failure_class": "repair_fail",
        "total_cost": 0.10,
        "backend_picks": ["tier2", "tier2"],
        "turn_traces": [
            {"workflow_segment": "Action", "backend_tier": 2, "has_progress": False},
        ],
        "routing_decision_schema": "v1",
        "task_set_kind": "familiar",
        "policy_kind": "bootstrap",
        "learn_policy_input_views": ["routing", "escalation"],
        "harness_trust": "trusted",
    }
    record.update(overrides)
    return record


def _pass_record(**overrides) -> dict:
    return _record(
        harness_resolved=True,
        score_status="pass",
        failure_class="pass",
        backend_picks=["tier2"],
        turn_traces=[{"workflow_segment": "Context", "backend_tier": 2, "has_progress": True}],
        **overrides,
    )


def test_policy_memory_source_rejects_host_dependency_contamination(tmp_path: Path) -> None:
    contaminated = tmp_path / "contaminated.jsonl"
    contaminated.write_text(json.dumps(_record(
        detail="fail_after=fail; ValueError: numpy.dtype size changed",
    )) + "\n")
    clean = tmp_path / "clean.jsonl"
    clean.write_text(json.dumps(_record(
        detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
    )) + "\n")

    assert looks_like_policy_memory_source(contaminated) is False
    assert looks_like_policy_memory_source(clean) is True


def test_policy_memory_rebuilds_task_repo_and_routing_priors() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _pass_record(instance_id="sympy__sympy-1", total_cost=0.05),
        _record(instance_id="sympy__sympy-2", total_cost=0.20),
        _record(instance_id="sympy__sympy-2", total_cost=0.30, backend_picks=["tier3"]),
    ])

    task = memory.task_prior("sympy__sympy-2")
    repo = memory.repo_prior("sympy__sympy-1")
    summary = memory.routing_prior_summary("sympy__sympy-2", WorkflowSegment.ACTION)

    assert task.seen == 2
    assert task.pass_count == 0
    assert repo.total_tasks == 2
    assert repo.t2_turns > 0
    assert repo.t3_turns > 0
    assert summary["task_seen"] == 2
    assert summary["repo_t2_success"] >= 0.0
    assert "learned_action" in summary
    assert "regret_threshold" in summary


def test_policy_memory_ignores_abort_records() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__sympy-abort",
            score_status="abort",
            abort_reason="provider_or_infra_error",
            failure_class="infra_fail",
            total_cost=0.40,
        ),
    ])

    assert memory.task_prior("sympy__sympy-abort").seen == 0
    assert memory.repo_prior("sympy__sympy-abort").evidence_weight == 0.0

    memory.rebuild_from_records([
        _record(
            instance_id="sympy__sympy-abort",
            score_status="abort",
            abort_reason="provider_or_infra_error",
            failure_class="infra_fail",
            total_cost=0.40,
        ),
        _pass_record(instance_id="sympy__sympy-pass", total_cost=0.10),
    ])

    assert memory.task_prior("sympy__sympy-pass").seen == 1
    assert memory.repo_prior("sympy__sympy-pass").evidence_weight == 1.0


def test_policy_memory_preserves_generic_tier_evidence() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__sympy-1",
            harness_resolved=True,
            failure_class="pass",
            backend_picks=["tier2_balanced", "tier4", "tier5", "tier5"],
            turn_traces=[
                {"workflow_segment": "Action", "backend_tier": 4},
                {"workflow_segment": "Action", "backend_tier": 5},
            ],
        )
    ])

    repo = memory.repo_prior("sympy__sympy-1")
    task = memory.task_prior("sympy__sympy-1")
    summary = memory.routing_prior_summary("sympy__sympy-1", WorkflowSegment.ACTION)

    assert dict(repo.tier_turns) == {2: 1, 4: 1, 5: 2}
    assert dict(task.tier_turns) == {2: 1, 4: 1, 5: 2}
    assert summary["repo_tier_turns"] == {"2": 1, "4": 1, "5": 2}
    assert summary["segment_tier_success"] == {"4": 1.0, "5": 1.0}
    assert summary["repo_t3_success"] == 0


def test_policy_memory_uses_workflow_segment_keys_when_available() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="repo__repair-a",
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2}],
        ),
        _record(
            instance_id="repo__repair-b",
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2}],
        ),
        _record(
            instance_id="repo__repair-c",
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2}],
        ),
    ])

    summary = memory.routing_prior_summary("repo__new-repair", WorkflowSegment.ACTION)

    assert summary["segment_tier_weight"]["2"] == 3.0
    assert summary["learned_action"] == "early_rescue"


def test_policy_memory_learns_t1_t2_actions_from_prior_runs() -> None:
    records = [
        _record(instance_id="repair__task-a", backend_picks=["tier2"]),
        _record(instance_id="repair__task-b", backend_picks=["tier2"]),
        _record(instance_id="repair__task-c", backend_picks=["tier2"]),
        _record(instance_id="cost__task-a", routing="segment_value_aware", total_cost=0.35),
        _record(instance_id="cost__task-a", routing="budget_only", strategy="budget_only_baseline", total_cost=0.05),
        _record(instance_id="cost__task-b", routing="segment_value_aware", total_cost=0.30),
        _record(instance_id="cost__task-b", routing="budget_only", strategy="budget_only_baseline", total_cost=0.06),
    ]
    memory = PolicyMemory()
    memory.rebuild_from_records(records)

    assert memory.routing_prior_summary("repair__task-a", WorkflowSegment.ACTION)["learned_action"] == "early_rescue"
    assert memory.routing_prior_summary("cost__task-a", WorkflowSegment.ACTION)["learned_action"] == "cap_strongest"


def test_low_weight_segment_evidence_does_not_drive_learned_actions() -> None:
    stale_failures = [
        _record(instance_id=f"repo__repair-{i}", _policy_memory_weight=0.05)
        for i in range(10)
    ]
    stale_localization_passes = [
        _pass_record(instance_id=f"repo__loc-{i}", _policy_memory_weight=0.05)
        for i in range(10)
    ]
    memory = PolicyMemory()
    memory.rebuild_from_records(stale_failures + stale_localization_passes)

    repair = memory.routing_prior_summary("repo__new-repair", WorkflowSegment.ACTION)
    localization = memory.routing_prior_summary("repo__new-loc", WorkflowSegment.CONTEXT)

    assert repair["segment_tier_weight"]["2"] == 0.5
    assert repair["learned_action"] == "default"
    assert localization["segment_tier_weight"]["2"] == 0.5
    assert localization["learned_action"] == "default"


def test_low_weight_protocol_evidence_does_not_drive_learned_action() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="repo__same-task",
            failure_class="format_error",
            _policy_memory_weight=0.05,
        ),
        _pass_record(
            instance_id="repo__same-task",
            _policy_memory_weight=1.0,
        ),
    ])

    summary = memory.routing_prior_summary("repo__same-task", WorkflowSegment.ACTION)

    assert summary["task_evidence_weight"] == 1.05
    assert summary["recent_failure_axis"] == "format_error"
    assert summary["learned_action"] == "default"


def test_sufficient_weight_protocol_evidence_drives_learned_action() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="repo__same-task",
            failure_class="format_error",
            _policy_memory_weight=1.0,
        ),
    ])

    summary = memory.routing_prior_summary("repo__same-task", WorkflowSegment.ACTION)

    assert summary["task_evidence_weight"] == 1.0
    assert summary["learned_action"] == "protocol_issue"


def test_low_weight_all_pro_failures_do_not_reduce_rescue() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="repo__same-task",
            strategy="all_pro",
            _policy_memory_weight=0.4,
        ),
        _record(
            instance_id="repo__same-task",
            strategy="all_pro",
            _policy_memory_weight=0.4,
        ),
    ])

    summary = memory.routing_prior_summary("repo__same-task", WorkflowSegment.ACTION)

    assert summary["task_all_pro_failure_weight"] == 0.8
    assert summary["learned_action"] == "default"


def test_weighted_tier_success_uses_effective_evidence_denominator() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _pass_record(instance_id="repo__loc-a", _policy_memory_weight=0.35),
    ])

    summary = memory.routing_prior_summary("repo__loc-b", WorkflowSegment.CONTEXT)

    assert summary["repo_evidence_weight"] == 0.35
    assert summary["repo_tier_success"]["2"] == 1.0
    assert summary["segment_tier_success"]["2"] == 1.0


def test_policy_memory_changes_runtime_rescue_and_starting_tier() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(instance_id="repo__repair-a", backend_picks=["tier2"]),
        _record(instance_id="repo__repair-b", backend_picks=["tier2"]),
        _record(instance_id="repo__repair-c", backend_picks=["tier2"]),
        _pass_record(instance_id="repo__loc-a"),
        _pass_record(instance_id="repo__loc-b"),
    ])

    rescue = rescue_state_for_strategy("segment_value_aware", memory, "repo__repair-a")
    state = AdaptiveRoutingState(strategy_name="budgetflow_segment", policy_memory=memory)
    state.set_task_context("repo__loc-a")

    assert rescue.trigger_turns < 6
    assert state.starting_tier() == 2
    assert state.prior_summary_for_trace() is not None


def test_policy_memory_can_imitate_budget_only_strongest_starter_window() -> None:
    bo_t3_frontload = [
        {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
        {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
    ]
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__task-a",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=bo_t3_frontload,
        ),
        _record(
            instance_id="django__task-a",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2}],
        ),
    ])

    summary = memory.routing_prior_summary("django__new-task", WorkflowSegment.CONTEXT)
    state = AdaptiveRoutingState(strategy_name="budgetflow_segment", policy_memory=memory)
    state.set_task_context("django__new-task")

    assert summary["starter_memory_source"] == "repo"
    assert summary["strongest_starter_action"] == "frontload_strongest"
    assert state.starting_tier() == 3
    assert state.consume_strongest_starter_tier(3) == 3
    assert state.strongest_starter_window_opened is True
    assert state.strongest_starter_applied_this_turn is True
    state.on_step()
    assert state.strongest_starter_applied_this_turn is False


def test_low_weight_budget_only_starter_evidence_does_not_frontload_strongest() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__task-a",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            _policy_memory_weight=0.4,
            turn_traces=[{"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"}],
        ),
        _record(
            instance_id="django__task-a",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            _policy_memory_weight=0.4,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2}],
        ),
    ])

    summary = memory.routing_prior_summary("django__new-task", WorkflowSegment.CONTEXT)

    assert summary["starter_attempts"] == 0.4
    assert summary["strongest_starter_action"] == "default"


def test_weak_task_starter_prior_does_not_override_repo_frontload() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__repo-a",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
            ],
        ),
        _record(
            instance_id="sympy__repo-a",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=False,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"}],
        ),
        _record(
            instance_id="sympy__repo-b",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
            ],
        ),
        _record(
            instance_id="sympy__repo-b",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=False,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"}],
        ),
        _record(
            instance_id="sympy__weak-task",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            _policy_memory_weight=0.35,
            turn_traces=[{"workflow_segment": "Context", "backend_tier": 2, "final_backend": "tier2"}],
        ),
        _record(
            instance_id="sympy__weak-task",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=False,
            _policy_memory_weight=0.35,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"}],
        ),
    ])

    summary = memory.routing_prior_summary("sympy__weak-task", WorkflowSegment.CONTEXT)

    assert summary["starter_memory_source"] == "repo"
    assert summary["starter_attempts"] >= 2.0
    assert summary["strongest_starter_action"] == "frontload_strongest"


def test_low_budget_only_frontload_rate_does_not_create_starter_action() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__task-a",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"workflow_segment": "Context", "backend_tier": 2, "final_backend": "tier2"},
                {"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
            ],
        ),
        _record(
            instance_id="sympy__task-a",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=False,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"}],
        ),
    ])

    summary = memory.routing_prior_summary("sympy__new-task", WorkflowSegment.CONTEXT)

    assert summary["starter_bo_frontload_rate"] < 0.4
    assert summary["strongest_starter_action"] == "default"


def test_budget_only_cheaper_success_extends_strongest_starter_window() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__task-a",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.20,
            turn_traces=[
                {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"},
            ],
        ),
        _record(
            instance_id="sympy__task-a",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.90,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"}],
        ),
    ])

    task_summary = memory.routing_prior_summary("sympy__task-a", WorkflowSegment.CONTEXT)
    repo_summary = memory.routing_prior_summary("sympy__new-task", WorkflowSegment.CONTEXT)

    assert task_summary["starter_memory_source"] == "task"
    assert task_summary["starter_budgetflow_expensive_success_weight"] == 1.0
    assert task_summary["starter_success_cost_ratio"] == 4.5
    assert task_summary["strongest_starter_action"] == "frontload_strongest"
    assert task_summary["strongest_starter_window"] == 4
    assert repo_summary["starter_memory_source"] == "repo"
    assert repo_summary["strongest_starter_window"] == 2


def test_unproductive_budgetflow_starter_shortens_frontload_window() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__task-a",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
            ],
        ),
        _record(
            instance_id="sympy__task-a",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=False,
            turn_traces=[
                {
                    "workflow_segment": "Context",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "strongest_starter_applied": True,
                    "has_progress": False,
                    "action_has_progress": False,
                    "billable_cost": 0.06,
                }
            ],
        ),
    ])

    summary = memory.routing_prior_summary("sympy__new-task", WorkflowSegment.CONTEXT)

    assert summary["starter_budgetflow_applied_weight"] == 1.0
    assert summary["starter_budgetflow_applied_failure_weight"] == 1.0
    assert summary["starter_budgetflow_success_rate"] == 0.0
    assert summary["starter_budgetflow_t3_productive_rate"] == 0.0
    assert summary["starter_budgetflow_t3_no_progress_cost"] == 0.06
    assert summary["strongest_starter_action"] == "frontload_strongest"
    assert summary["strongest_starter_window"] == 1


def test_repeated_unproductive_budgetflow_starter_disables_frontload() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id=f"sympy__task-{i}",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
            ],
        )
        for i in range(2)
    ] + [
        _record(
            instance_id=f"sympy__task-{i}",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=False,
            turn_traces=[
                {
                    "workflow_segment": "Context",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "strongest_starter_applied": True,
                    "has_progress": False,
                    "action_has_progress": False,
                    "billable_cost": 0.08,
                }
            ],
        )
        for i in range(2)
    ])

    summary = memory.routing_prior_summary("sympy__new-task", WorkflowSegment.CONTEXT)

    assert summary["starter_attempts"] == 2.0
    assert summary["starter_budgetflow_applied_weight"] == 2.0
    assert summary["starter_budgetflow_t3_no_progress_cost"] == 0.16
    assert summary["strongest_starter_action"] == "default"
    assert summary["strongest_starter_window"] == 0


def test_verified_starter_success_prevents_turn_level_no_progress_from_disabling_frontload() -> None:
    memory = PolicyMemory()
    records = []
    for i, resolved in enumerate([True, True, False, False]):
        records.append(_record(
            instance_id=f"sympy__task-{i}",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
                {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
            ],
        ))
        records.append(_record(
            instance_id=f"sympy__task-{i}",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=resolved,
            failure_class="pass" if resolved else "repair_fail",
            turn_traces=[
                {
                    "workflow_segment": "Context",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "strongest_starter_applied": True,
                    "has_progress": False,
                    "action_has_progress": False,
                    "billable_cost": 0.08,
                }
            ],
        ))
    memory.rebuild_from_records(records)

    summary = memory.routing_prior_summary("sympy__new-task", WorkflowSegment.CONTEXT)

    assert summary["starter_budgetflow_applied_success_weight"] == 2.0
    assert summary["starter_budgetflow_applied_failure_weight"] == 2.0
    assert summary["starter_budgetflow_success_rate"] == 0.5
    assert summary["starter_budgetflow_t3_productive_rate"] == 0.0
    assert summary["strongest_starter_action"] == "frontload_strongest"
    assert summary["strongest_starter_window"] == 3


def test_budget_only_equal_cost_success_does_not_create_starter_evidence() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__task-a",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.20,
            turn_traces=[{"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"}],
        ),
        _record(
            instance_id="sympy__task-a",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.25,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"}],
        ),
    ])

    summary = memory.routing_prior_summary("sympy__new-task", WorkflowSegment.CONTEXT)

    assert summary["starter_attempts"] == 0
    assert summary["strongest_starter_action"] == "default"


def test_policy_memory_learns_value_triggered_escalation_policy() -> None:
    memory = PolicyMemory()
    bad_t3_trace = {
        "workflow_segment": "Action",
        "backend_tier": 3,
        "final_backend": "tier3",
        "value_triggered_escalation_active": True,
        "has_progress": False,
        "action_has_progress": False,
        "billable_cost": 0.08,
    }
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="segment_value_aware",
            turn_traces=[bad_t3_trace],
        ),
        _record(
            instance_id="django__django-2",
            routing="segment_value_aware",
            turn_traces=[bad_t3_trace],
        ),
    ])

    summary = memory.routing_prior_summary("django__django-3", WorkflowSegment.ACTION)

    assert summary["escalation_memory_source"] == "repo"
    assert summary["escalation_attempts"] == 2
    assert summary["t3_productive_rate"] == 0.0
    assert summary["t3_no_progress_cost"] == 0.16
    assert summary["value_triggered_escalation_action"] == "disable_value_triggered_escalation"
    assert summary["value_triggered_escalation_window"] == 0


def test_low_weight_value_triggered_escalation_does_not_disable_policy() -> None:
    memory = PolicyMemory()
    bad_t3_trace = {
        "workflow_segment": "Action",
        "backend_tier": 3,
        "final_backend": "tier3",
        "value_triggered_escalation_active": True,
        "has_progress": False,
        "action_has_progress": False,
        "billable_cost": 0.08,
    }
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="segment_value_aware",
            turn_traces=[bad_t3_trace],
            _policy_memory_weight=0.4,
        ),
        _record(
            instance_id="django__django-2",
            routing="segment_value_aware",
            turn_traces=[bad_t3_trace],
            _policy_memory_weight=0.4,
        ),
    ])

    summary = memory.routing_prior_summary("django__django-3", WorkflowSegment.ACTION)

    assert summary["escalation_attempts"] == 0.8
    assert summary["t3_no_progress_cost"] == 0.064
    assert summary["value_triggered_escalation_action"] == "default"


def test_policy_memory_shortens_after_one_costly_unproductive_escalation() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="segment_value_aware",
            turn_traces=[
                {
                    "workflow_segment": "Action",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "value_triggered_escalation_active": True,
                    "has_progress": False,
                    "action_has_progress": False,
                    "billable_cost": 0.08,
                }
            ],
        )
    ])

    summary = memory.routing_prior_summary("django__django-2", WorkflowSegment.ACTION)

    assert summary["escalation_memory_source"] == "repo"
    assert summary["escalation_attempts"] == 1
    assert summary["value_triggered_escalation_action"] == "shorten_value_triggered_escalation"
    assert summary["value_triggered_escalation_window"] == 1


def test_policy_memory_uses_current_action_progress_for_t3_productivity() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="segment_value_aware",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {
                    "workflow_segment": "Action",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "value_triggered_escalation_active": True,
                    "has_progress": False,
                    "action_has_progress": True,
                    "action_progress_reason": "action_repair_pattern",
                    "billable_cost": 0.08,
                }
            ],
        )
    ])

    summary = memory.routing_prior_summary("django__django-2", WorkflowSegment.ACTION)

    assert summary["t3_productive_rate"] == 1.0
    assert summary["t3_no_progress_cost"] == 0.0
    assert summary["value_triggered_escalation_action"] == "extend_value_triggered_escalation"


def test_policy_memory_does_not_treat_unknown_progress_as_negative_evidence() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="segment_value_aware",
            turn_traces=[
                {
                    "workflow_segment": "Action",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "value_triggered_escalation_active": True,
                    "action_progress_state": "unknown",
                    "billable_cost": 0.08,
                }
            ],
        )
    ])

    summary = memory.routing_prior_summary("django__django-2", WorkflowSegment.ACTION)

    assert summary["escalation_attempts"] == 1
    assert summary["t3_productive_rate"] == 0.0
    assert summary["t3_no_progress_cost"] == 0.0
    assert summary["value_triggered_escalation_action"] == "default"


def test_policy_memory_treats_any_progress_channel_as_productive() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="segment_value_aware",
            turn_traces=[
                {
                    "workflow_segment": "Action",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "value_triggered_escalation_active": True,
                    "progress_state": "progress",
                    "action_progress_state": "no_progress",
                    "billable_cost": 0.08,
                }
            ],
        )
    ])

    summary = memory.routing_prior_summary("django__django-2", WorkflowSegment.ACTION)

    assert summary["escalation_attempts"] == 1
    assert summary["t3_productive_rate"] == 1.0
    assert summary["t3_no_progress_cost"] == 0.0
    assert summary["value_triggered_escalation_action"] == "default"


def test_rebuild_from_jsonl_sets_source_and_ignores_bad_lines(tmp_path: Path) -> None:
    source = tmp_path / "run.jsonl"
    source.write_text(json.dumps(_pass_record(instance_id="django__django-1")) + "\nnot-json\n")

    memory = PolicyMemory()
    memory.rebuild_from_jsonl(source)

    assert memory._source_path == str(source)
    assert memory.task_prior("django__django-1").seen == 1
    assert memory.routing_prior_summary("django__django-1")["policy_memory_source"] == str(source)


def test_auto_budget_dry_run_exposes_escalation_memory_decision(tmp_path: Path) -> None:
    policy_memory = tmp_path / "routing_memory.jsonl"
    policy_memory.write_text(json.dumps(_record(
        instance_id="sympy__sympy-14774",
        routing="segment_value_aware",
        turn_traces=[
            {
                "workflow_segment": "Action",
                "backend_tier": 3,
                "final_backend": "tier3",
                "value_triggered_escalation_active": True,
                "has_progress": False,
                "action_has_progress": False,
                "billable_cost": 0.08,
            }
        ],
    )) + "\n")
    env = {
        **os.environ,
        "NO_COLOR": "1",
        "PYTHONPATH": f"{ROOT / 'src'}:{ROOT.parent / 'external' / 'mini-swe-agent' / 'src'}",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budgetflow.run_mini_swe_compare",
            "--ids",
            "sympy__sympy-14774",
            "--strategies",
            "budgetflow_segment",
            "--auto-budget",
            "--auto-budget-dry-run",
            "--auto-budget-memory",
            "data/runs/auto_budget_memory.jsonl",
            "--policy-memory",
            str(policy_memory),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "[policy_memory] loaded from" in result.stdout
    policy_line = next(line for line in result.stdout.splitlines() if "policy_memory=on source=" in line)
    assert str(policy_memory) in policy_line
    assert "shorten_value_triggered_escalation" in result.stdout
    assert "/w=1" in result.stdout


def test_budgetflow_segment_routing_contributes_to_starter_prior() -> None:
    """budgetflow_segment must learn from budget_only frontload evidence same as other budgetflow strategies."""
    bo_t3_frontload = [
        {"workflow_segment": "Context", "backend_tier": 3, "final_backend": "tier3"},
        {"workflow_segment": "Action", "backend_tier": 3, "final_backend": "tier3"},
        {"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"},
    ]
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__task-bf-full",
            routing="budget_only",
            strategy="budget_only_baseline",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.15,
            turn_traces=bo_t3_frontload,
        ),
        _record(
            instance_id="django__task-bf-full",
            routing="segment_value_aware",
            strategy="budgetflow_segment",
            harness_resolved=False,
            total_cost=0.60,
            turn_traces=[{"workflow_segment": "Action", "backend_tier": 2, "final_backend": "tier2"}],
        ),
    ])

    summary = memory.routing_prior_summary("django__new-bf-full", WorkflowSegment.CONTEXT)
    starter, source = memory.starter_prior("django__new-bf-full")

    assert source == "repo"
    assert starter.attempts >= 1.0
    assert starter.budget_only_successes >= 1.0
    assert starter.budgetflow_failures >= 1.0
    assert summary["starter_attempts"] >= 1.0
    assert summary["strongest_starter_action"] == "frontload_strongest"
    assert summary["strongest_starter_window"] >= 2

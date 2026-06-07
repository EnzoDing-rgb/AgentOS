from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from budgetflow.adaptive_routing import AdaptiveRoutingState, rescue_state_for_strategy
from budgetflow.policy_memory import PolicyMemory
from budgetflow.types import Stage

ROOT = Path(__file__).resolve().parents[1]


def _record(**overrides) -> dict:
    record = {
        "instance_id": "sympy__sympy-10001",
        "strategy": "budgetflow_value_aware_tight",
        "routing": "budgetflow_value_aware",
        "harness_resolved": False,
        "failure_class": "repair_fail",
        "total_cost": 0.10,
        "backend_picks": ["tier2", "tier2"],
        "turn_traces": [
            {"stage": "REPAIR", "backend_tier": 2, "has_progress": False},
        ],
    }
    record.update(overrides)
    return record


def _pass_record(**overrides) -> dict:
    return _record(
        harness_resolved=True,
        failure_class="pass",
        backend_picks=["tier2"],
        turn_traces=[{"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True}],
        **overrides,
    )


def test_policy_memory_rebuilds_task_repo_and_routing_priors() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _pass_record(instance_id="sympy__sympy-1", total_cost=0.05),
        _record(instance_id="sympy__sympy-2", total_cost=0.20),
        _record(instance_id="sympy__sympy-2", total_cost=0.30, backend_picks=["tier3"]),
    ])

    task = memory.task_prior("sympy__sympy-2")
    repo = memory.repo_prior("sympy__sympy-1")
    summary = memory.routing_prior_summary("sympy__sympy-2", Stage.REPAIR)

    assert task.seen == 2
    assert task.pass_count == 0
    assert repo.total_tasks == 2
    assert repo.t2_turns > 0
    assert repo.t3_turns > 0
    assert summary["task_seen"] == 2
    assert summary["repo_t2_success"] >= 0.0
    assert "learned_action" in summary
    assert "regret_threshold" in summary


def test_policy_memory_preserves_generic_tier_evidence() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__sympy-1",
            harness_resolved=True,
            failure_class="pass",
            backend_picks=["tier2_balanced", "tier4", "tier5", "tier5"],
            turn_traces=[
                {"stage": "REPAIR", "backend_tier": 4},
                {"stage": "REPAIR", "backend_tier": 5},
            ],
        )
    ])

    repo = memory.repo_prior("sympy__sympy-1")
    task = memory.task_prior("sympy__sympy-1")
    summary = memory.routing_prior_summary("sympy__sympy-1", Stage.REPAIR)

    assert dict(repo.tier_turns) == {2: 1, 4: 1, 5: 2}
    assert dict(task.tier_turns) == {2: 1, 4: 1, 5: 2}
    assert summary["repo_tier_turns"] == {"2": 1, "4": 1, "5": 2}
    assert summary["stage_tier_success"] == {"4": 1.0, "5": 1.0}
    assert summary["repo_t3_success"] == 0


def test_policy_memory_learns_t1_t2_actions_from_prior_runs() -> None:
    records = [
        _record(instance_id="repair__task-a", backend_picks=["tier2"]),
        _record(instance_id="repair__task-b", backend_picks=["tier2"]),
        _record(instance_id="repair__task-c", backend_picks=["tier2"]),
        _record(instance_id="cost__task-a", routing="budgetflow_value_aware", total_cost=0.35),
        _record(instance_id="cost__task-a", routing="budget_only", strategy="budget_only_tight", total_cost=0.05),
        _record(instance_id="cost__task-b", routing="budgetflow_value_aware", total_cost=0.30),
        _record(instance_id="cost__task-b", routing="budget_only", strategy="budget_only_tight", total_cost=0.06),
    ]
    memory = PolicyMemory()
    memory.rebuild_from_records(records)

    assert memory.routing_prior_summary("repair__task-a", Stage.REPAIR)["learned_action"] == "early_rescue"
    assert memory.routing_prior_summary("cost__task-a", Stage.REPAIR)["learned_action"] == "cap_strongest"


def test_low_weight_stage_evidence_does_not_drive_learned_actions() -> None:
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

    repair = memory.routing_prior_summary("repo__new-repair", Stage.REPAIR)
    localization = memory.routing_prior_summary("repo__new-loc", Stage.LOCALIZATION)

    assert repair["stage_tier_weight"]["2"] == 0.5
    assert repair["learned_action"] == "default"
    assert localization["stage_tier_weight"]["2"] == 0.5
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

    summary = memory.routing_prior_summary("repo__same-task", Stage.REPAIR)

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

    summary = memory.routing_prior_summary("repo__same-task", Stage.REPAIR)

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

    summary = memory.routing_prior_summary("repo__same-task", Stage.REPAIR)

    assert summary["task_all_pro_failure_weight"] == 0.8
    assert summary["learned_action"] == "default"


def test_weighted_tier_success_uses_effective_evidence_denominator() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _pass_record(instance_id="repo__loc-a", _policy_memory_weight=0.35),
    ])

    summary = memory.routing_prior_summary("repo__loc-b", Stage.LOCALIZATION)

    assert summary["repo_evidence_weight"] == 0.35
    assert summary["repo_tier_success"]["2"] == 1.0
    assert summary["stage_tier_success"]["2"] == 1.0


def test_policy_memory_changes_runtime_rescue_and_starting_tier() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(instance_id="repo__repair-a", backend_picks=["tier2"]),
        _record(instance_id="repo__repair-b", backend_picks=["tier2"]),
        _record(instance_id="repo__repair-c", backend_picks=["tier2"]),
        _pass_record(instance_id="repo__loc-a"),
        _pass_record(instance_id="repo__loc-b"),
    ])

    rescue = rescue_state_for_strategy("budgetflow_value_aware", memory, "repo__repair-a")
    state = AdaptiveRoutingState(strategy_name="budgetflow_value_aware_tight", policy_memory=memory)
    state.set_task_context("repo__loc-a")

    assert rescue.trigger_turns < 6
    assert state.starting_tier() == 2
    assert state.prior_summary_for_trace() is not None


def test_policy_memory_can_imitate_budget_only_strongest_starter_window() -> None:
    bo_t3_frontload = [
        {"stage": "LOCALIZATION", "backend_tier": 3, "final_backend": "tier3"},
        {"stage": "REPAIR", "backend_tier": 3, "final_backend": "tier3"},
    ]
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__task-a",
            routing="budget_only",
            strategy="budget_only_tight",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=bo_t3_frontload,
        ),
        _record(
            instance_id="django__task-a",
            routing="budgetflow_value_aware",
            strategy="budgetflow_value_aware_tight",
            turn_traces=[{"stage": "REPAIR", "backend_tier": 2}],
        ),
    ])

    summary = memory.routing_prior_summary("django__new-task", Stage.LOCALIZATION)
    state = AdaptiveRoutingState(strategy_name="budgetflow_value_aware_tight", policy_memory=memory)
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
            strategy="budget_only_tight",
            harness_resolved=True,
            failure_class="pass",
            _policy_memory_weight=0.4,
            turn_traces=[{"stage": "LOCALIZATION", "backend_tier": 3, "final_backend": "tier3"}],
        ),
        _record(
            instance_id="django__task-a",
            routing="budgetflow_value_aware",
            strategy="budgetflow_value_aware_tight",
            _policy_memory_weight=0.4,
            turn_traces=[{"stage": "REPAIR", "backend_tier": 2}],
        ),
    ])

    summary = memory.routing_prior_summary("django__new-task", Stage.LOCALIZATION)

    assert summary["starter_attempts"] == 0.4
    assert summary["strongest_starter_action"] == "default"


def test_budget_only_cheaper_success_extends_strongest_starter_window() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="sympy__task-a",
            routing="budget_only",
            strategy="budget_only_tight",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.20,
            turn_traces=[
                {"stage": "LOCALIZATION", "backend_tier": 3, "final_backend": "tier3"},
                {"stage": "REPAIR", "backend_tier": 3, "final_backend": "tier3"},
                {"stage": "REPAIR", "backend_tier": 3, "final_backend": "tier3"},
                {"stage": "REPAIR", "backend_tier": 2, "final_backend": "tier2"},
            ],
        ),
        _record(
            instance_id="sympy__task-a",
            routing="budgetflow_value_aware",
            strategy="budgetflow_value_aware_tight",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.90,
            turn_traces=[{"stage": "REPAIR", "backend_tier": 2, "final_backend": "tier2"}],
        ),
    ])

    task_summary = memory.routing_prior_summary("sympy__task-a", Stage.LOCALIZATION)
    repo_summary = memory.routing_prior_summary("sympy__new-task", Stage.LOCALIZATION)

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
            strategy="budget_only_tight",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"stage": "LOCALIZATION", "backend_tier": 3, "final_backend": "tier3"},
                {"stage": "REPAIR", "backend_tier": 3, "final_backend": "tier3"},
            ],
        ),
        _record(
            instance_id="sympy__task-a",
            routing="budgetflow_value_aware",
            strategy="budgetflow_value_aware_tight",
            harness_resolved=False,
            turn_traces=[
                {
                    "stage": "LOCALIZATION",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "strongest_starter_applied": True,
                    "has_progress": False,
                    "billable_cost": 0.06,
                }
            ],
        ),
    ])

    summary = memory.routing_prior_summary("sympy__new-task", Stage.LOCALIZATION)

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
            strategy="budget_only_tight",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"stage": "LOCALIZATION", "backend_tier": 3, "final_backend": "tier3"},
                {"stage": "REPAIR", "backend_tier": 3, "final_backend": "tier3"},
            ],
        )
        for i in range(2)
    ] + [
        _record(
            instance_id=f"sympy__task-{i}",
            routing="budgetflow_value_aware",
            strategy="budgetflow_value_aware_tight",
            harness_resolved=False,
            turn_traces=[
                {
                    "stage": "LOCALIZATION",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "strongest_starter_applied": True,
                    "has_progress": False,
                    "billable_cost": 0.08,
                }
            ],
        )
        for i in range(2)
    ])

    summary = memory.routing_prior_summary("sympy__new-task", Stage.LOCALIZATION)

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
            strategy="budget_only_tight",
            harness_resolved=True,
            failure_class="pass",
            turn_traces=[
                {"stage": "LOCALIZATION", "backend_tier": 3, "final_backend": "tier3"},
                {"stage": "REPAIR", "backend_tier": 3, "final_backend": "tier3"},
            ],
        ))
        records.append(_record(
            instance_id=f"sympy__task-{i}",
            routing="budgetflow_value_aware",
            strategy="budgetflow_value_aware_tight",
            harness_resolved=resolved,
            failure_class="pass" if resolved else "repair_fail",
            turn_traces=[
                {
                    "stage": "LOCALIZATION",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "strongest_starter_applied": True,
                    "has_progress": False,
                    "billable_cost": 0.08,
                }
            ],
        ))
    memory.rebuild_from_records(records)

    summary = memory.routing_prior_summary("sympy__new-task", Stage.LOCALIZATION)

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
            strategy="budget_only_tight",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.20,
            turn_traces=[{"stage": "LOCALIZATION", "backend_tier": 3, "final_backend": "tier3"}],
        ),
        _record(
            instance_id="sympy__task-a",
            routing="budgetflow_value_aware",
            strategy="budgetflow_value_aware_tight",
            harness_resolved=True,
            failure_class="pass",
            total_cost=0.25,
            turn_traces=[{"stage": "REPAIR", "backend_tier": 2, "final_backend": "tier2"}],
        ),
    ])

    summary = memory.routing_prior_summary("sympy__new-task", Stage.LOCALIZATION)

    assert summary["starter_attempts"] == 0
    assert summary["strongest_starter_action"] == "default"


def test_policy_memory_learns_value_triggered_escalation_policy() -> None:
    memory = PolicyMemory()
    bad_t3_trace = {
        "stage": "REPAIR",
        "backend_tier": 3,
        "final_backend": "tier3",
        "value_triggered_escalation_active": True,
        "has_progress": False,
        "billable_cost": 0.08,
    }
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="budgetflow_value_aware",
            turn_traces=[bad_t3_trace],
        ),
        _record(
            instance_id="django__django-2",
            routing="budgetflow_value_aware",
            turn_traces=[bad_t3_trace],
        ),
    ])

    summary = memory.routing_prior_summary("django__django-3", Stage.REPAIR)

    assert summary["escalation_memory_source"] == "repo"
    assert summary["escalation_attempts"] == 2
    assert summary["t3_productive_rate"] == 0.0
    assert summary["t3_no_progress_cost"] == 0.16
    assert summary["value_triggered_escalation_action"] == "disable_value_triggered_escalation"
    assert summary["value_triggered_escalation_window"] == 0


def test_low_weight_value_triggered_escalation_does_not_disable_policy() -> None:
    memory = PolicyMemory()
    bad_t3_trace = {
        "stage": "REPAIR",
        "backend_tier": 3,
        "final_backend": "tier3",
        "value_triggered_escalation_active": True,
        "has_progress": False,
        "billable_cost": 0.08,
    }
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="budgetflow_value_aware",
            turn_traces=[bad_t3_trace],
            _policy_memory_weight=0.4,
        ),
        _record(
            instance_id="django__django-2",
            routing="budgetflow_value_aware",
            turn_traces=[bad_t3_trace],
            _policy_memory_weight=0.4,
        ),
    ])

    summary = memory.routing_prior_summary("django__django-3", Stage.REPAIR)

    assert summary["escalation_attempts"] == 0.8
    assert summary["t3_no_progress_cost"] == 0.064
    assert summary["value_triggered_escalation_action"] == "default"


def test_policy_memory_shortens_after_one_costly_unproductive_escalation() -> None:
    memory = PolicyMemory()
    memory.rebuild_from_records([
        _record(
            instance_id="django__django-1",
            routing="budgetflow_value_aware",
            turn_traces=[
                {
                    "stage": "REPAIR",
                    "backend_tier": 3,
                    "final_backend": "tier3",
                    "value_triggered_escalation_active": True,
                    "has_progress": False,
                    "billable_cost": 0.08,
                }
            ],
        )
    ])

    summary = memory.routing_prior_summary("django__django-2", Stage.REPAIR)

    assert summary["escalation_memory_source"] == "repo"
    assert summary["escalation_attempts"] == 1
    assert summary["value_triggered_escalation_action"] == "shorten_value_triggered_escalation"
    assert summary["value_triggered_escalation_window"] == 1


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
        routing="budgetflow_value_aware",
        turn_traces=[
            {
                "stage": "REPAIR",
                "backend_tier": 3,
                "final_backend": "tier3",
                "value_triggered_escalation_active": True,
                "has_progress": False,
                "billable_cost": 0.08,
            }
        ],
    )) + "\n")
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT.parent / 'external' / 'mini-swe-agent' / 'src'}"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budgetflow.run_mini_swe_compare",
            "--ids",
            "sympy__sympy-14774",
            "--strategies",
            "budgetflow_value_aware_tight",
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

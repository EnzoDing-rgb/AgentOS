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

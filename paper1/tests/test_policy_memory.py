"""Tests for PolicyMemory / RoutingPrior — rebuild, priors, regret, rescue adjustment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import pytest
from budgetflow.policy_memory import (
    BudgetAccount,
    PolicyMemory,
    PolicyRegret,
    RepoPrior,
    TaskContext,
    TaskPrior,
    _extract_repo,
)
from budgetflow.adaptive_routing import (
    AdaptiveRoutingRegistry,
    AdaptiveRoutingState,
    EvidenceRescueState,
    rescue_state_for_strategy,
)
from budgetflow.types import Stage

# ── helpers ────────────────────────────────────────────────────────────────


def _record(**kw) -> dict:
    base = {
        "instance_id": "sympy__sympy-10001",
        "strategy": "budgetflow_full_tight",
        "routing": "budgetflow_full",
        "harness_resolved": False,
        "total_cost": 0.05,
        "failure_class": "repair_fail",
        "exit_status": "StagnationExit",
        "exit_reason": "stagnation_repeat_command",
        "backend_picks": ["tier2", "tier2", "tier3"],
        "turn_traces": [
            {"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True},
            {"stage": "REPAIR", "backend_tier": 2, "has_progress": False},
            {"stage": "REPAIR", "backend_tier": 3, "has_progress": False},
        ],
        "turn_trace_count": 3,
    }
    base.update(kw)
    return base


def _pass_record(**kw) -> dict:
    return _record(harness_resolved=True, failure_class="pass", exit_status="Submitted", exit_reason="submitted", **kw)


# ── extract_repo ───────────────────────────────────────────────────────────


def test_extract_repo_sympy() -> None:
    assert _extract_repo("sympy__sympy-14774") == "sympy"


def test_extract_repo_django() -> None:
    assert _extract_repo("django__django-10924") == "django"


def test_extract_repo_no_separator() -> None:
    assert _extract_repo("simple-task") == "simple-task"


# ── TaskContext / BudgetAccount ─────────────────────────────────────────────


def test_task_context_from_instance_id() -> None:
    ctx = TaskContext.from_instance_id("sympy__sympy-14774")
    assert ctx.repo == "sympy"
    assert ctx.instance_id == "sympy__sympy-14774"
    assert ctx.task_type == "swebench"


def test_budget_account_defaults() -> None:
    acct = BudgetAccount()
    assert acct.remaining_budget == float("inf")


# ── PolicyMemory rebuild ───────────────────────────────────────────────────


def test_policy_memory_rebuilds_from_records() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(instance_id="sympy__sympy-1", total_cost=0.03, backend_picks=["tier2"]),
        _pass_record(instance_id="sympy__sympy-1", total_cost=0.04, backend_picks=["tier2", "tier3"]),
        _record(instance_id="sympy__sympy-2", total_cost=0.08, backend_picks=["tier2", "tier2", "tier3"]),
    ]
    pm.rebuild_from_records(records)

    repo = pm.repo_prior("sympy__sympy-1")
    assert repo.total_tasks == 2
    assert repo.pass_count == 2
    assert repo.t2_turns > 0
    assert repo.t3_turns > 0

    task1 = pm.task_prior("sympy__sympy-1")
    assert task1.seen == 2
    assert task1.pass_count == 2

    task2 = pm.task_prior("sympy__sympy-2")
    assert task2.seen == 1
    assert task2.pass_count == 0


def test_policy_memory_empty_records() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([])
    assert len(pm._repo_priors) == 0


def test_policy_memory_skips_bad_lines() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([{"bad": "record"}])
    # No instance_id, so skipped
    assert len(pm._task_priors) == 0


# ── Repo prior ─────────────────────────────────────────────────────────────


def test_repo_prior_t2_t3_success_rate() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(instance_id="repo__task-1", backend_picks=["tier2", "tier2"]),
        _record(instance_id="repo__task-2", backend_picks=["tier2", "tier3"]),
        _record(instance_id="repo__task-2", backend_picks=["tier3"]),
    ]
    pm.rebuild_from_records(records)
    prior = pm.repo_prior("repo__task-1")
    # Task-1: T2 only, pass → T2 success. Task-2: T2+T3, fail twice
    assert 0 < prior.t2_success_rate <= 1.0
    assert prior.t3_success_rate == 0.0


def test_repo_prior_t3_success_when_resolved() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(instance_id="repo__task-3", backend_picks=["tier3", "tier3"]),
    ]
    pm.rebuild_from_records(records)
    prior = pm.repo_prior("repo__task-3")
    assert prior.t3_success_rate == 1.0


def test_repo_prior_stage_success() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(
            instance_id="repo__task-4",
            backend_picks=["tier2"],
            turn_traces=[
                {"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True},
                {"stage": "REPAIR", "backend_tier": 2, "has_progress": True},
            ],
        ),
    ]
    pm.rebuild_from_records(records)
    prior = pm.repo_prior("repo__task-4")
    assert prior.t2_stage_success.get("localization", 0) == 1.0
    assert prior.t2_stage_success.get("repair", 0) == 1.0


def test_repo_prior_median_cost() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-5", total_cost=0.10),
        _record(instance_id="repo__task-5", total_cost=0.20),
        _record(instance_id="repo__task-5", total_cost=0.30),
    ]
    pm.rebuild_from_records(records)
    prior = pm.repo_prior("repo__task-5")
    assert prior.median_cost == pytest.approx(0.20)


# ── Task prior ─────────────────────────────────────────────────────────────


def test_task_prior_seen_and_pass() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(instance_id="repo__task-10"),
        _record(instance_id="repo__task-10"),
        _record(instance_id="repo__task-10"),
    ]
    pm.rebuild_from_records(records)
    task = pm.task_prior("repo__task-10")
    assert task.seen == 3
    assert task.pass_count == 1


def test_task_prior_all_pro_failures() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-11", strategy="all_pro", routing="all_pro"),
        _record(instance_id="repo__task-11", strategy="all_pro", routing="all_pro"),
        _pass_record(instance_id="repo__task-11", strategy="all_pro", routing="all_pro"),
    ]
    pm.rebuild_from_records(records)
    task = pm.task_prior("repo__task-11")
    assert task.all_pro_failures == 2


def test_task_prior_tier_turns() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-12", backend_picks=["tier2", "tier2", "tier3"]),
    ]
    pm.rebuild_from_records(records)
    task = pm.task_prior("repo__task-12")
    assert task.tier_turns[2] == 2
    assert task.tier_turns[3] == 1


def test_task_prior_failure_classes() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-13", failure_class="repair_fail"),
        _record(instance_id="repo__task-13", failure_class="repair_fail"),
        _record(instance_id="repo__task-13", failure_class="loc_fail"),
    ]
    pm.rebuild_from_records(records)
    task = pm.task_prior("repo__task-13")
    assert task.failure_classes["repair_fail"] == 2
    assert task.failure_classes["loc_fail"] == 1


# ── Policy regret ──────────────────────────────────────────────────────────


def test_full_vs_tight_regret_no_data() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([_record()])
    regret = pm.policy_regret("sympy__sympy-10001")
    assert regret is not None
    assert regret.regret == 0.0


def test_full_vs_tight_regret_positive_when_full_more_expensive() -> None:
    pm = PolicyMemory()
    records = [
        _record(
            instance_id="repo__task-20", routing="budgetflow_full",
            strategy="budgetflow_full_tight", total_cost=0.15, harness_resolved=False,
        ),
        _record(
            instance_id="repo__task-20", routing="budget_only",
            strategy="budget_only_tight", total_cost=0.05, harness_resolved=False,
        ),
    ]
    pm.rebuild_from_records(records)
    regret = pm.policy_regret("repo__task-20")
    assert regret.regret > 0


def test_full_vs_tight_regret_zero_when_full_better() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(
            instance_id="repo__task-21", routing="budgetflow_full",
            strategy="budgetflow_full_tight", total_cost=0.03,
        ),
        _record(
            instance_id="repo__task-21", routing="budget_only",
            strategy="budget_only_tight", total_cost=0.05, harness_resolved=False,
        ),
    ]
    pm.rebuild_from_records(records)
    regret = pm.policy_regret("repo__task-21")
    # Full passes + cheaper → no regret
    assert regret.regret == 0.0


def test_full_vs_tight_regret_high_when_full_30pct_more() -> None:
    pm = PolicyMemory()
    records = [
        _record(
            instance_id="repo__task-22", routing="budgetflow_full",
            strategy="budgetflow_full_loose", total_cost=0.20, harness_resolved=False,
        ),
        _record(
            instance_id="repo__task-22", routing="budget_only",
            strategy="budget_only_tight", total_cost=0.05, harness_resolved=False,
        ),
    ]
    pm.rebuild_from_records(records)
    regret = pm.policy_regret("repo__task-22")
    # full=0.20, tight=0.05, full > 1.3x tight → regret
    assert regret.regret > 0


# ── routing_prior_summary ──────────────────────────────────────────────────


def test_routing_prior_summary_includes_all_fields() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(instance_id="repo__task-30", total_cost=0.05, backend_picks=["tier2", "tier2"]),
    ]
    pm.rebuild_from_records(records)
    summary = pm.routing_prior_summary("repo__task-30", Stage.REPAIR)
    assert "repo_t2_success" in summary
    assert "repo_t3_success" in summary
    assert "task_seen" in summary
    assert "recent_failure_axis" in summary
    assert "full_vs_tight_regret" in summary
    assert "learned_action" in summary
    assert "stage_t2_success" in summary
    assert "stage_t3_success" in summary


def test_routing_prior_summary_learned_action_early_rescue() -> None:
    pm = PolicyMemory()
    # T2 repair fails on 3 different tasks → low T2 repair success
    records = []
    for i in range(3):
        records.append(_record(
            instance_id=f"repo__task-4{i}",
            backend_picks=["tier2", "tier2"],
            turn_traces=[
                {"stage": "REPAIR", "backend_tier": 2, "has_progress": False},
                {"stage": "REPAIR", "backend_tier": 2, "has_progress": False},
            ],
        ))
    pm.rebuild_from_records(records)
    summary = pm.routing_prior_summary("repo__task-40", Stage.REPAIR)
    assert summary["learned_action"] == "early_rescue"


def test_routing_prior_summary_learned_action_reduce_rescue() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-50", strategy="all_pro", routing="all_pro", backend_picks=["tier3"]),
        _record(instance_id="repo__task-50", strategy="all_pro", routing="all_pro", backend_picks=["tier3"]),
    ]
    pm.rebuild_from_records(records)
    summary = pm.routing_prior_summary("repo__task-50", Stage.REPAIR)
    assert summary["learned_action"] == "reduce_rescue"


def test_routing_prior_summary_learned_action_cap_t3() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-60", routing="budgetflow_full", total_cost=0.35),
        _record(instance_id="repo__task-60", routing="budget_only", total_cost=0.05),
        _record(instance_id="repo__task-61", routing="budgetflow_full", total_cost=0.30),
        _record(instance_id="repo__task-61", routing="budget_only", total_cost=0.06),
    ]
    pm.rebuild_from_records(records)
    summary = pm.routing_prior_summary("repo__task-60", Stage.REPAIR)
    assert summary["learned_action"] == "cap_t3"


def test_routing_prior_summary_protocol_issue() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-70", failure_class="extract_fail"),
        _record(instance_id="repo__task-70", failure_class="extract_fail"),
    ]
    pm.rebuild_from_records(records)
    summary = pm.routing_prior_summary("repo__task-70", Stage.REPAIR)
    assert summary["learned_action"] == "protocol_issue"


def test_routing_prior_summary_start_t2() -> None:
    pm = PolicyMemory()
    records = [
        _pass_record(
            instance_id="repo__task-80",
            backend_picks=["tier2"],
            turn_traces=[{"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True}],
        ),
        _pass_record(
            instance_id="repo__task-81",
            backend_picks=["tier2"],
            turn_traces=[{"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True}],
        ),
    ]
    pm.rebuild_from_records(records)
    summary = pm.routing_prior_summary("repo__task-80", Stage.LOCALIZATION)
    assert summary["learned_action"] == "start_t2"


# ── rescue_state_for_strategy with PolicyMemory ─────────────────────────────


def test_rescue_early_rescue_shortens_trigger() -> None:
    pm = PolicyMemory()
    records = []
    for i in range(3):
        records.append(_record(
            instance_id=f"repo__task-a{i}",
            backend_picks=["tier2"],
            turn_traces=[{"stage": "REPAIR", "backend_tier": 2, "has_progress": False}],
        ))
    pm.rebuild_from_records(records)
    rescue = rescue_state_for_strategy("budgetflow_full", pm, "repo__task-a0")
    assert rescue.trigger_turns < 6  # default is 6, early_rescue reduces by 3 → 3


def test_rescue_reduce_rescue_lengthens_trigger() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-b0", strategy="all_pro", routing="all_pro", backend_picks=["tier3"]),
        _record(instance_id="repo__task-b0", strategy="all_pro", routing="all_pro", backend_picks=["tier3"]),
    ]
    pm.rebuild_from_records(records)
    rescue = rescue_state_for_strategy("budgetflow_full", pm, "repo__task-b0")
    assert rescue.trigger_turns > 6  # default is 6, reduce_rescue adds 4 → 10


def test_rescue_cap_t3_shortens_window() -> None:
    pm = PolicyMemory()
    records = [
        _record(instance_id="repo__task-c0", routing="budgetflow_full", total_cost=0.35),
        _record(instance_id="repo__task-c0", routing="budget_only", total_cost=0.05),
        _record(instance_id="repo__task-c1", routing="budgetflow_full", total_cost=0.30),
        _record(instance_id="repo__task-c1", routing="budget_only", total_cost=0.06),
    ]
    pm.rebuild_from_records(records)
    rescue = rescue_state_for_strategy("budgetflow_full", pm, "repo__task-c0")
    assert rescue.window_turns < 3  # default is 3, cap_t3 reduces by 1 → 2
    assert rescue.stop_loss_turns < 6  # default is 6, cap_t3 tightens further


def test_rescue_no_policy_memory_returns_default() -> None:
    rescue = rescue_state_for_strategy("budgetflow_full", None, None)
    assert rescue.trigger_turns == 6
    assert rescue.window_turns == 3
    assert rescue.stop_loss_turns == 6


# ── AdaptiveRoutingState with PolicyMemory ──────────────────────────────────


def test_starting_tier_start_t2_from_policy() -> None:
    pm = PolicyMemory()
    # High T2 localization success → start_t2 action
    records = [
        _pass_record(
            instance_id="repo__task-d0",
            backend_picks=["tier2"],
            turn_traces=[{"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True}],
        ),
        _pass_record(
            instance_id="repo__task-d1",
            backend_picks=["tier2"],
            turn_traces=[{"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True}],
        ),
    ]
    pm.rebuild_from_records(records)

    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight", policy_memory=pm)
    state.set_task_context("repo__task-d0")
    # start_t2 should make starting_tier return 2 even with 0 fails
    assert state.starting_tier() == 2


def test_starting_tier_still_capped_at_2() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    for _ in range(10):
        state.record_task(_record(harness_resolved=False))
    assert state.starting_tier() == 2


def test_set_task_context_rebuilds_rescue() -> None:
    pm = PolicyMemory()
    records = []
    for i in range(3):
        records.append(_record(
            instance_id=f"repo__task-e{i}",
            backend_picks=["tier2"],
            turn_traces=[{"stage": "REPAIR", "backend_tier": 2, "has_progress": False}],
        ))
    pm.rebuild_from_records(records)

    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight", policy_memory=pm)
    state.set_task_context("repo__task-e0")
    # early_rescue should have shortened trigger_turns
    assert state.rescue.trigger_turns < 6


def test_prior_summary_for_trace_after_set_task_context() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([
        _pass_record(instance_id="repo__task-f0", backend_picks=["tier2"]),
    ])
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight", policy_memory=pm)
    state.set_task_context("repo__task-f0")
    prior = state.prior_summary_for_trace()
    assert prior is not None
    assert "learned_action" in prior


def test_prior_summary_none_without_policy_memory() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    state.set_task_context("some-task")
    assert state.prior_summary_for_trace() is None


def test_reset_task_runtime_clears_prior_summary() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([
        _pass_record(instance_id="repo__task-g0", backend_picks=["tier2"]),
    ])
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight", policy_memory=pm)
    state.set_task_context("repo__task-g0")
    assert state.prior_summary_for_trace() is not None
    state.reset_task_runtime()
    assert state.prior_summary_for_trace() is None


# ── Dry-run on real JSONL ──────────────────────────────────────────────────


def test_policy_memory_rebuilds_from_postfix_017_jsonl() -> None:
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    pm = PolicyMemory()
    pm.rebuild_from_jsonl(jsonl)
    # Should have at least sympy repo
    assert "sympy" in pm._repo_priors
    repo = pm.repo_prior("sympy__sympy-14774")
    assert repo.total_tasks >= 1
    assert repo.pass_count >= 0
    # Every task should have been seen at least once
    task = pm.task_prior("sympy__sympy-14774")
    assert task.seen >= 1


def test_routing_prior_summary_from_real_data() -> None:
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    pm = PolicyMemory()
    pm.rebuild_from_jsonl(jsonl)
    summary = pm.routing_prior_summary("sympy__sympy-14774", Stage.REPAIR)
    assert isinstance(summary["repo_t2_success"], float)
    assert isinstance(summary["repo_t3_success"], float)
    assert summary["task_seen"] >= 1
    assert summary["learned_action"] in (
        "default", "early_rescue", "reduce_rescue", "cap_t3", "start_t2", "protocol_issue",
    )


def test_summary_lines_from_real_data() -> None:
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    pm = PolicyMemory()
    pm.rebuild_from_jsonl(jsonl)
    lines = pm.summary_lines()
    assert len(lines) >= 2  # header + at least one repo


# ── Warm-up gate equivalent checks ──────────────────────────────────────────


def test_gate_checks_fail_without_memory() -> None:
    """Simulates gate: without PolicyMemory, loaded=False should be detected."""
    # Gate requires policy_memory != None
    policy_memory = None
    loaded = policy_memory is not None
    records_ok = policy_memory is not None and policy_memory._record_count >= 10
    assert not loaded
    assert not records_ok


def test_gate_checks_pass_with_postfix_017() -> None:
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    pm = PolicyMemory()
    pm.rebuild_from_jsonl(jsonl)
    assert pm._record_count >= 10
    assert len(pm._repo_priors) >= 1
    assert len(pm._task_priors) >= 10


def test_gate_sympy_17630_not_early_rescue() -> None:
    """sympy-17630 has all_pro failures + extract_fail → should be protocol_issue, not early_rescue."""
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    pm = PolicyMemory()
    pm.rebuild_from_jsonl(jsonl)
    summary = pm.routing_prior_summary("sympy__sympy-17630")
    action = summary["learned_action"]
    # With extract_fail + all_pro failures, protocol_issue takes priority over early_rescue
    assert action != "early_rescue", f"sympy-17630 should not be early_rescue (all_pro failures present), got {action}"


# ── Regret threshold ────────────────────────────────────────────────────────


def test_regret_threshold_from_defaults() -> None:
    from budgetflow.defaults import POLICY_REGRET_THRESHOLD
    pm = PolicyMemory()
    assert pm.regret_threshold == POLICY_REGRET_THRESHOLD


def test_regret_threshold_configurable() -> None:
    pm = PolicyMemory(regret_threshold=0.30)
    assert pm.regret_threshold == 0.30
    # Verify it's used in routing_prior_summary
    records = [
        _record(instance_id="r__t-c0", routing="budgetflow_full", total_cost=0.35),
        _record(instance_id="r__t-c0", routing="budget_only", total_cost=0.05),
    ]
    pm.rebuild_from_records(records)
    summary = pm.routing_prior_summary("r__t-c0")
    assert summary["regret_threshold"] == 0.30
    # With threshold 0.30, regret of 0.13 won't trigger cap_t3
    # (regret would be: full_avg=0.35, tight_avg=0.05, same task comparision...)
    # Actually these are same instance_id so regret is computed within the _build_policy_regret


def test_regret_threshold_cli_override_affects_cap_t3() -> None:
    """Higher threshold → fewer cap_t3 actions."""
    records = [
        _record(instance_id="r__t-d0", routing="budgetflow_full", total_cost=0.35),
        _record(instance_id="r__t-d0", routing="budget_only", total_cost=0.05),
        _record(instance_id="r__t-d1", routing="budgetflow_full", total_cost=0.25),
        _record(instance_id="r__t-d1", routing="budget_only", total_cost=0.03),
    ]
    # With default 0.15 threshold → cap_t3 triggers
    pm_default = PolicyMemory()
    pm_default.rebuild_from_records(records)
    assert pm_default.routing_prior_summary("r__t-d0")["learned_action"] == "cap_t3"

    # With high 0.50 threshold → no cap_t3
    pm_high = PolicyMemory(regret_threshold=0.50)
    pm_high.rebuild_from_records(records)
    assert pm_high.routing_prior_summary("r__t-d0")["learned_action"] != "cap_t3"


# ── Routing prior summary includes trace fields ─────────────────────────────


def test_routing_prior_summary_has_regret_threshold_and_source() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([
        _pass_record(instance_id="r__t-e0", backend_picks=["tier2"]),
    ])
    summary = pm.routing_prior_summary("r__t-e0")
    assert "regret_threshold" in summary
    assert "policy_memory_source" in summary
    assert summary["regret_threshold"] == pm.regret_threshold


def test_policy_memory_source_set_after_rebuild() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([_pass_record(instance_id="r__t-f0")])
    # When built from records (not JSONL), source should be empty
    assert pm._source_path == ""


# ── AdaptiveRoutingRegistry with PolicyMemory ───────────────────────────────


def test_registry_gets_policy_memory_from_constructor() -> None:
    from budgetflow.adaptive_routing import AdaptiveRoutingRegistry
    pm = PolicyMemory()
    pm.rebuild_from_records([
        _pass_record(instance_id="r__t-g0", backend_picks=["tier2"]),
    ])
    registry = AdaptiveRoutingRegistry(policy_memory=pm)
    state = registry.for_strategy("budgetflow_full_tight", "budgetflow_full")
    assert state is not None
    assert state.policy_memory is pm


def test_set_task_context_writes_prior_summary() -> None:
    pm = PolicyMemory()
    pm.rebuild_from_records([
        _pass_record(instance_id="r__t-h0", backend_picks=["tier2", "tier2"]),
    ])
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight", policy_memory=pm)
    state.set_task_context("r__t-h0")
    prior = state.prior_summary_for_trace()
    assert prior is not None
    assert "learned_action" in prior
    assert "repo_t2_success" in prior
    assert "task_seen" in prior
    assert "regret_threshold" in prior
    assert "policy_memory_source" in prior


def test_policy_memory_disabled_record_has_false_flag() -> None:
    """Simulate _run_one: when adaptive has no prior, policy_memory_enabled=False."""
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    state.set_task_context("some-task")
    prior = state.prior_summary_for_trace()
    # Without PolicyMemory, prior summary should be None
    assert prior is None
    # Simulate what _run_one writes: record["policy_memory_enabled"] = False
    policy_memory_enabled = prior is not None
    assert not policy_memory_enabled


# ── Gate-only subprocess tests ───────────────────────────────────────────────


def _gate_cli_cmd(*extra_args: str) -> list[str]:
    return [
        sys.executable, "-m", "budgetflow.run_mini_swe_compare",
        "--policy-memory-gate-only",
        *extra_args,
    ]


def test_auto_budget_dry_run_loads_default_policy_memory_source() -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "budgetflow.run_mini_swe_compare",
            "--ids", "sympy__sympy-14774",
            "--strategies", "budgetflow_value_aware_tight",
            "--auto-budget",
            "--auto-budget-dry-run",
            "--auto-budget-memory", "data/runs/auto_budget_memory.jsonl",
        ],
        capture_output=True, text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": f"{ROOT/'src'}:{ROOT/'..'/'external'/'mini-swe-agent'/'src'}"},
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "[policy_memory] loaded from" in result.stdout
    policy_line = next(line for line in result.stdout.splitlines() if "policy_memory=on source=" in line)
    assert "auto_budget_memory.jsonl" not in policy_line


def test_gate_only_without_policy_memory_exits_1() -> None:
    """gate-only without --policy-memory should exit 1."""
    result = subprocess.run(
        _gate_cli_cmd(),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": f"{ROOT/'src'}:{ROOT/'..'/'external'/'mini-swe-agent'/'src'}"},
    )
    assert result.returncode == 1, f"stderr: {result.stderr}"


def test_gate_only_with_postfix_017_exits_0() -> None:
    """gate-only with postfix_017 JSONL should exit 0 (all checks pass)."""
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    result = subprocess.run(
        _gate_cli_cmd("--policy-memory", str(jsonl)),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": f"{ROOT/'src'}:{ROOT/'..'/'external'/'mini-swe-agent'/'src'}"},
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_gate_only_does_not_check_provider_signatures() -> None:
    """gate-only output must not contain 'preflight' (no provider check)."""
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    result = subprocess.run(
        _gate_cli_cmd("--policy-memory", str(jsonl)),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": f"{ROOT/'src'}:{ROOT/'..'/'external'/'mini-swe-agent'/'src'}"},
    )
    assert "preflight" not in result.stdout, f"gate-only should not hit provider check\nstdout:\n{result.stdout}"
    assert "preflight" not in result.stderr, f"gate-only should not hit provider check\nstderr:\n{result.stderr}"


def test_gate_only_prints_run_id_via_gate_not_compare() -> None:
    """gate-only output must not contain 'run_id=compare' (no misleading run header)."""
    jsonl = ROOT / "data" / "runs" / "postfix_017_10x5-0.jsonl"
    if not jsonl.is_file():
        pytest.skip("postfix_017 JSONL not found")
    result = subprocess.run(
        _gate_cli_cmd("--policy-memory", str(jsonl)),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": f"{ROOT/'src'}:{ROOT/'..'/'external'/'mini-swe-agent'/'src'}"},
    )
    assert "run_id=compare" not in result.stdout, (
        f"gate-only should not print misleading run_id=compare_...\nstdout:\n{result.stdout}"
    )
    assert "out=" not in result.stdout, (
        f"gate-only should not print misleading out=...\nstdout:\n{result.stdout}"
    )
    assert "checkpoint=" not in result.stdout, (
        f"gate-only should not print misleading checkpoint=...\nstdout:\n{result.stdout}"
    )

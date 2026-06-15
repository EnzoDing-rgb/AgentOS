from __future__ import annotations

from argparse import Namespace

import pytest

from budgetflow.experiments.compare_config import CompareStrategy, task_set_kind
from budgetflow.experiments.compare_setup import (
    build_batch_budget_modes,
    load_tasks_for_compare,
    resolve_budget_plan,
    resolve_task_count,
    select_strategies,
    trace_console_from_args,
)


def _args(**overrides):
    base = dict(
        preset="3x3",
        limit=None,
        task_set="easy",
        budget=None,
        pressure_init=None,
        pressure_max=None,
        budget_scale=1.0,
        max_overrun=0.0,
        trace_verbose=False,
        trace_quiet=False,
        strategies=None,
        strategy_set=None,
        jobs=None,
        ids=None,
    )
    base.update(overrides)
    return Namespace(**base)


def test_resolve_task_count_medium_defaults_to_15() -> None:
    assert resolve_task_count(_args(task_set="medium")) == 15
    assert resolve_task_count(_args(task_set="medium", limit=4)) == 4


def test_medium_task_set_uses_medium_pool_not_3x3_preset() -> None:
    args = _args(task_set="medium")
    tasks = load_tasks_for_compare(args, tasks_n=resolve_task_count(args))

    assert len(tasks) == 15
    assert {task.instance_id for task in tasks} != {
        "sympy__sympy-13480",
        "sympy__sympy-20212",
        "sympy__sympy-16988",
    }


def test_task_set_kind_labels_experiment_groups() -> None:
    assert task_set_kind(task_set="easy") == "familiar"
    assert task_set_kind(task_set="medium") == "unseen"
    assert task_set_kind(task_set="easy", ids="repo__task") == "custom"


def test_budget_plan_uses_defaults_and_scales() -> None:
    plan = resolve_budget_plan(_args(budget=2.0, budget_scale=2.0), tasks_n=3)

    assert plan.constrained == 4.0
    assert plan.max_overrun == 0.0


def test_trace_console_priority() -> None:
    assert trace_console_from_args(_args()) == "milestones"
    assert trace_console_from_args(_args(trace_quiet=True)) == "quiet"
    assert trace_console_from_args(_args(trace_quiet=True, trace_verbose=True)) == "verbose"


def test_3x3_selects_mechanism_isolation_strategies_and_parallel_jobs() -> None:
    selection = select_strategies(_args(jobs=1))
    names = {s.name for s in selection.strategies}

    assert names == {
        "bare_t3_baseline",
        "enterprise_router_baseline",
        "budgetflow_same_enterprise_router",
    }
    assert selection.policy_jobs == 3
    assert selection.jobs_upgraded is True


def test_custom_ids_default_to_paper_mainline_six_policy_set() -> None:
    selection = select_strategies(_args(ids="sympy__sympy-22714", jobs=1))
    names = [s.name for s in selection.strategies]

    assert names == [
        "bare_t2_baseline",
        "bare_t3_baseline",
        "enterprise_router_baseline",
        "budgetflow_same_enterprise_router",
        "budgetflow_task_level",
        "budgetflow_segment",
    ]
    assert selection.policy_jobs == 6
    assert selection.jobs_upgraded is True


def test_non_3x3_preset_defaults_to_paper_mainline_not_full_catalog() -> None:
    selection = select_strategies(_args(preset="5x5", jobs=6))
    names = [s.name for s in selection.strategies]

    assert names == [
        "bare_t2_baseline",
        "bare_t3_baseline",
        "enterprise_router_baseline",
        "budgetflow_same_enterprise_router",
        "budgetflow_task_level",
        "budgetflow_segment",
    ]


def test_explicit_strategy_set_file_controls_order(tmp_path) -> None:
    import json
    strategy_set = tmp_path / "strategies.json"
    strategy_set.write_text(json.dumps({
        "strategies": [
            {"name": "budgetflow_task_level"},
            {"name": "bare_t2_baseline"},
        ]
    }))

    selection = select_strategies(_args(strategy_set=str(strategy_set), jobs=1))

    assert [s.name for s in selection.strategies] == [
        "budgetflow_task_level",
        "bare_t2_baseline",
    ]
    assert selection.policy_jobs == 2


def test_unknown_strategy_name_fails_fast() -> None:
    try:
        select_strategies(_args(strategies="not_a_policy"))
    except SystemExit as exc:
        assert "unknown strategies" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_batch_budget_modes_distinguish_dynamic_caps() -> None:
    strategies = (
        CompareStrategy("budgetflow_segment", "segment_value_aware"),
        CompareStrategy("all_pro", "all_pro", budgeted=False),
    )
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps={"t1": 0.1, "t2": 0.2},
        constrained_budget=1.0,
    )

    assert modes.batch_caps["budgetflow_segment"] == pytest.approx(0.3)
    assert modes.budget_modes["budgetflow_segment"] == "dynamic_task_caps"
    assert modes.batch_caps["all_pro"] is None
    assert modes.budget_modes["all_pro"] == "shared"


def test_batch_budget_modes_frozen_router_caps_for_mechanism_strategies() -> None:
    """enterprise_router and budgetflow_same_enterprise_router get frozen_router_caps mode."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
        CompareStrategy("budgetflow_same_enterprise_router", "budgetflow_same_router"),
        CompareStrategy("bare_t3_baseline", "bare_t3"),
    )
    frozen_caps = {"task-a": 0.25, "task-b": 0.50}
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=None,
        constrained_budget=1.0,
        frozen_task_caps=frozen_caps,
    )

    assert modes.budget_modes["enterprise_router_baseline"] == "frozen_router_caps"
    assert modes.budget_modes["budgetflow_same_enterprise_router"] == "frozen_router_caps"
    assert modes.budget_modes["bare_t3_baseline"] == "shared"
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(0.75)
    assert modes.batch_caps["budgetflow_same_enterprise_router"] == pytest.approx(0.75)
    assert modes.batch_caps["bare_t3_baseline"] == pytest.approx(1.0)


def test_resolve_budget_plan_from_budget_plan_json(tmp_path) -> None:
    """When --budget-plan is provided and --budget is not set, use hard_cap_usd."""
    import json
    bp_path = tmp_path / "bp.json"
    bp_path.write_text(json.dumps({
        "hard_cap_usd": 1.2262,
        "budget_mode": "target_utilization",
        "decision": "PASS",
    }))

    plan = resolve_budget_plan(
        _args(budget_plan=str(bp_path)),
        tasks_n=20,
    )
    assert plan.constrained == 1.2262, f"expected 1.2262, got {plan.constrained}"
    assert "budget_plan" in plan.source, f"source should mention budget_plan, got {plan.source}"


def test_resolve_budget_plan_explicit_budget_overrides_budget_plan(tmp_path) -> None:
    """--budget on CLI wins over --budget-plan hard_cap_usd."""
    import json
    bp_path = tmp_path / "bp.json"
    bp_path.write_text(json.dumps({"hard_cap_usd": 1.2262}))

    plan = resolve_budget_plan(
        _args(budget=5.0, budget_plan=str(bp_path)),
        tasks_n=20,
    )
    assert plan.constrained == 5.0
    assert plan.source == "cli"


def test_resolve_budget_plan_frozen_fallback_when_no_budget_plan(tmp_path) -> None:
    """When --budget-plan is absent, frozen plan cap sum still works."""
    import json
    fp_path = tmp_path / "fp.json"
    fp_path.write_text(json.dumps({
        "plan": {
            "task-a": {"base_cap": 1.5, "preferred_model": "tier2", "priority": 1},
            "task-b": {"base_cap": 2.0, "preferred_model": "tier3", "priority": 2},
        }
    }))

    plan = resolve_budget_plan(
        _args(), tasks_n=2,
        frozen_plan_path=str(fp_path),
        task_ids=["task-a", "task-b"],
    )
    assert plan.constrained == 3.5
    assert plan.source == "frozen_plan_cap_sum"


def test_batch_budget_modes_frozen_caps_override_dynamic_caps() -> None:
    """frozen_task_caps take priority over auto_budget_task_caps for mechanism strategies."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
        CompareStrategy("budgetflow_segment", "segment_value_aware"),
    )
    frozen_caps = {"task-a": 0.25}
    auto_caps = {"task-a": 0.99}
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=auto_caps,
        constrained_budget=1.0,
        frozen_task_caps=frozen_caps,
    )

    assert modes.budget_modes["enterprise_router_baseline"] == "frozen_router_caps"
    assert modes.budget_modes["budgetflow_segment"] == "dynamic_task_caps"
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(0.25)
    assert modes.batch_caps["budgetflow_segment"] == pytest.approx(0.99)


def test_target_utilization_scales_frozen_caps_to_constrained_budget() -> None:
    """In target_utilization mode, frozen per-task caps are scaled so sum = hard_cap."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
        CompareStrategy("budgetflow_same_enterprise_router", "budgetflow_same_router"),
        CompareStrategy("bare_t3_baseline", "bare_t3"),
        CompareStrategy("budgetflow_segment", "segment_value_aware"),
    )
    frozen_caps = {"task-a": 2.0, "task-b": 3.0, "task-c": 5.0}  # sum = 10.0
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=None,
        constrained_budget=2.0,  # target_utilization hard_cap
        frozen_task_caps=frozen_caps,
        budget_mode="target_utilization",
    )

    # Scaled sum = 2.0 (not 10.0)
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(2.0)
    assert modes.batch_caps["budgetflow_same_enterprise_router"] == pytest.approx(2.0)
    # Non-frozen strategies still get constrained_budget
    assert modes.batch_caps["bare_t3_baseline"] == pytest.approx(2.0)
    assert modes.batch_caps["budgetflow_segment"] == pytest.approx(2.0)

    # effective_frozen_caps are scaled proportionally
    eff = modes.effective_frozen_caps
    assert eff is not None
    assert eff["task-a"] == pytest.approx(0.4)   # 2.0 * (2/10)
    assert eff["task-b"] == pytest.approx(0.6)   # 3.0 * (2/10)
    assert eff["task-c"] == pytest.approx(1.0)   # 5.0 * (2/10)
    assert sum(eff.values()) == pytest.approx(2.0)


def test_target_utilization_no_scaling_when_sum_already_matches() -> None:
    """When frozen cap sum already equals constrained_budget, no scaling needed."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
    )
    frozen_caps = {"task-a": 1.0, "task-b": 1.0}  # sum = 2.0
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=None,
        constrained_budget=2.0,
        frozen_task_caps=frozen_caps,
        budget_mode="target_utilization",
    )
    # effective_frozen_caps is the original dict (no scaling)
    assert modes.effective_frozen_caps is frozen_caps
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(2.0)


def test_legacy_mode_does_not_scale_frozen_caps() -> None:
    """Without target_utilization, frozen caps keep their raw sum."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
    )
    frozen_caps = {"task-a": 2.0, "task-b": 3.0}  # sum = 5.0
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=None,
        constrained_budget=1.0,
        frozen_task_caps=frozen_caps,
        # no budget_mode → legacy
    )
    # Legacy: frozen cap sum = 5.0, not constrained_budget 1.0
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(5.0)
    # effective_frozen_caps is the original unmodified dict
    assert modes.effective_frozen_caps is frozen_caps

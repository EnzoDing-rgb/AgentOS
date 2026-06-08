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
        "bare_strong_model",
        "enterprise_router_baseline",
        "budgetflow_same_router",
    }
    assert selection.policy_jobs == 3
    assert selection.jobs_upgraded is True


def test_unknown_strategy_name_fails_fast() -> None:
    try:
        select_strategies(_args(strategies="not_a_policy"))
    except SystemExit as exc:
        assert "unknown strategies" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_batch_budget_modes_distinguish_dynamic_caps() -> None:
    strategies = (
        CompareStrategy("budgetflow_full", "budgetflow_value_aware"),
        CompareStrategy("all_pro", "all_pro", budgeted=False),
    )
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps={"t1": 0.1, "t2": 0.2},
        constrained_budget=1.0,
    )

    assert modes.batch_caps["budgetflow_full"] == pytest.approx(0.3)
    assert modes.budget_modes["budgetflow_full"] == "dynamic_task_caps"
    assert modes.batch_caps["all_pro"] is None
    assert modes.budget_modes["all_pro"] == "shared"


def test_batch_budget_modes_frozen_router_caps_for_mechanism_strategies() -> None:
    """enterprise_router and budgetflow_same_router get frozen_router_caps mode."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
        CompareStrategy("budgetflow_same_router", "budgetflow_same_router"),
        CompareStrategy("bare_strong_model", "bare_strong"),
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
    assert modes.budget_modes["budgetflow_same_router"] == "frozen_router_caps"
    assert modes.budget_modes["bare_strong_model"] == "shared"
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(0.75)
    assert modes.batch_caps["budgetflow_same_router"] == pytest.approx(0.75)
    assert modes.batch_caps["bare_strong_model"] == pytest.approx(1.0)


def test_batch_budget_modes_frozen_caps_override_dynamic_caps() -> None:
    """frozen_task_caps take priority over auto_budget_task_caps for mechanism strategies."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
        CompareStrategy("budgetflow_full", "budgetflow_value_aware"),
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
    assert modes.budget_modes["budgetflow_full"] == "dynamic_task_caps"
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(0.25)
    assert modes.batch_caps["budgetflow_full"] == pytest.approx(0.99)

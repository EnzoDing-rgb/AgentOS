from __future__ import annotations

from argparse import Namespace

import pytest

from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.experiments.compare_setup import (
    build_batch_budget_modes,
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
        loose=None,
        tight=None,
        pressure_init=None,
        pressure_max=None,
        tight_scale=1.0,
        loose_scale=1.0,
        max_overrun=0.0,
        trace_verbose=False,
        trace_quiet=False,
        strategies=None,
        jobs=None,
    )
    base.update(overrides)
    return Namespace(**base)


def test_resolve_task_count_medium_defaults_to_15() -> None:
    assert resolve_task_count(_args(task_set="medium")) == 15
    assert resolve_task_count(_args(task_set="medium", limit=4)) == 4


def test_budget_plan_uses_defaults_and_scales() -> None:
    plan = resolve_budget_plan(_args(tight=2.0, loose=5.0, tight_scale=2.0), tasks_n=3)

    assert plan.tight == 4.0
    assert plan.loose == 5.0
    assert plan.max_overrun == 0.0
    assert plan.budget_caps == {"loose": 5.0, "tight": 4.0}


def test_trace_console_priority() -> None:
    assert trace_console_from_args(_args()) == "milestones"
    assert trace_console_from_args(_args(trace_quiet=True)) == "quiet"
    assert trace_console_from_args(_args(trace_quiet=True, trace_verbose=True)) == "verbose"


def test_3x3_selects_canonical_diagnostic_strategies_and_parallel_jobs() -> None:
    selection = select_strategies(_args(jobs=1))
    names = {s.name for s in selection.strategies}

    assert names == {
        "budget_only_tight",
        "budgetflow_full_tight",
        "budgetflow_equal_weight_tight",
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
        CompareStrategy("budgetflow_value_aware_tight", "budgetflow_value_aware", "tight"),
        CompareStrategy("all_pro", "all_pro", None),
    )
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps={"t1": 0.1, "t2": 0.2},
        budget_caps={"tight": 1.0, "loose": 2.0},
    )

    assert modes.batch_caps["budgetflow_value_aware_tight"] == pytest.approx(0.3)
    assert modes.budget_modes["budgetflow_value_aware_tight"] == "dynamic_task_caps"
    assert modes.batch_caps["all_pro"] is None
    assert modes.budget_modes["all_pro"] == "shared"

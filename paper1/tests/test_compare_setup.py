from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest
import budgetflow.experiments.compare_setup as compare_setup

from budgetflow.experiments.compare_cli import parse_compare_args
from budgetflow.experiments.compare_config import (
    CompareStrategy,
    required_backends_for_strategies,
    task_set_kind,
)
from budgetflow.experiments.compare_memory import build_auto_budget_plan
from budgetflow.experiments.compare_setup import (
    build_batch_budget_modes,
    calibrated_model_fit_from_budget_plan,
    load_tasks_for_compare,
    resolve_budget_plan,
    resolve_task_count,
    select_strategies,
    trace_console_from_args,
    validate_paper_mainline_budget_contract,
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


def test_load_tasks_preserves_registered_task_order(monkeypatch) -> None:
    hard_first = SimpleNamespace(
        instance_id="repo__hard_first",
        patch="\n".join(str(i) for i in range(25)),
        fail_to_pass=["a", "b", "c"],
        pass_to_pass=["x", "y"],
    )
    easy_second = SimpleNamespace(
        instance_id="repo__easy_second",
        patch="one-line",
        fail_to_pass=[],
        pass_to_pass=[],
    )
    monkeypatch.setattr(
        compare_setup,
        "load_compare_medium_tasks",
        lambda tasks_n: [hard_first, easy_second],
    )

    tasks = load_tasks_for_compare(_args(task_set="medium"), tasks_n=2)

    assert [task.instance_id for task in tasks] == [
        "repo__hard_first",
        "repo__easy_second",
    ]


def test_task_set_kind_labels_experiment_groups() -> None:
    assert task_set_kind(task_set="easy") == "familiar"
    assert task_set_kind(task_set="medium") == "unseen"
    assert task_set_kind(task_set="easy", ids="repo__task") == "custom"


def test_budget_plan_uses_defaults_and_scales() -> None:
    plan = resolve_budget_plan(_args(budget=2.0, budget_scale=2.0))

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


def test_mainline_provider_preflight_matches_t2_t3_runtime_pool() -> None:
    selection = select_strategies(_args(ids="sympy__sympy-22714"))

    assert required_backends_for_strategies(selection.strategies) == ["tier2", "tier3"]


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
    assert modes.budget_modes["all_pro"] == "unconstrained"


def test_resolve_budget_plan_from_budget_plan_json(tmp_path) -> None:
    """When --budget-plan is provided and --budget is not set, use hard_cap_usd."""
    import json
    bp_path = tmp_path / "bp.json"
    bp_path.write_text(json.dumps({
        "hard_cap_usd": 1.2262,
        "generation_mode": "target_utilization",
        "decision": "PASS",
    }))

    plan = resolve_budget_plan(
        _args(budget_plan=str(bp_path)),
    )
    assert plan.constrained == 1.2262, f"expected 1.2262, got {plan.constrained}"
    assert "budget_plan" in plan.source, f"source should mention budget_plan, got {plan.source}"


def test_budget_plan_model_fit_evidence_parsed_as_global_runtime_signal(tmp_path) -> None:
    import json

    bp_path = tmp_path / "bp.json"
    bp_path.write_text(json.dumps({
        "hard_cap_usd": 1.2262,
        "generation_mode": "target_utilization",
        "model_fit_evidence": {
            "source": "historical_jsonl",
            "confidence": "medium",
            "tier_fit": {"2": 0.08, "3": 0.65},
        },
    }))

    fit, source = calibrated_model_fit_from_budget_plan(bp_path)

    assert fit == {"tier2": 0.08, "tier3": 0.65}
    assert source == "budget_plan:historical_jsonl"


def test_resolve_budget_plan_explicit_budget_overrides_budget_plan(tmp_path) -> None:
    """--budget on CLI wins over --budget-plan hard_cap_usd."""
    import json
    bp_path = tmp_path / "bp.json"
    bp_path.write_text(json.dumps({"hard_cap_usd": 1.2262}))

    plan = resolve_budget_plan(
        _args(budget=5.0, budget_plan=str(bp_path)),
    )
    assert plan.constrained == 5.0
    assert plan.source == "cli"


def test_batch_budget_modes_dynamic_caps_apply_to_all_strategies() -> None:
    """auto_budget_task_caps apply to all budgeted strategies equally."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
        CompareStrategy("budgetflow_segment", "segment_value_aware"),
    )
    auto_caps = {"task-a": 0.99}
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=auto_caps,
        constrained_budget=1.0,
    )

    assert modes.budget_modes["enterprise_router_baseline"] == "dynamic_task_caps"
    assert modes.budget_modes["budgetflow_segment"] == "dynamic_task_caps"
    assert modes.batch_caps["enterprise_router_baseline"] == pytest.approx(0.99)
    assert modes.batch_caps["budgetflow_segment"] == pytest.approx(0.99)


def test_frozen_router_plan_does_not_create_separate_batch_caps() -> None:
    """Frozen router plans are passed to routing, not batch budget setup."""
    strategies = (
        CompareStrategy("enterprise_router_baseline", "enterprise_router"),
        CompareStrategy("budgetflow_same_enterprise_router", "budgetflow_same_router"),
        CompareStrategy("bare_t3_baseline", "bare_t3"),
        CompareStrategy("budgetflow_segment", "segment_value_aware"),
    )
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=None,
        constrained_budget=2.0,
    )

    for name in ("enterprise_router_baseline", "budgetflow_same_enterprise_router",
                 "bare_t3_baseline", "budgetflow_segment"):
        assert modes.batch_caps[name] == pytest.approx(2.0)
        assert modes.budget_modes[name] == "shared_batch_hard_budget"


def test_unbudgeted_strategy_gets_no_cap() -> None:
    """Unbudgeted strategies get None cap and unconstrained mode."""
    strategies = (
        CompareStrategy("all_pro", "all_pro", budgeted=False),
    )
    modes = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=None,
        auto_budget_task_caps=None,
        constrained_budget=1.0,
    )
    assert modes.batch_caps["all_pro"] is None
    assert modes.budget_modes["all_pro"] == "unconstrained"


def test_paper_mainline_budget_contract_blocks_mixed_cap_modes() -> None:
    selection = select_strategies(_args(ids="sympy__sympy-22714"))
    batch_caps = {strategy.name: 1.0 for strategy in selection.strategies}
    budget_modes = {strategy.name: "shared_batch_hard_budget" for strategy in selection.strategies}
    budget_modes["enterprise_router_baseline"] = "dynamic_task_caps"

    with pytest.raises(SystemExit, match="paper mainline requires shared_batch_hard_budget"):
        validate_paper_mainline_budget_contract(
            strategies=selection.strategies,
            batch_caps=batch_caps,
            budget_modes=budget_modes,
        )


def test_paper_mainline_budget_contract_blocks_unequal_caps() -> None:
    selection = select_strategies(_args(ids="sympy__sympy-22714"))
    batch_caps = {strategy.name: 1.0 for strategy in selection.strategies}
    batch_caps["budgetflow_same_enterprise_router"] = 0.1
    budget_modes = {strategy.name: "shared_batch_hard_budget" for strategy in selection.strategies}

    with pytest.raises(SystemExit, match="paper mainline requires equal shared batch caps"):
        validate_paper_mainline_budget_contract(
            strategies=selection.strategies,
            batch_caps=batch_caps,
            budget_modes=budget_modes,
        )


def test_retired_auto_budget_cli_flags_are_not_exposed() -> None:
    with pytest.raises(SystemExit):
        parse_compare_args(["--auto-budget"])
    with pytest.raises(SystemExit):
        parse_compare_args(["--budget-mode", "retired"])
    with pytest.raises(SystemExit):
        parse_compare_args(["--target-utilization", "0.9"])
    args = parse_compare_args([])
    assert args.auto_budget is False
    assert args.auto_budget_dry_run is False


def test_retired_auto_budget_does_not_enable_cost_memory_by_default(tmp_path) -> None:
    args = parse_compare_args([])
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        repo="sympy/sympy",
        patch="diff --git a/x.py b/x.py\n+line\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    plan = build_auto_budget_plan(args, tasks=[task], runs_dir=tmp_path)

    assert plan.memory is None
    assert plan.estimates == {}
    assert plan.task_caps is None
    assert not (tmp_path / "auto_budget_memory.jsonl").exists()

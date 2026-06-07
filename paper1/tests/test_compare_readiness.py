from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.experiments.compare_readiness import build_compare_readiness_report
from budgetflow.value_efficiency import ValueEfficiencyContext


def _args(**overrides):
    base = dict(
        preset="3x3",
        ids=None,
        task_set="easy",
        trace_turns=True,
    )
    base.update(overrides)
    return Namespace(**base)


def test_readiness_blocks_uncovered_non_equal_value_matrix(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text('{"tasks":{"covered":{"values":{"difficulty":0.2}}}}')
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="difficulty", value_matrix_path=str(matrix))

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="covered"), SimpleNamespace(instance_id="missing")],
        strategies=(CompareStrategy("budgetflow_value_aware_tight", "budgetflow_value_aware", "tight"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=True,
        auto_budget_caps={"covered": 0.1, "missing": 0.1},
    )

    assert not report.ok
    assert any("missing 1 selected task values" in issue for issue in report.blocking)


def test_readiness_warns_equal_value_bfv_is_not_t1_evidence() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a")],
        strategies=(CompareStrategy("budgetflow_value_aware_tight", "budgetflow_value_aware", "tight"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert report.ok
    assert any("not T1 value evidence" in warning for warning in report.warnings)


def test_readiness_blocks_underparallel_policy_jobs() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a")],
        strategies=(
            CompareStrategy("budget_only_tight", "budget_only", "tight"),
            CompareStrategy("budgetflow_value_aware_tight", "budgetflow_value_aware", "tight"),
        ),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert not report.ok
    assert any("policy_jobs=1" in issue for issue in report.blocking)

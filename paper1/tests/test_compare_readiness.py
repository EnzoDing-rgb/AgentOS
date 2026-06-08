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
        auto_budget_dry_run=False,
        allow_global_fallback_auto_budget=False,
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
        tasks=[
            SimpleNamespace(instance_id="covered", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="missing", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budgetflow_full", "budgetflow_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=True,
        auto_budget_caps={"covered": 0.1, "missing": 0.1},
    )

    assert not report.ok
    assert any("missing 1 selected task values" in issue for issue in report.blocking)
    assert "planned_policy_cap=0.2000" in report.facts
    assert "planned_total_cap=0.2000" in report.facts


def test_readiness_warns_equal_value_is_not_t1_evidence() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_full", "budgetflow_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert report.ok
    assert any("not T1 value evidence" in warning for warning in report.warnings)
    assert "value_source_class=equal_sanity" in report.facts
    assert "value_evidence=sanity_fallback" in report.facts
    assert "value_primary_t1=false" in report.facts


def test_readiness_warns_plain_matrix_is_not_primary_t1_evidence(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text('{"tasks":{"task-a":{"values":{"difficulty":0.2}}}}')
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="difficulty", value_matrix_path=str(matrix))

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_full", "budgetflow_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert report.ok
    assert "value_source_class=value_matrix_diagnostic" in report.facts
    assert "value_evidence=value_matrix_diagnostic" in report.facts
    assert "value_primary_t1=false" in report.facts
    assert any("not primary T1 evidence" in warning for warning in report.warnings)


def test_readiness_accepts_pre_registered_manual_as_primary_t1_evidence(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text('{"tasks":{"task-a":{"values":{"difficulty":0.2}}}}')
    value_context = ValueEfficiencyContext()
    value_context.init(
        value_profile="difficulty",
        value_matrix_path=str(matrix),
        value_source_kind="pre_registered_manual",
    )

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_full", "budgetflow_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert report.ok
    assert "value_source_class=pre_registered_manual" in report.facts
    assert "value_evidence=primary_t1" in report.facts
    assert "value_confidence=manual" in report.facts
    assert "value_primary_t1=true" in report.facts
    assert not any("not primary T1 evidence" in warning for warning in report.warnings)


def test_readiness_blocks_underparallel_policy_jobs() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(
            CompareStrategy("budget_only_baseline", "budget_only"),
            CompareStrategy("budgetflow_full", "budgetflow_value_aware"),
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


def test_readiness_blocks_skipping_provider_signature_check() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(no_provider_signature_check=True),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("bare_strong_model", "bare_strong"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert not report.ok
    assert any("--no-provider-signature-check is not allowed" in issue for issue in report.blocking)


def test_readiness_blocks_missing_frozen_plan_for_mechanism_router() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=None),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_same_router", "budgetflow_same_router"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert not report.ok
    assert any("require --frozen-plan" in issue for issue in report.blocking)


def test_readiness_blocks_frozen_plan_without_selected_task(tmp_path) -> None:
    plan = tmp_path / "frozen_plan.json"
    plan.write_text(
        '{"meta":{"name":"unit_plan"},"plan":{"task-a":{"preferred_model":"tier2","base_cap":0.2,"priority":1}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=str(plan)),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("enterprise_router_baseline", "enterprise_router"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert not report.ok
    assert "frozen_plan=unit_plan" in report.facts
    assert "frozen_plan_entries=1" in report.facts
    assert any("missing 1 selected tasks: task-b" in issue for issue in report.blocking)


def test_readiness_accepts_frozen_plan_covering_selected_tasks(tmp_path) -> None:
    plan = tmp_path / "frozen_plan.json"
    plan.write_text(
        '{"meta":{"name":"unit_plan"},"plan":{"task-a":{"preferred_model":"tier2","base_cap":0.2,"priority":1}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=str(plan)),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_same_router", "budgetflow_same_router"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert report.ok
    assert "frozen_plan=unit_plan" in report.facts
    assert "frozen_plan_entries=1" in report.facts
    assert "frozen_plan_planned_cap=0.2000" in report.facts


def test_readiness_blocks_budget_mismatch_with_frozen_plan_hard_cap(tmp_path) -> None:
    plan = tmp_path / "frozen_plan.json"
    plan.write_text(
        '{"meta":{"name":"unit_plan","hard_cap_usd":0.2},'
        '"plan":{"task-a":{"preferred_model":"tier2","base_cap":0.2,"priority":1}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=str(plan), budget=1.0),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_same_router", "budgetflow_same_router"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert not report.ok
    assert "frozen_plan_hard_cap=0.2000" in report.facts
    assert any("does not match frozen plan hard_cap_usd" in issue for issue in report.blocking)


def test_readiness_blocks_tasks_without_verifiable_harness_metadata() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="missing-test-patch", test_patch="", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="missing-f2p", test_patch="diff", fail_to_pass=()),
        ],
        strategies=(CompareStrategy("bare_strong_model", "bare_strong"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert not report.ok
    assert any("lack test_patch" in issue for issue in report.blocking)
    assert any("lack fail_to_pass" in issue for issue in report.blocking)


def test_readiness_blocks_malformed_frozen_plan(tmp_path) -> None:
    plan = tmp_path / "bad_frozen_plan.json"
    plan.write_text('{"meta":{"name":"bad"},"plan":{"task-a":{"preferred_model":"tier2","priority":1}}}')
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=str(plan)),
        tasks=[SimpleNamespace(instance_id="task-a")],
        strategies=(CompareStrategy("enterprise_router_baseline", "enterprise_router"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=False,
        auto_budget_caps=None,
    )

    assert not report.ok
    assert any("cannot load frozen router plan" in issue for issue in report.blocking)


def test_readiness_blocks_paid_run_when_auto_budget_has_no_memory_lift() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budget_only_baseline", "budget_only"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=True,
        auto_budget_caps={"task-a": 0.1, "task-b": 0.2},
        auto_budget_estimates={
            "task-a": SimpleNamespace(source="global_fallback", confidence="low"),
            "task-b": SimpleNamespace(source="global_fallback", confidence="low"),
        },
    )

    assert not report.ok
    assert any("dynamic task caps are all global_fallback" in issue for issue in report.blocking)


def test_readiness_allows_explicit_global_fallback_cap_diagnostic() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(allow_global_fallback_auto_budget=True),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budget_only_baseline", "budget_only"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        auto_budget_enabled=True,
        auto_budget_caps={"task-a": 0.1, "task-b": 0.2},
        auto_budget_estimates={
            "task-a": SimpleNamespace(source="global_fallback", confidence="low"),
            "task-b": SimpleNamespace(source="global_fallback", confidence="low"),
        },
    )

    assert report.ok
    assert any("dynamic task caps are all global_fallback" in warning for warning in report.warnings)

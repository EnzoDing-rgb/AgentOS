from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from budgetflow.experiments.compare_config import CompareStrategy, paper_mainline_strategies
from budgetflow.experiments.compare_readiness import build_compare_readiness_report
from budgetflow.model_tiers import DEFAULT_CATALOG_PATH, init_catalog
from budgetflow.value_efficiency import ValueEfficiencyContext


def _args(**overrides):
    base = dict(
        preset="3x3",
        ids=None,
        task_set="easy",
        trace_turns=True,
        diagnostic_catalog=False,
        frozen_plan=None,
    )
    base.update(overrides)
    return Namespace(**base)


def test_readiness_blocks_uncovered_non_equal_value_matrix(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text('{"tasks":{"covered":{"task_value":{"difficulty":0.2}}}}')
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="difficulty", value_matrix_path=str(matrix))

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="covered", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="missing", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("missing 1 selected task values" in issue for issue in report.blocking)


def test_readiness_warns_equal_value_is_not_t1_evidence() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert report.ok
    assert any("not T1 value evidence" in warning for warning in report.warnings)
    assert "value_source_class=equal_sanity" in report.facts
    assert "value_evidence=sanity_fallback" in report.facts
    assert "value_primary_t1=false" in report.facts


def test_readiness_warns_plain_matrix_is_not_primary_t1_evidence(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text('{"tasks":{"task-a":{"task_value":{"difficulty":0.2}}}}')
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="difficulty", value_matrix_path=str(matrix))

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert report.ok
    assert "value_source_class=value_matrix_diagnostic" in report.facts
    assert "value_evidence=value_matrix_diagnostic" in report.facts
    assert "value_primary_t1=false" in report.facts
    assert any("not primary T1 evidence" in warning for warning in report.warnings)


def test_readiness_accepts_pre_registered_manual_as_primary_t1_evidence(tmp_path) -> None:
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text('{"tasks":{"task-a":{"task_value":{"difficulty":0.2}}}}')
    value_context = ValueEfficiencyContext()
    value_context.init(
        value_profile="difficulty",
        value_matrix_path=str(matrix),
        value_source_kind="pre_registered_manual",
    )

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
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
            CompareStrategy("budgetflow_segment", "segment_value_aware"),
        ),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("policy_jobs=1" in issue for issue in report.blocking)


def test_paper_mainline_blocks_non_tool_call_catalog(monkeypatch) -> None:
    import budgetflow.experiments.compare_readiness as readiness

    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    class _Catalog:
        configs = (
            SimpleNamespace(backend="tier1", protocol="tool_call"),
            SimpleNamespace(backend="tier2", protocol="legacy_parser"),
            SimpleNamespace(backend="tier3", protocol="tool_call"),
        )

    monkeypatch.setattr(readiness, "MODEL_CATALOG", _Catalog())

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=paper_mainline_strategies(),
        policy_jobs=len(paper_mainline_strategies()),
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("requires native tool_call action protocol" in issue for issue in report.blocking)


def test_readiness_blocks_skipping_provider_signature_check() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(no_provider_signature_check=True),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("bare_t3_baseline", "bare_t3"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("--no-provider-signature-check is not allowed" in issue for issue in report.blocking)


def test_readiness_blocks_runtime_worktree_python_contamination(tmp_path, monkeypatch) -> None:
    import budgetflow.experiments.compare_readiness as readiness

    monkeypatch.setattr(
        readiness,
        "find_runtime_worktree_python_contamination",
        lambda runtime_root: [f"{tmp_path}/site-packages/stale.pth: /tmp/budgetflow-runtime/worktrees/repo/task"],
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("bare_t3_baseline", "bare_t3"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("runtime worktree paths" in issue for issue in report.blocking)


def test_readiness_blocks_missing_frozen_plan_for_mechanism_router() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=None),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_same_enterprise_router", "budgetflow_same_router"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("require --frozen-plan" in issue for issue in report.blocking)


def test_readiness_blocks_paper_mainline_without_budget_plan() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=paper_mainline_strategies(),
        policy_jobs=len(paper_mainline_strategies()),
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("Budget Regime Compiler" in issue for issue in report.blocking)


def test_readiness_blocks_retired_run_series() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(run_series="mainline_6x30_v1"),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("bare_t3_baseline", "bare_t3"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("retired run series" in issue for issue in report.blocking)


def test_readiness_blocks_paper_mainline_without_primary_value_source(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"task_ids":["task-a"],'
        '"strategy_names":["bare_t2_baseline","bare_t3_baseline","enterprise_router_baseline",'
        '"budgetflow_task_level","budgetflow_segment"]}'
    )
    frozen_plan = tmp_path / "frozen_plan.json"
    frozen_plan.write_text(
        '{"meta":{"name":"unit_plan"},'
        '"plan":{"task-a":{"preferred_model":"tier2","priority":1}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=str(frozen_plan), budget_plan=str(bp)),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=paper_mainline_strategies(),
        policy_jobs=len(paper_mainline_strategies()),
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("primary value evidence" in issue for issue in report.blocking)
    assert any("generation_mode" in issue for issue in report.blocking)


def test_readiness_blocks_frozen_plan_without_selected_task(tmp_path) -> None:
    plan = tmp_path / "frozen_plan.json"
    plan.write_text(
        '{"meta":{"name":"unit_plan"},"plan":{"task-a":{"preferred_model":"tier2","priority":1}}}'
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
    )

    assert not report.ok
    assert "frozen_plan=unit_plan" in report.facts
    assert "frozen_plan_entries=1" in report.facts
    assert any("missing 1 selected tasks: task-b" in issue for issue in report.blocking)


def test_readiness_accepts_frozen_plan_covering_selected_tasks(tmp_path) -> None:
    plan = tmp_path / "frozen_plan.json"
    plan.write_text(
        '{"meta":{"name":"unit_plan"},"plan":{"task-a":{"preferred_model":"tier2","priority":1}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(frozen_plan=str(plan)),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_same_enterprise_router", "budgetflow_same_router"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert report.ok
    assert "frozen_plan=unit_plan" in report.facts
    assert "frozen_plan_entries=1" in report.facts


def test_readiness_blocks_tasks_without_verifiable_harness_metadata() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="missing-test-patch", test_patch="", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="missing-f2p", test_patch="diff", fail_to_pass=()),
        ],
        strategies=(CompareStrategy("bare_t3_baseline", "bare_t3"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("lack test_patch" in issue for issue in report.blocking)
    assert any("lack fail_to_pass" in issue for issue in report.blocking)


def test_readiness_blocks_malformed_frozen_plan(tmp_path) -> None:
    plan = tmp_path / "bad_frozen_plan.json"
    plan.write_text('{"meta":{"name":"bad"},"plan":{"task-a":{"preferred_model":"tier2","base_cap":0.2,"priority":1}}}')
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
    )

    assert not report.ok
    assert any("cannot load frozen router plan" in issue for issue in report.blocking)


def test_readiness_blocks_budget_plan_blck_decision(tmp_path) -> None:
    """Budget plan decision=BLOCK → paid readiness NO-GO."""
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":3.58,"source":"budget_binding_calibrator",'
        '"generation_mode":"target_utilization",'
        '"decision":"BLOCK","reasons":["max utilization 13% < 15%"]}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("budget plan decision is BLOCK" in issue for issue in report.blocking)


def test_readiness_blocks_retired_budget_plan_generation_mode(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"retired_budget_mode",'
        '"decision":"PASS","task_ids":["task-a"]}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("generation_mode must be target_utilization" in issue for issue in report.blocking)


def test_readiness_blocks_budget_plan_missing_selected_tasks(tmp_path) -> None:
    """Budget plans must be generated for exactly the selected task list."""
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"target_utilization","decision":"PASS",'
        '"task_ids":["task-a"]}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("budget plan task_ids must exactly match selected tasks/order" in issue for issue in report.blocking)
    assert any("missing selected tasks: task-b" in issue for issue in report.blocking)


def test_readiness_blocks_budget_plan_strategy_set_drift(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level","bare_t2_baseline"]}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(
            CompareStrategy("bare_t2_baseline", "all_tier2"),
            CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        ),
        policy_jobs=2,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("strategy set/order" in issue for issue in report.blocking)


def test_readiness_blocks_budget_plan_superset_for_short_run(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"target_utilization","decision":"PASS",'
        '"task_ids":["task-a","task-b","task-c"]}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert "budget_plan_task_ids=3" in report.facts
    assert any("extra budget-plan tasks: task-c" in issue for issue in report.blocking)


def test_readiness_blocks_budget_plan_task_order_drift(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"target_utilization","decision":"PASS",'
        '"task_ids":["task-b","task-a"]}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("same task set but different order" in issue for issue in report.blocking)


def test_readiness_blocks_diagnostic_catalog_without_explicit_opt_in(tmp_path) -> None:
    t3x3_path = Path(__file__).resolve().parents[1] / "docs/config/model_tiers.t3x3.json"
    if not t3x3_path.exists():
        return
    init_catalog(t3x3_path)
    try:
        value_context = ValueEfficiencyContext()
        value_context.init(value_profile="equal")

        report = build_compare_readiness_report(
            args=_args(),
            tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
            strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
            policy_jobs=1,
            value_context=value_context,
            catalog_issues=[],
            runtime_root=Path("/tmp/budgetflow-runtime"),
        )

        assert not report.ok
        assert any("--diagnostic-catalog" in issue for issue in report.blocking)
    finally:
        init_catalog(DEFAULT_CATALOG_PATH)


def test_readiness_accepts_diagnostic_catalog_with_explicit_opt_in(tmp_path) -> None:
    t3x3_path = Path(__file__).resolve().parents[1] / "docs/config/model_tiers.t3x3.json"
    if not t3x3_path.exists():
        return
    init_catalog(t3x3_path)
    try:
        value_context = ValueEfficiencyContext()
        value_context.init(value_profile="equal")

        report = build_compare_readiness_report(
            args=_args(diagnostic_catalog=True),
            tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
            strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
            policy_jobs=1,
            value_context=value_context,
            catalog_issues=[],
            runtime_root=Path("/tmp/budgetflow-runtime"),
        )

        assert report.ok
        assert any("catalog_role=diagnostic" in fact for fact in report.facts)
    finally:
        init_catalog(DEFAULT_CATALOG_PATH)

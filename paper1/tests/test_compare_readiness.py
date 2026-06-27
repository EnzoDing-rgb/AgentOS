from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

import budgetflow.experiments.compare_readiness as readiness
from budgetflow.experiments.compare_config import CompareStrategy, paper_mainline_strategies
from budgetflow.experiments.compare_readiness import build_compare_readiness_report
from budgetflow.defaults import PAID_MAINLINE_STEP_LIMIT
from budgetflow.model_tiers import DEFAULT_CATALOG_PATH, init_catalog
from budgetflow.value_efficiency import ValueEfficiencyContext


@pytest.fixture(autouse=True)
def _clean_runtime_python(monkeypatch):
    monkeypatch.setattr(readiness, "find_runtime_worktree_python_contamination", lambda runtime_root: [])


def _args(**overrides):
    base = dict(
        preset="3x3",
        ids=None,
        task_set="easy",
        trace_turns=True,
        diagnostic_catalog=False,
        frozen_plan=None,
        step_limit=PAID_MAINLINE_STEP_LIMIT,
    )
    base.update(overrides)
    return Namespace(**base)


def test_protocol_health_uses_current_classifier_for_archived_rows(tmp_path) -> None:
    jsonl = tmp_path / "run.jsonl"
    rows = [
        {
            "score_status": "abort",
            "failure_owner": "protocol",
            "abort_owner": "protocol",
            "harness_resolved": False,
            "patch_extracted": False,
            "agent_gold_edited": False,
            "exit_status": "LimitsExceeded",
            "exit_reason": None,
            "detail": "no model patch extracted",
            "turn_trace_count": 60,
        },
        {
            "score_status": "abort",
            "failure_owner": "protocol",
            "abort_owner": "protocol",
            "harness_resolved": False,
            "patch_extracted": False,
            "agent_gold_edited": False,
            "exit_status": "FormatError",
            "exit_reason": "format_error_text_action",
            "detail": "no model patch extracted",
            "turn_trace_count": 1,
        },
    ]
    jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows))

    stats = readiness._compute_protocol_health(jsonl)

    assert stats["total_rows"] == 2
    assert stats["protocol_abort_rate"] == 0.5


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


def test_readiness_warns_equal_value_is_not_primary_claim1_evidence() -> None:
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
    assert any("not primary Claim 1 value evidence" in warning for warning in report.warnings)
    assert "value_source_class=equal_sanity" in report.facts
    assert "value_evidence=sanity_fallback" in report.facts
    assert "value_primary_claim1=false" in report.facts


def test_readiness_warns_plain_matrix_is_not_primary_claim1_evidence(tmp_path) -> None:
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
    assert "value_primary_claim1=false" in report.facts
    assert any("not primary Claim 1 value evidence" in warning for warning in report.warnings)


def test_readiness_accepts_pre_registered_manual_as_primary_claim1_evidence(tmp_path) -> None:
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
    assert "value_evidence=primary_claim1" in report.facts
    assert "value_confidence=manual" in report.facts
    assert "value_primary_claim1=true" in report.facts
    assert not any("not primary Claim 1 value evidence" in warning for warning in report.warnings)


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


def test_paper_mainline_blocks_step_limit_above_paid_safety_cap() -> None:
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(step_limit=150),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=paper_mainline_strategies(),
        policy_jobs=len(paper_mainline_strategies()),
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any(
        f"step_limit=150" in issue and f"paid safety cap {PAID_MAINLINE_STEP_LIMIT}" in issue
        for issue in report.blocking
    )


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
        '"strategy_names":["bare_t2_baseline","bare_t3_baseline",'
        '"routellm_learned_router_baseline","budgetflow_task_level"]}'
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
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(
        '{"tasks":{"task-a":{"task_value":{"criticality_value":1.0},'
        '"criticality_level":"normal"}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(
        value_profile="criticality_value",
        value_matrix_path=str(matrix),
        value_source_kind="pre_registered_manual",
    )

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


def test_readiness_blocks_selected_repo_with_missing_harness_dependency(monkeypatch) -> None:
    import budgetflow.experiments.compare_readiness as readiness

    monkeypatch.setattr(
        readiness,
        "_missing_selected_harness_dependencies",
        lambda tasks: {"mwaskom/seaborn": ("matplotlib",)},
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")
    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(
                instance_id="mwaskom__seaborn-3010",
                repo="mwaskom/seaborn",
                test_patch="diff",
                fail_to_pass=("tests/test_regression.py::test_polyfit_missing_data",),
            )
        ],
        strategies=(CompareStrategy("bare_t3_baseline", "bare_t3"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("missing harness dependencies" in issue for issue in report.blocking)


def test_readiness_blocks_sphinx_when_requests_is_missing(monkeypatch) -> None:
    import budgetflow.experiments.compare_readiness as readiness

    monkeypatch.setattr(readiness.importlib.util, "find_spec", lambda module: None)
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")
    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(
                instance_id="sphinx-doc__sphinx-8273",
                repo="sphinx-doc/sphinx",
                test_patch="diff",
                fail_to_pass=("tests/test_build_manpage.py::test_man_make_section_directory",),
            )
        ],
        strategies=(CompareStrategy("bare_t3_baseline", "bare_t3"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
    )

    assert not report.ok
    assert any("selected repo sphinx-doc/sphinx has missing harness dependencies: requests" in issue for issue in report.blocking)


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
    assert any("generation_mode must be one of" in issue for issue in report.blocking)


def test_readiness_accepts_stage_prefix_pressure_budget_plan(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"stage_prefix_pressure",'
        '"budget_pressure_spec":{"mode":"stage_prefix_pressure",'
        '"stage_prefix_count":1,"stage_target_budget_fraction":0.35,'
        '"stage_reference_strategy":"bare_t3_baseline"},'
        '"decision":"PASS","task_ids":["task-a"],'
        '"strategy_names":["budgetflow_segment"],'
        '"planned_task_budget_policy":{"mode":"budgetflow_planned_task_budget"},'
        '"planned_task_budget_by_strategy":{"budgetflow_segment":{"task-a":0.8}}}'
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

    assert report.ok
    assert "budget_plan_generation_mode=stage_prefix_pressure" in report.facts


def test_readiness_blocks_stage_prefix_count_larger_than_current_stage(tmp_path) -> None:
    """Do not run only part of a compiled stage-prefix pressure contract."""
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"stage_prefix_pressure",'
        '"budget_pressure_spec":{"mode":"stage_prefix_pressure",'
        '"stage_prefix_count":10,"stage_target_budget_fraction":0.35,'
        '"stage_reference_strategy":"bare_t3_baseline"},'
        '"decision":"PASS","task_ids":["t1","t2","t3","t4","t5","t6","t7","t8","t9","t10"],'
        '"strategy_names":["budgetflow_segment"],'
        '"planned_task_budget_policy":{"mode":"budgetflow_planned_task_budget"},'
        '"planned_task_budget_by_strategy":{"budgetflow_segment":{'
        '"t1":0.8,"t2":0.8,"t3":0.8,"t4":0.8,"t5":0.8,'
        '"t6":0.8,"t7":0.8,"t8":0.8,"t9":0.8,"t10":0.8}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")
    tasks = [
        SimpleNamespace(instance_id=f"t{i}", test_patch="diff", fail_to_pass=("test",))
        for i in range(1, 11)
    ]

    report = build_compare_readiness_report(
        args=_args(max_tasks_per_strategy=5),
        tasks=tasks,
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any(
        "stage_prefix_count=10 exceeds --max-tasks-per-strategy=5" in issue
        for issue in report.blocking
    )


def test_readiness_accepts_later_stage_for_stage_prefix_pressure_plan(tmp_path) -> None:
    """A 10-prefix plan can resume with max_tasks_per_strategy=20 or 30."""
    bp = tmp_path / "budget_plan.json"
    caps = ",".join(f'"t{i}":0.8' for i in range(1, 31))
    task_ids = ",".join(f'"t{i}"' for i in range(1, 31))
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"stage_prefix_pressure",'
        '"budget_pressure_spec":{"mode":"stage_prefix_pressure",'
        '"stage_prefix_count":10,"stage_target_budget_fraction":0.35,'
        '"stage_reference_strategy":"bare_t3_baseline"},'
        '"decision":"PASS","task_ids":[' + task_ids + '],'
        '"strategy_names":["budgetflow_segment"],'
        '"planned_task_budget_policy":{"mode":"budgetflow_planned_task_budget"},'
        '"planned_task_budget_by_strategy":{"budgetflow_segment":{' + caps + '}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")
    tasks = [
        SimpleNamespace(instance_id=f"t{i}", test_patch="diff", fail_to_pass=("test",))
        for i in range(1, 31)
    ]

    report = build_compare_readiness_report(
        args=_args(max_tasks_per_strategy=20),
        tasks=tasks,
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert report.ok


def test_readiness_blocks_stage_prefix_count_exceeds_task_count(tmp_path) -> None:
    """stage_prefix_count must not exceed the selected task list length."""
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"stage_prefix_pressure",'
        '"budget_pressure_spec":{"mode":"stage_prefix_pressure",'
        '"stage_prefix_count":5,"stage_target_budget_fraction":0.35,'
        '"stage_reference_strategy":"bare_t3_baseline"},'
        '"decision":"PASS","task_ids":["t1","t2","t3"],'
        '"strategy_names":["budgetflow_segment"],'
        '"planned_task_budget_policy":{"mode":"budgetflow_planned_task_budget"},'
        '"planned_task_budget_by_strategy":{"budgetflow_segment":{"t1":0.8}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="t1", test_patch="diff", fail_to_pass=("test",)),
            SimpleNamespace(instance_id="t2", test_patch="diff", fail_to_pass=("test",)),
            SimpleNamespace(instance_id="t3", test_patch="diff", fail_to_pass=("test",)),
        ],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any(
        "stage_prefix_count=5 exceeds selected task count=3" in issue
        for issue in report.blocking
    )


def test_readiness_blocks_stage_prefix_pressure_task_order_mismatch(tmp_path) -> None:
    """stage_prefix_pressure is order-sensitive; order mismatch must block."""
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"stage_prefix_pressure",'
        '"budget_pressure_spec":{"mode":"stage_prefix_pressure",'
        '"stage_prefix_count":2,"stage_target_budget_fraction":0.35,'
        '"stage_reference_strategy":"bare_t3_baseline"},'
        '"decision":"PASS","task_ids":["t1","t2","t3"],'
        '"strategy_names":["budgetflow_segment"],'
        '"planned_task_budget_policy":{"mode":"budgetflow_planned_task_budget"},'
        '"planned_task_budget_by_strategy":{"budgetflow_segment":{"t1":0.8,"t2":0.8,"t3":0.8}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="t2", test_patch="diff", fail_to_pass=("test",)),
            SimpleNamespace(instance_id="t1", test_patch="diff", fail_to_pass=("test",)),
            SimpleNamespace(instance_id="t3", test_patch="diff", fail_to_pass=("test",)),
        ],
        strategies=(CompareStrategy("budgetflow_segment", "segment_value_aware"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any(
        "budget plan task_ids order must exactly match selected task order"
        in issue
        for issue in report.blocking
    )


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
    assert any("budget plan task_ids must exactly match selected task set" in issue for issue in report.blocking)
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


def test_readiness_blocks_budgetflow_plan_without_planned_task_budgets(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level"]}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("missing planned_task_budget_by_strategy" in issue for issue in report.blocking)


def test_readiness_blocks_budgetflow_plan_missing_planned_task_cap(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a","task-b"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
        ],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("missing selected tasks: task-b" in issue for issue in report.blocking)


def test_readiness_blocks_stale_planned_task_budget_mode(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_policy":{"mode":"budgetflow_loose_task_budget"},'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("planned_task_budget_policy.mode" in issue for issue in report.blocking)


def test_readiness_warns_budgetflow_under_target_pressure_contract(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}},'
        '"projection_diagnostics":{"budgetflow_task_level":{'
        '"degeneration":"mixed","runtime_projected_tier_counts":{"tier2":1,"tier3":1},'
        '"runtime_projected_strongest_task_fraction":0.5}},'
        '"projected_utilization_by_strategy":{"budgetflow_task_level":0.36},'
        '"pressure_contract":{"grade":"warn","violations":["budgetflow_under_target: budgetflow_task_level at 36.0% < 85%"]}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert report.ok
    assert any("budgetflow_under_target" in warning for warning in report.warnings)


def test_readiness_blocks_task_level_projected_pure_reference_degeneration(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}},'
        '"projected_utilization_by_strategy":{"budgetflow_task_level":0.36},'
        '"projection_diagnostics":{"budgetflow_task_level":{'
        '"degeneration":"pure_reference_tier","runtime_projected_tier_counts":{"tier2":1},'
        '"runtime_projected_strongest_task_fraction":0.0}},'
        '"pressure_contract":{"grade":"warn","violations":['
        '"budgetflow_task_level_degenerated: projected task-level policy uses zero Strongest Model tasks under compiled task budgets"]}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("pure_reference_tier" in issue for issue in report.blocking)


def test_readiness_blocks_reference_frontier_diagnostic_pure_reference(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}},'
        '"projected_utilization_by_strategy":{"budgetflow_task_level":0.36},'
        '"projection_diagnostics":{"budgetflow_task_level":{'
        '"degeneration":"pure_reference_tier","runtime_projected_tier_counts":{"tier2":1},'
        '"runtime_projected_strongest_task_fraction":0.0}},'
        '"frontier_diagnostic":{"posture":"reference_cost_dominant",'
        '"scope":"projection_only_not_outcome_evidence"},'
        '"pressure_contract":{"grade":"warn","violations":['
        '"budgetflow_task_level_degenerated: projected task-level policy uses zero Strongest Model tasks under compiled task budgets"]}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert "frontier_posture=reference_cost_dominant" in report.facts
    assert any("pure_reference_tier" in issue for issue in report.blocking)


def test_readiness_blocks_task_level_projected_pure_strongest_degeneration(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}},'
        '"projected_utilization_by_strategy":{"budgetflow_task_level":0.90},'
        '"projection_diagnostics":{"budgetflow_task_level":{'
        '"degeneration":"pure_strongest_tier","runtime_projected_tier_counts":{"tier3":1},'
        '"runtime_projected_strongest_task_fraction":1.0}},'
        '"pressure_contract":{"grade":"warn","violations":['
        '"budgetflow_task_level_degenerated: projected task-level policy uses only Strongest Model under compiled task budgets"]}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("pure_strongest_tier" in issue for issue in report.blocking)


def test_readiness_blocks_strongest_frontier_diagnostic_pure_strongest(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}},'
        '"projected_utilization_by_strategy":{"budgetflow_task_level":0.90},'
        '"projection_diagnostics":{"budgetflow_task_level":{'
        '"degeneration":"pure_strongest_tier","runtime_projected_tier_counts":{"tier3":1},'
        '"runtime_projected_strongest_task_fraction":1.0}},'
        '"frontier_diagnostic":{"posture":"strongest_cost_dominant",'
        '"scope":"projection_only_not_outcome_evidence"},'
        '"pressure_contract":{"grade":"warn","violations":['
        '"budgetflow_task_level_degenerated: projected task-level policy uses only Strongest Model under compiled task budgets"]}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert "frontier_posture=strongest_cost_dominant" in report.facts
    assert any("pure_strongest_tier" in issue for issue in report.blocking)


def test_readiness_warns_reference_cost_dominant_frontier(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator","decision":"PASS",'
        '"generation_mode":"target_utilization",'
        '"task_ids":["task-a"],'
        '"strategy_names":["bare_t2_baseline","bare_t3_baseline","budgetflow_task_level"],'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{"task-a":0.8}},'
        '"projection_diagnostics":{"budgetflow_task_level":{'
        '"degeneration":"mixed","runtime_projected_tier_counts":{"tier2":1,"tier3":1},'
        '"runtime_projected_strongest_task_fraction":0.5}},'
        '"frontier_diagnostic":{"posture":"reference_cost_dominant",'
        '"scope":"projection_only_not_outcome_evidence"}}'
    )
    matrix = tmp_path / "value_matrix.json"
    matrix.write_text(
        '{"tasks":{"task-a":{"task_value":{"criticality_value":1.0},'
        '"criticality_level":"normal"}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(
        value_profile="criticality_value",
        value_matrix_path=str(matrix),
        value_source_kind="pre_registered_manual",
    )

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",))],
        strategies=(
            CompareStrategy("bare_t2_baseline", "all_tier2"),
            CompareStrategy("bare_t3_baseline", "bare_t3"),
            CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        ),
        policy_jobs=3,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert report.ok
    assert "frontier_posture=reference_cost_dominant" in report.facts
    assert any("reference tier is projected cheaper" in warning for warning in report.warnings)


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
        '"task_ids":["task-b","task-a"],'
        '"planned_task_budget_by_strategy":{"budgetflow_segment":{"task-a":1.0,"task-b":1.0}}}'
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
    assert any("task_ids order must exactly match" in issue for issue in report.blocking)


def test_readiness_blocks_nonfinite_or_nonpositive_planned_task_caps(tmp_path) -> None:
    bp = tmp_path / "budget_plan.json"
    bp.write_text(
        '{"hard_cap_usd":1.0,"source":"budget_binding_calibrator",'
        '"generation_mode":"target_utilization","decision":"PASS",'
        '"task_ids":["task-a","task-b","task-c","task-d"],'
        '"strategy_names":["budgetflow_task_level"],'
        '"planned_task_budget_policy":{"mode":"budgetflow_planned_task_budget"},'
        '"planned_task_budget_by_strategy":{"budgetflow_task_level":{'
        '"task-a":0.0,"task-b":-1.0,"task-c":1e999,"task-d":"nan"}},'
        '"projection_diagnostics":{"budgetflow_task_level":{'
        '"degeneration":"mixed","runtime_projected_tier_counts":{"tier2":2,"tier3":2},'
        '"runtime_projected_strongest_task_fraction":0.5}}}'
    )
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    report = build_compare_readiness_report(
        args=_args(),
        tasks=[
            SimpleNamespace(instance_id="task-a", test_patch="diff", fail_to_pass=("test_a",)),
            SimpleNamespace(instance_id="task-b", test_patch="diff", fail_to_pass=("test_b",)),
            SimpleNamespace(instance_id="task-c", test_patch="diff", fail_to_pass=("test_c",)),
            SimpleNamespace(instance_id="task-d", test_patch="diff", fail_to_pass=("test_d",)),
        ],
        strategies=(CompareStrategy("budgetflow_task_level", "value_aware_task_level"),),
        policy_jobs=1,
        value_context=value_context,
        catalog_issues=[],
        runtime_root=Path("/tmp/budgetflow-runtime"),
        budget_plan_path=bp,
    )

    assert not report.ok
    assert any("must be finite positive USD values" in issue for issue in report.blocking)


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

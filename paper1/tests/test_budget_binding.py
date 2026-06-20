"""Tests for budget_binding.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from budgetflow.experiments.budget_binding import (
    _load_historical_costs,
    _load_historical_cost_signals,
    _row_catalog_compatible,
    _row_is_calibration_eligible,
    _distribution_p75,
    _build_pressure_contract,
    _apply_pressure_contract_gate,
    audit_calibration,
    BudgetBindingPlan,
    CalibrationAudit,
    calibrate_budget,
    main as budget_binding_main,
)
from budgetflow.model_tiers import catalog_source_info


def _trusted(row: dict) -> dict:
    row = dict(row)
    row.setdefault("harness_trust", "trusted")
    return row


# ── _distribution_p75 ───────────────────────────────────────────────────


def test_p75_five_values() -> None:
    """Nearest-rank method: p75 of 5 sorted values = 4th value (ceil(0.75*5)=4)."""
    assert _distribution_p75([1.0, 2.0, 3.0, 4.0, 5.0]) == 4.0


def test_p75_single_value() -> None:
    assert _distribution_p75([7.0]) == 7.0


def test_p75_empty_returns_zero() -> None:
    assert _distribution_p75([]) == 0.0


def test_p75_two_values() -> None:
    # ceil(0.75*2)=ceil(1.5)=2 → index 1 → second value
    assert _distribution_p75([3.0, 9.0]) == 9.0


# ── target_utilization budget generation ─────────────────────────────────


def test_calibrate_target_utilization_produces_p75_reference(tmp_path: Path) -> None:
    """With target_utilization=0.80, hard_cap = p75 / 0.80, NOT frozen cap sum."""
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {}}))
    plan = calibrate_budget(
        ["task-a"],
        value_matrix_path=vm,
        target_utilization=0.80,
        output_path=tmp_path / "bp.json",
    )
    assert plan.generation_mode == "target_utilization"
    assert plan.target_projected_utilization == 0.80
    assert any("reference_rule: strategy_set_p75" in r for r in plan.reasons)


def test_calibrate_target_utilization_has_no_frozen_plan_input(tmp_path: Path) -> None:
    """Budget Compiler does not accept frozen caps as a budget input."""
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({
        "tasks": {
            "task-a": {"bootstrap_difficulty": 50.0},
            "task-b": {"bootstrap_difficulty": 50.0},
        }
    }))
    plan = calibrate_budget(
        ["task-a", "task-b"],
        value_matrix_path=vm,
        target_utilization=0.80,
        output_path=tmp_path / "bp.json",
    )
    assert plan.historical_source == "bootstrap_estimate"
    assert all("frozen" not in reason.lower() for reason in plan.reasons)
    assert plan.decision != "BLOCK"


def test_calibrate_target_utilization_reference_is_not_budgetflow_specific(tmp_path: Path) -> None:
    """Reference rule is p75 of configured strategies — not BudgetFlow-specific."""
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {}}))
    plan = calibrate_budget(
        ["task-a"],
        value_matrix_path=vm,
        target_utilization=0.80,
        output_path=tmp_path / "bp.json",
    )
    all_reasons = " ".join(plan.reasons)
    assert "strategy_set_p75" in all_reasons
    assert "budgetflow_segment_projected" not in all_reasons
    assert "budgetflow_task_level_projected" not in all_reasons
    assert "max_projected" not in all_reasons


def test_calibrate_defaults_to_paper_mainline_policy_set(tmp_path: Path) -> None:
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {}}))
    plan = calibrate_budget(
        ["task-a"],
        value_matrix_path=vm,
        target_utilization=0.80,
        output_path=tmp_path / "bp.json",
    )

    assert list(plan.projected_spend_by_strategy) == [
        "bare_t2_baseline",
        "bare_t3_baseline",
        "enterprise_router_baseline",
        "budgetflow_task_level",
    ]
    assert plan.strategy_names == list(plan.projected_spend_by_strategy)
    written = json.loads((tmp_path / "bp.json").read_text())
    assert written["strategy_names"] == list(plan.projected_spend_by_strategy)


def test_calibrate_budget_plan_records_catalog_content_hash(tmp_path: Path) -> None:
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {}}))
    plan = calibrate_budget(
        ["task-a"],
        value_matrix_path=vm,
        target_utilization=0.80,
        output_path=tmp_path / "bp.json",
    )

    written = json.loads((tmp_path / "bp.json").read_text())
    assert plan.catalog_content_hash
    assert written["catalog_content_hash"] == plan.catalog_content_hash


def test_budget_plan_model_fit_evidence_is_global_not_per_task_assignment(tmp_path: Path) -> None:
    catalog = catalog_source_info()
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(
        "\n".join([
            json.dumps({
                "strategy": "bare_t2_baseline",
                "instance_id": "task-a",
                "total_cost": 0.80,
                "budget_mode": "shared_batch_hard_budget",
                "catalog": catalog,
                "score_status": "true_fail",
                "exit_status": "HarnessFailed",
                "harness_trust": "trusted",
                "row_finished_at": 1,
            }),
            json.dumps({
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.20,
                "budget_mode": "shared_batch_hard_budget",
                "catalog": catalog,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "harness_trust": "trusted",
                "row_finished_at": 1,
            }),
        ])
        + "\n"
    )
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {"task-a": {"task_effort": {"bootstrap_heuristic": 10.0}}}}))

    plan = calibrate_budget(
        ["task-a"],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=("bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"),
        target_utilization=0.80,
        output_path=tmp_path / "bp.json",
    )

    written = json.loads((tmp_path / "bp.json").read_text())
    assert plan.model_fit_evidence is not None
    assert set(written["model_fit_evidence"]) >= {
        "tier_fit",
        "source",
        "confidence",
        "tier_evidence_counts",
        "tier_completed_counts",
        "tier_censored_counts",
    }
    assert set(written["model_fit_evidence"]["tier_fit"]) >= {"tier2", "tier3"}
    assert set(written["model_fit_evidence"]["tier_evidence_counts"]) >= {"tier2", "tier3"}
    assert set(written["model_fit_evidence"]["tier_completed_counts"]) >= {"tier2", "tier3"}
    assert set(written["model_fit_evidence"]["tier_censored_counts"]) >= {"tier2", "tier3"}
    forbidden = ("preferred_model", "model_tier", "assigned_tier", "selected_backend")
    assert not any(key in json.dumps(written["projected_task_cost_by_strategy"]) for key in forbidden)
    assert not any(key in json.dumps(written["model_fit_evidence"]) for key in forbidden)


def test_budget_plan_round_trip_preserves_model_fit_evidence() -> None:
    plan = BudgetBindingPlan(
        hard_cap_usd=1.25,
        generation_mode="target_utilization",
        model_fit_evidence={
            "tier_fit": {"tier2": 0.08, "tier3": 0.65},
            "source": "historical_jsonl",
            "confidence": "medium",
            "evidence_tasks": 4,
            "tier_evidence_counts": {"tier2": 2, "tier3": 4},
            "tier_completed_counts": {"tier2": 1, "tier3": 4},
            "tier_censored_counts": {"tier2": 1, "tier3": 0},
        },
    )

    restored = BudgetBindingPlan.from_dict(plan.to_dict())

    assert restored.model_fit_evidence == plan.model_fit_evidence


def test_budget_plan_round_trips_budgetflow_planned_task_budgets() -> None:
    plan = BudgetBindingPlan(
        hard_cap_usd=1.25,
        generation_mode="target_utilization",
        planned_task_budget_by_strategy={
            "budgetflow_task_level": {
                "task-a": 0.40,
                "task-b": 0.70,
            }
        },
        planned_task_budget_policy={
            "mode": "budgetflow_loose_task_budget",
            "sum_can_exceed_hard_cap": True,
        },
    )

    restored = BudgetBindingPlan.from_dict(plan.to_dict())

    assert restored.planned_task_budget_by_strategy == {
        "budgetflow_task_level": {"task-a": 0.4, "task-b": 0.7}
    }
    assert restored.planned_task_budget_policy["sum_can_exceed_hard_cap"] is True


def test_calibrate_emits_loose_budgetflow_task_budgets(tmp_path: Path) -> None:
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({
        "tasks": {
            "task-a": {"task_effort": {"bootstrap_heuristic": 10.0}},
            "task-b": {"task_effort": {"bootstrap_heuristic": 80.0}},
        }
    }))

    plan = calibrate_budget(
        ["task-a", "task-b"],
        value_matrix_path=vm,
        strategies=("bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"),
        target_utilization=0.90,
    )

    caps = plan.planned_task_budget_by_strategy["budgetflow_task_level"]
    assert set(caps) == {"task-a", "task-b"}
    assert caps["task-b"] > caps["task-a"]
    assert sum(caps.values()) > plan.hard_cap_usd
    assert "enterprise_router_baseline" not in plan.planned_task_budget_by_strategy


def test_task_level_projection_diagnostic_uses_compiled_budget_without_rewriting_cap_costs(tmp_path: Path) -> None:
    """Compiler predicts runtime tier mix as diagnostics, not cap source."""
    catalog = catalog_source_info()
    jsonl = tmp_path / "hist.jsonl"
    rows = []
    effort = 126.6339
    tier2_per_turn = 0.006408
    tier3_per_turn = 0.03204
    # Eight clean calibration tasks overcome the completed-sample prior shrink
    # and produce workload fit close to tier2=0.81, tier3=0.85.
    for i in range(8):
        rows.append(_trusted({
            "strategy": "bare_t2_baseline",
            "instance_id": f"cal-t2-{i}",
            "total_cost": effort * tier2_per_turn / 0.9525,
            "task_effort": effort,
            "budget_mode": "shared_batch_hard_budget",
            "catalog": catalog,
            "score_status": "pass",
            "exit_status": "HarnessResolved",
            "row_finished_at": i + 1,
        }))
        rows.append(_trusted({
            "strategy": "bare_t3_baseline",
            "instance_id": f"cal-t3-{i}",
            "total_cost": effort * tier3_per_turn / 1.0,
            "task_effort": effort,
            "budget_mode": "shared_batch_hard_budget",
            "catalog": catalog,
            "score_status": "pass",
            "exit_status": "HarnessResolved",
            "row_finished_at": i + 1,
        }))
    jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({
        "tasks": {
            "task-a": {
                "task_value": {"manual_value": 0.91},
                "task_effort": {"bootstrap_heuristic": 126.6339},
            }
        }
    }))

    plan = calibrate_budget(
        ["task-a"],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=("bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"),
        target_utilization=1.0,
    )

    task_budget = plan.planned_task_budget_by_strategy["budgetflow_task_level"]["task-a"]
    t3_cost = plan.projected_task_cost_by_strategy["bare_t3_baseline"]["task-a"]
    cap_generation_task_level = plan.projected_spend_by_strategy["budgetflow_task_level"]
    diagnostic = plan.projection_diagnostics["budgetflow_task_level"]

    assert task_budget > t3_cost
    assert cap_generation_task_level < t3_cost
    assert diagnostic["projected_tier_counts"]["tier3"] == 1
    assert diagnostic["projected_spend_usd"] == pytest.approx(t3_cost, rel=1e-4)
    assert diagnostic["role"] == "readiness_diagnostic_not_cap_source"
    assert any("task_level_policy_projection" in reason for reason in plan.reasons)


def test_small_historical_sample_cannot_collapse_large_workload_cap(tmp_path: Path) -> None:
    """A few cheap diagnostic rows can calibrate scale, but not starve a larger batch."""
    catalog = catalog_source_info()
    jsonl = tmp_path / "hist.jsonl"
    rows = []
    for strategy in (
        "bare_t2_baseline",
        "bare_t3_baseline",
        "enterprise_router_baseline",
        "budgetflow_task_level",
    ):
        for i in range(6):
            rows.append(_trusted({
                "strategy": strategy,
                "instance_id": f"task-{i}",
                "total_cost": 0.10,
                "budget_mode": "shared_batch_hard_budget",
                "catalog": catalog,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": i + 1,
            }))
    jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({
        "tasks": {
            f"task-{i}": {"task_effort": {"bootstrap_heuristic": 30.0}}
            for i in range(25)
        }
    }))

    plan = calibrate_budget(
        [f"task-{i}" for i in range(25)],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=(
            "bare_t2_baseline",
            "bare_t3_baseline",
            "enterprise_router_baseline",
            "budgetflow_task_level",
        ),
        target_utilization=1.0,
    )

    assert plan.hard_cap_usd >= 8.0
    assert any("sample_coverage_shrink" in reason for reason in plan.reasons)


def test_planned_task_budgets_use_cross_strategy_task_cost_ceiling() -> None:
    from budgetflow.experiments.budget_binding import _build_budgetflow_planned_task_budgets

    caps = _build_budgetflow_planned_task_budgets(
        ("bare_t3_baseline", "budgetflow_task_level"),
        ["task-a", "task-b"],
        {
            "bare_t3_baseline": {"task-a": 0.5, "task-b": 0.1},
            "budgetflow_task_level": {"task-a": 0.05, "task-b": 0.2},
        },
        hard_cap_usd=1.0,
    )

    task_caps = caps["budgetflow_task_level"]
    assert task_caps["task-a"] > task_caps["task-b"]
    assert task_caps["task-a"] == pytest.approx((1.0 / (2 ** 0.5)) + 2.0 * 0.5)


def test_calibrate_reuses_current_catalog_historical_cost_without_repricing(tmp_path: Path) -> None:
    """Current-schema cost rows are already in active catalog units."""
    catalog = catalog_source_info()
    jsonl = tmp_path / "hist.jsonl"
    row = _trusted({
        "strategy": "bare_t3_baseline",
        "instance_id": "task-a",
        "total_cost": 0.25,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": {
            "catalog_revision": catalog["catalog_revision"],
            "catalog_content_hash": catalog["catalog_content_hash"],
        },
        "score_status": "true_fail",
        "exit_status": "HarnessResolved",
    })
    jsonl.write_text(json.dumps(row) + "\n")
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {"task-a": {"task_effort": {"bootstrap_heuristic": 10.0}}}}))

    plan = calibrate_budget(
        ["task-a"],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=("bare_t3_baseline",),
        target_utilization=0.5,
    )

    assert plan.projected_spend_by_strategy == {"bare_t3_baseline": 0.25}
    assert plan.hard_cap_usd == 0.50
    assert plan.reference_spend_usd == 0.25
    assert plan.strongest_boundary_usd == 0.25
    assert plan.max_projected_spend_usd == 0.25
    assert any("strongest_boundary" in reason for reason in plan.reasons)
    assert not any("clipped" in reason for reason in plan.reasons)


def test_calibrate_uses_budget_exhausted_rows_as_floor_not_observed_sample(tmp_path: Path) -> None:
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(_trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.75,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "row_finished_at": 1,
    })) + "\n")
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {"task-a": {"task_effort": {"bootstrap_heuristic": 10.0}}}}))

    signals = _load_historical_cost_signals(jsonl)
    assert signals.observed_costs == {}
    assert signals.censored_spend_floor_by_strategy == {"budgetflow_task_level": 0.75}

    plan = calibrate_budget(
        ["task-a"],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=("budgetflow_task_level",),
        target_utilization=0.75,
    )

    # baseline adds workload-level remaining runway without treating the
    # exhausted row as a complete observation.
    assert plan.projected_spend_by_strategy["budgetflow_task_level"] > 0.75
    assert plan.censored_spend_floor_by_strategy == {"budgetflow_task_level": 0.75}
    assert any("censored spend floors" in reason for reason in plan.reasons)


def test_fixed_tier_turn_cap_is_not_censored_budget_floor(tmp_path: Path) -> None:
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps({
        "strategy": "bare_t2_baseline",
        "instance_id": "task-a",
        "total_cost": 0.75,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "StagnationExit",
        "exit_reason": "tier2_turn_cap",
        "agent_exit_status": "StagnationExit",
        "agent_exit_reason": "tier2_turn_cap",
        "failure_class": "extract_fail",
        "harness_trust": "incomplete",
        "row_finished_at": 1,
    }) + "\n")

    signals = _load_historical_cost_signals(jsonl)

    assert signals.observed_costs == {}
    assert signals.censored_spend_floor_by_strategy == {}
    assert signals.censored_task_costs_by_strategy == {}
    assert signals.excluded == {"harness_trust:incomplete": 1}


def test_budget_exhausted_floor_requires_trusted_harness_row(tmp_path: Path) -> None:
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.75,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "harness_trust": "invalid",
        "row_finished_at": 1,
    }) + "\n")

    signals = _load_historical_cost_signals(jsonl)

    assert signals.observed_costs == {}
    assert signals.censored_spend_floor_by_strategy == {}
    assert signals.censored_task_costs_by_strategy == {}
    assert signals.excluded == {"harness_trust:invalid": 1}


def test_budget_exhausted_floor_requires_positive_spend(tmp_path: Path) -> None:
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(_trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.0,
        "budget_mode": "budgetflow_planned_task_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "budget_exhausted": True,
        "harness_trust": "incomplete",
        "row_finished_at": 1,
    })) + "\n")

    signals = _load_historical_cost_signals(jsonl)

    assert signals.observed_costs == {}
    assert signals.censored_spend_floor_by_strategy == {}
    assert signals.censored_task_costs_by_strategy == {}
    assert signals.excluded == {"budget_exhausted_zero_spend": 1}


def test_calibrate_projects_censored_task_with_remaining_runway(tmp_path: Path) -> None:
    catalog = catalog_source_info()
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(
        "\n".join([
            json.dumps(_trusted({
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.10,
                "budget_mode": "shared_batch_hard_budget",
                "catalog": catalog,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            })),
            json.dumps(_trusted({
                "strategy": "bare_t3_baseline",
                "instance_id": "task-b",
                "total_cost": 0.20,
                "budget_mode": "shared_batch_hard_budget",
                "catalog": catalog,
                "score_status": "true_fail",
                "exit_status": "BudgetFlowBudgetError",
                "exit_reason": "budget_exhausted",
                "row_finished_at": 1,
            })),
        ])
        + "\n"
    )
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({
        "tasks": {
            "task-a": {"task_effort": {"bootstrap_heuristic": 100.0}},
            "task-b": {"task_effort": {"bootstrap_heuristic": 100.0}},
        }
    }))

    plan = calibrate_budget(
        ["task-a", "task-b"],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=("bare_t3_baseline",),
        target_utilization=0.50,
    )

    per_task = plan.projected_task_cost_by_strategy["bare_t3_baseline"]
    assert per_task["task-a"] == 0.10
    assert per_task["task-b"] > 0.20
    assert plan.projected_spend_by_strategy["bare_t3_baseline"] > 0.30


def test_cold_start_prices_fixed_tier_controls_without_assigning_budgetflow_tiers(tmp_path: Path) -> None:
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {"task-a": {"task_effort": {"bootstrap_heuristic": 50.0}}}}))

    plan = calibrate_budget(
        ["task-a"],
        value_matrix_path=vm,
        strategies=("bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"),
        target_utilization=0.80,
    )

    bare_t2 = plan.projected_spend_by_strategy["bare_t2_baseline"]
    bare_t3 = plan.projected_spend_by_strategy["bare_t3_baseline"]
    budgetflow = plan.projected_spend_by_strategy["budgetflow_task_level"]

    assert bare_t3 > bare_t2
    assert bare_t3 > budgetflow
    written = plan.to_dict()
    forbidden = ("preferred_model", "model_tier", "assigned_tier", "selected_backend")
    assert not any(key in json.dumps(written["projected_task_cost_by_strategy"]) for key in forbidden)


def test_calibrate_cap_allows_strongest_model_to_reach_final_task(tmp_path: Path) -> None:
    catalog = catalog_source_info()
    jsonl = tmp_path / "hist.jsonl"
    rows = []
    for task_id, cost in (("task-a", 0.10), ("task-b", 0.12), ("task-c", 0.14)):
        rows.append(_trusted({
            "strategy": "bare_t3_baseline",
            "instance_id": task_id,
            "total_cost": cost,
            "budget_mode": "shared_batch_hard_budget",
            "catalog": catalog,
            "score_status": "pass",
            "exit_status": "HarnessResolved",
            "row_finished_at": 1,
        }))
    jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({
        "tasks": {
            "task-a": {"task_effort": {"bootstrap_heuristic": 100.0}},
            "task-b": {"task_effort": {"bootstrap_heuristic": 100.0}},
            "task-c": {"task_effort": {"bootstrap_heuristic": 100.0}},
        }
    }))

    plan = calibrate_budget(
        ["task-a", "task-b", "task-c"],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=("bare_t3_baseline",),
        target_utilization=0.20,
    )

    assert plan.hard_cap_usd == pytest.approx(1.80)
    assert any("strongest_runway_floor" in reason for reason in plan.reasons)
    assert not any("clipped" in reason for reason in plan.reasons)


def test_calibrate_does_not_clip_cap_to_underestimated_strongest_projection(tmp_path: Path) -> None:
    catalog = catalog_source_info()
    jsonl = tmp_path / "hist.jsonl"
    rows = [
        _trusted({
            "strategy": "bare_t3_baseline",
            "instance_id": "task-a",
            "total_cost": 0.40,
            "budget_mode": "shared_batch_hard_budget",
            "catalog": catalog,
            "score_status": "pass",
            "exit_status": "HarnessResolved",
            "row_finished_at": 1,
        }),
        _trusted({
            "strategy": "budgetflow_task_level",
            "instance_id": "task-a",
            "total_cost": 1.80,
            "budget_mode": "shared_batch_hard_budget",
            "catalog": catalog,
            "score_status": "pass",
            "exit_status": "HarnessResolved",
            "row_finished_at": 1,
        }),
    ]
    jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {"task-a": {"task_effort": {"bootstrap_heuristic": 100.0}}}}))

    plan = calibrate_budget(
        ["task-a"],
        historical_jsonl=jsonl,
        value_matrix_path=vm,
        strategies=("bare_t3_baseline", "budgetflow_task_level"),
        target_utilization=0.90,
    )

    assert plan.reference_spend_usd == 1.80
    assert plan.strongest_boundary_usd == 0.40
    assert plan.hard_cap_usd == 2.00
    assert plan.hard_cap_usd > plan.strongest_boundary_usd
    assert any("not a hard cap" in reason for reason in plan.reasons)


def test_target_utilization_below_zero_raises() -> None:
    import pytest
    with pytest.raises(ValueError, match="target_utilization"):
        calibrate_budget(["task-a"], target_utilization=0.0)


def test_target_utilization_above_one_raises() -> None:
    import pytest
    with pytest.raises(ValueError, match="target_utilization"):
        calibrate_budget(["task-a"], target_utilization=1.5)


# ── pressure-shape audit ────────────────────────────────────────────────


def test_pressure_contract_flags_weak_strongest_pressure() -> None:
    plan = BudgetBindingPlan(
        hard_cap_usd=10.0,
        generation_mode="target_utilization",
        target_projected_utilization=0.80,
    )
    plan.projected_utilization_by_strategy = {
        "bare_t2_baseline": 0.30,
        "bare_t3_baseline": 0.20,
        "enterprise_router_baseline": 0.30,
        "budgetflow_same_enterprise_router": 0.30,
        "budgetflow_task_level": 0.42,
        "budgetflow_segment": 0.40,
    }
    original_decision = plan.decision
    _build_pressure_contract(plan, ("bare_t2_baseline", "bare_t3_baseline", "budgetflow_segment"))
    assert plan.decision == original_decision
    assert plan.pressure_contract["grade"] == "warn"
    assert any("t3_loose" in v for v in plan.pressure_contract["violations"])


def test_pressure_gate_warns_budgetflow_under_target_without_blocking_compiler() -> None:
    plan = BudgetBindingPlan(
        hard_cap_usd=10.0,
        generation_mode="target_utilization",
        target_projected_utilization=0.80,
        decision="PASS",
    )
    plan.projected_utilization_by_strategy = {
        "bare_t2_baseline": 0.40,
        "bare_t3_baseline": 0.90,
        "budgetflow_task_level": 0.36,
    }

    _build_pressure_contract(plan, ("bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"))
    _apply_pressure_contract_gate(plan)

    assert plan.decision == "PASS"
    assert any("PRESSURE_GATE WARNING" in reason for reason in plan.reasons)


def test_pressure_contract_flags_task_level_pure_reference_degeneration() -> None:
    plan = BudgetBindingPlan(
        hard_cap_usd=10.0,
        generation_mode="target_utilization",
        target_projected_utilization=0.80,
    )
    plan.projected_utilization_by_strategy = {
        "bare_t2_baseline": 0.40,
        "bare_t3_baseline": 0.90,
        "budgetflow_task_level": 0.36,
    }
    plan.projection_diagnostics = {
        "budgetflow_task_level": {
            "degeneration": "pure_reference_tier",
            "projected_tier_counts": {"tier2": 25},
            "projected_strongest_task_fraction": 0.0,
        }
    }

    _build_pressure_contract(plan, ("bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"))

    assert plan.pressure_contract["grade"] == "warn"
    assert any("budgetflow_task_level_degenerated" in v for v in plan.pressure_contract["violations"])


def test_pressure_contract_accepts_mixed_task_level_projection_below_util_target() -> None:
    plan = BudgetBindingPlan(
        hard_cap_usd=10.0,
        generation_mode="target_utilization",
        target_projected_utilization=1.0,
    )
    plan.projected_utilization_by_strategy = {
        "bare_t2_baseline": 0.40,
        "bare_t3_baseline": 1.00,
        "budgetflow_task_level": 0.36,
    }
    plan.projection_diagnostics = {
        "budgetflow_task_level": {
            "degeneration": "mixed_or_strongest",
            "projected_tier_counts": {"tier2": 8, "tier3": 17},
            "projected_strongest_task_fraction": 0.68,
        }
    }

    _build_pressure_contract(plan, ("bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"))

    assert not any("budgetflow_under_target" in v for v in plan.pressure_contract["violations"])
    assert not any("budgetflow_task_level_degenerated" in v for v in plan.pressure_contract["violations"])
    assert any("budgetflow_task_level_mixed" in a for a in plan.pressure_contract["assertions"])


def test_pressure_contract_healthy_shape_grade_pass() -> None:
    """T3 tight and BudgetFlow pressure-ready = expected shape, grade pass."""
    plan = BudgetBindingPlan(
        hard_cap_usd=5.0,
        generation_mode="target_utilization",
        target_projected_utilization=0.80,
    )
    plan.projected_utilization_by_strategy = {
        "bare_t2_baseline": 0.30,
        "bare_t3_baseline": 0.85,
        "enterprise_router_baseline": 0.50,
        "budgetflow_task_level": 0.75,
        "budgetflow_segment": 0.70,
    }
    _build_pressure_contract(plan, ("bare_t2_baseline", "bare_t3_baseline", "budgetflow_segment"))
    assert plan.pressure_contract["grade"] == "pass"
    assert len(plan.pressure_contract["violations"]) == 0
    assert any("t2_diagnostic" in a for a in plan.pressure_contract["assertions"])
    assert any("t3_tight" in a for a in plan.pressure_contract["assertions"])
    assert any("budgetflow_pressure_ready" in a for a in plan.pressure_contract["assertions"])


def test_calibrate_requires_target_utilization() -> None:
    import pytest

    with pytest.raises(ValueError, match="target_utilization is required"):
        calibrate_budget(["task-a"])


def test_audit_calibration_dedup_keeps_last_row(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                json.dumps(_trusted({
                    "strategy": "bare_t3_baseline",
                    "instance_id": "task-a",
                    "total_cost": 0.10,
                    "row_finished_at": 1,
                })),
                json.dumps({
                    "strategy": "bare_t3_baseline",
                    "instance_id": "task-a",
                    "total_cost": 0.40,
                    "row_finished_at": 2,
                }),
                json.dumps({
                    "strategy": "budgetflow_task_level",
                    "instance_id": "task-a",
                    "total_cost": 0.20,
                    "row_finished_at": 1,
                }),
            ]
        )
        + "\n"
    )
    plan = BudgetBindingPlan(hard_cap_usd=1.0)
    plan.projected_spend_by_strategy = {
        "bare_t3_baseline": 0.50,
        "budgetflow_task_level": 0.25,
    }

    audit = audit_calibration(jsonl, plan)

    assert audit.strategy_errors["bare_t3_baseline"]["actual"] == 0.40
    assert audit.strategy_errors["bare_t3_baseline"]["task_count"] == 1


def test_historical_cost_loader_dedup_keeps_latest_row(tmp_path: Path) -> None:
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(
        "\n".join([
            json.dumps(_trusted({
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.10,
                "budget_mode": "shared_batch_hard_budget",
                "catalog": catalog_source_info(),
                "score_status": "true_fail",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            })),
            json.dumps(_trusted({
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.40,
                "budget_mode": "shared_batch_hard_budget",
                "catalog": catalog_source_info(),
                "score_status": "true_fail",
                "exit_status": "HarnessResolved",
                "row_finished_at": 2,
            })),
        ])
        + "\n"
    )

    costs, excluded = _load_historical_costs(jsonl)

    assert excluded == {}
    assert costs == {"bare_t3_baseline": {"task-a": 0.40}}


def test_calibration_keeps_clean_shared_rows_from_frozen_plan_budget_source(tmp_path: Path) -> None:
    """Budget source name is not contamination when runtime budget mode is clean."""
    row = _trusted({
        "strategy": "bare_t3_baseline",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "HarnessResolved",
    })
    eligible, reason = _row_is_calibration_eligible(row)
    assert (eligible, reason) == (True, "clean")

    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(row) + "\n")
    costs, excluded = _load_historical_costs(jsonl)
    assert costs == {"bare_t3_baseline": {"task-a": 0.12}}
    assert excluded == {}


def test_calibration_excludes_actual_frozen_router_cap_rows() -> None:
    row = _trusted({
        "strategy": "enterprise_router_baseline",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "frozen_router_caps",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "HarnessResolved",
    })
    eligible, reason = _row_is_calibration_eligible(row)
    assert eligible is False
    assert reason == "budget_asymmetry:frozen_router_caps"


def test_calibration_keeps_enterprise_router_when_value_aware_inactive() -> None:
    row = _trusted({
        "strategy": "enterprise_router_baseline",
        "routing": "enterprise_router",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "HarnessResolved",
        "va_active": False,
    })
    eligible, reason = _row_is_calibration_eligible(row)
    assert (eligible, reason) == (True, "clean")


def test_calibration_excludes_enterprise_router_with_value_aware_active() -> None:
    row = _trusted({
        "strategy": "enterprise_router_baseline",
        "routing": "enterprise_router",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "HarnessResolved",
        "va_active": True,
    })
    eligible, reason = _row_is_calibration_eligible(row)
    assert eligible is False
    assert reason == "contaminated:enterprise_router_with_va_active"


def test_calibration_excludes_protocol_retry_cost_overhead(tmp_path: Path) -> None:
    row = _trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "true_fail",
        "exit_status": "HarnessResolved",
        "protocol_retry_used": True,
        "protocol_retry_success": True,
    })
    eligible, reason = _row_is_calibration_eligible(row)
    assert eligible is False
    assert reason == "protocol_retry_overhead"

    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(row) + "\n")
    costs, excluded = _load_historical_costs(jsonl)
    assert costs == {}
    assert excluded == {"protocol_retry_overhead": 1}


def test_calibration_excludes_catalog_mismatch_rows(tmp_path: Path) -> None:
    row = _trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": {
            "catalog_revision": "different-revision",
            "catalog_content_hash": "not-current",
        },
        "score_status": "true_fail",
        "exit_status": "HarnessFailed",
        "exit_reason": "harness_failed",
    })
    eligible, reason = _row_is_calibration_eligible(row)
    assert eligible is False
    assert reason == "catalog_mismatch"

    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(row) + "\n")
    costs, excluded = _load_historical_costs(jsonl)
    assert costs == {}
    assert excluded == {"catalog_mismatch": 1}


def test_calibration_excludes_missing_catalog_rows(tmp_path: Path) -> None:
    row = _trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "score_status": "true_fail",
        "exit_status": "HarnessFailed",
        "exit_reason": "harness_failed",
    })

    assert _row_catalog_compatible({}) == (False, "missing_catalog")
    eligible, reason = _row_is_calibration_eligible(row)
    assert eligible is False
    assert reason == "missing_catalog"

    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(row) + "\n")
    costs, excluded = _load_historical_costs(jsonl)
    assert costs == {}
    assert excluded == {"missing_catalog": 1}


def test_calibration_excludes_missing_score_status_rows(tmp_path: Path) -> None:
    row = _trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "exit_status": "HarnessFailed",
        "exit_reason": "harness_failed",
    })

    eligible, reason = _row_is_calibration_eligible(row)
    assert eligible is False
    assert reason == "missing_score_status"

    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(row) + "\n")
    costs, excluded = _load_historical_costs(jsonl)
    assert costs == {}
    assert excluded == {"missing_score_status": 1}


def test_budget_exhausted_floor_requires_current_catalog(tmp_path: Path) -> None:
    jsonl = tmp_path / "hist.jsonl"
    jsonl.write_text(json.dumps(_trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.75,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": {"catalog_revision": "other", "catalog_content_hash": "other"},
        "score_status": "true_fail",
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "row_finished_at": 1,
    })) + "\n")

    signals = _load_historical_cost_signals(jsonl)
    assert signals.observed_costs == {}
    assert signals.censored_spend_floor_by_strategy == {}
    assert signals.excluded == {"catalog_mismatch": 1}


def test_calibration_excludes_score_abort_rows(tmp_path: Path) -> None:
    row = _trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "score_status": "abort",
        "abort_reason": "provider_or_infra_error",
        "exit_status": "ServiceUnavailableError",
        "exit_reason": "provider_unavailable",
    })
    eligible, reason = _row_is_calibration_eligible(row)
    assert eligible is False
    assert reason == "not_scoreable:abort"


def test_calibration_excludes_provider_and_parser_aborts_without_score_status() -> None:
    provider_row = _trusted({
        "strategy": "budgetflow_task_level",
        "instance_id": "task-a",
        "total_cost": 0.12,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "exit_status": "ServiceUnavailableError",
        "exit_reason": "provider_unavailable",
        "failure_class": "infra_fail",
        "score_status": "true_fail",
    })
    parser_row = _trusted({
        "strategy": "budgetflow_segment",
        "instance_id": "task-b",
        "total_cost": 0.11,
        "budget_mode": "shared_batch_hard_budget",
        "catalog": catalog_source_info(),
        "exit_status": "FormatError",
        "exit_reason": "format_error_no_tool_calls",
        "failure_class": "extract_fail",
        "score_status": "true_fail",
    })

    assert _row_is_calibration_eligible(provider_row) == (False, "infra_or_provider_abort")
    assert _row_is_calibration_eligible(parser_row) == (False, "protocol_or_parser_abort")


def test_audit_calibration_downgrades_when_all_strategies_hit_cap(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    rows = []
    for strategy in (
        "bare_t2_baseline",
        "bare_t3_baseline",
        "budgetflow_task_level",
        "budgetflow_segment",
    ):
        rows.append({
            "strategy": strategy,
            "instance_id": "task-a",
            "total_cost": 0.99,
            "row_finished_at": 1,
        })
    jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    plan = BudgetBindingPlan(hard_cap_usd=1.0, target_projected_utilization=0.90)
    plan.projected_spend_by_strategy = {
        "bare_t2_baseline": 0.92,
        "bare_t3_baseline": 0.93,
        "budgetflow_task_level": 0.94,
        "budgetflow_segment": 0.95,
    }
    plan.projected_utilization_by_strategy = {
        key: value for key, value in plan.projected_spend_by_strategy.items()
    }

    audit = audit_calibration(jsonl, plan)

    assert audit.projection_confidence == "low"
    assert any("all primary strategies exhausted" in rec for rec in audit.recommendations)


def test_audit_records_raw_utilization_and_budget_exhaustion(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(json.dumps({
        "strategy": "bare_t3_baseline",
        "instance_id": "task-a",
        "total_cost": 1.4,
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "row_finished_at": 1,
    }) + "\n")
    plan = BudgetBindingPlan(hard_cap_usd=1.0)
    plan.projected_spend_by_strategy = {"bare_t3_baseline": 1.4}
    plan.projected_utilization_by_strategy = {"bare_t3_baseline": 1.0}
    plan.raw_projected_utilization_by_strategy = {"bare_t3_baseline": 1.4}

    audit = audit_calibration(jsonl, plan)

    err = audit.strategy_errors["bare_t3_baseline"]
    assert err["actual_utilization"] == 1.0
    assert err["raw_actual_utilization"] == 1.4
    assert err["budget_exhausted_rows"] == 1
    assert audit.budget_exhausted_by_strategy == {"bare_t3_baseline": 1}


def test_cli_calibrate_accepts_calibration_evidence_audit(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(CalibrationAudit(
        strategy_errors={
            "budgetflow_task_level": {
                "error_pct": 0.20,
                "projected": 0.8,
                "actual": 1.0,
            }
        },
        overall_mape=0.20,
        max_error_strategy="budgetflow_task_level",
        max_error_pct=0.20,
        projection_confidence="high",
    ).to_dict()))
    output_path = tmp_path / "budget_plan.json"

    rc = budget_binding_main([
        "calibrate",
        "--task-ids",
        "task-a,task-b",
        "--target-utilization",
        "0.8",
        "--calibration-evidence",
        str(audit_path),
        "--output",
        str(output_path),
    ])

    written = json.loads(output_path.read_text())
    assert rc == 0
    assert written["projection_confidence"] == "high"
    assert written["calibration_error"] == {"budgetflow_task_level": 0.2}

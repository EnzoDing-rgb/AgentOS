"""Tests for budget_binding.py — prove no task-id hardcoding in T3 estimation."""
from __future__ import annotations

import json
from pathlib import Path

from budgetflow.experiments.budget_binding import (
    _estimate_t3_cost_share,
    _load_frozen_preferred_models,
    _load_frozen_caps,
    _distribution_p75,
    _audit_pressure_shape,
    BudgetBindingPlan,
    calibrate_budget,
)


# ── _load_frozen_preferred_models ────────────────────────────────────────


def test_load_frozen_preferred_models_extracts_tier2_and_tier3(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({
        "plan": {
            "custom__project-1": {"preferred_model": "tier3", "base_cap": 0.5},
            "custom__project-2": {"preferred_model": "tier2", "base_cap": 0.3},
            "custom__project-3": {"base_cap": 0.2},
        }
    }))
    models = _load_frozen_preferred_models(plan_path)
    assert models == {"custom__project-1": "tier3", "custom__project-2": "tier2"}


def test_load_frozen_preferred_models_empty_when_no_preferred_model(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({
        "plan": {
            "task-a": {"base_cap": 0.1},
            "task-b": {"base_cap": 0.2},
        }
    }))
    models = _load_frozen_preferred_models(plan_path)
    assert models == {}


# ── _estimate_t3_cost_share — no task-id dependency ─────────────────────


def test_t3_share_reads_preferred_model_not_task_id() -> None:
    """T3 share for frozen-plan strategies comes from preferred_models, not task_id."""
    preferred = {"some_arbitrary__repo-999": "tier3"}
    share = _estimate_t3_cost_share(
        "enterprise_router_baseline",
        "some_arbitrary__repo-999",
        {},
        preferred_models=preferred,
    )
    assert share == 1.0


def test_t3_share_tier2_task_returns_zero() -> None:
    preferred = {"completely__different-task": "tier2"}
    share = _estimate_t3_cost_share(
        "budgetflow_same_router",
        "completely__different-task",
        {},
        preferred_models=preferred,
    )
    assert share == 0.0


def test_t3_share_task_not_in_preferred_models_returns_zero() -> None:
    """If preferred_models doesn't list the task, assume tier2 (conservative)."""
    share = _estimate_t3_cost_share(
        "enterprise_router_baseline",
        "missing__task-99999",
        {},
        preferred_models={"other__task-1": "tier2"},
    )
    assert share == 0.0


def test_t3_share_preferred_models_none_returns_zero() -> None:
    """When preferred_models is None (no frozen plan), conservative default."""
    share = _estimate_t3_cost_share(
        "enterprise_router_baseline",
        "sympy__sympy-16988",  # even this well-known id is not special
        {},
        preferred_models=None,
    )
    assert share == 0.0


def test_t3_share_bare_t3_always_one_regardless_of_preferred() -> None:
    share = _estimate_t3_cost_share(
        "bare_t3_baseline",
        "some_task",
        {},
        preferred_models={"some_task": "tier2"},
    )
    assert share == 1.0


def test_t3_share_bare_t2_always_zero_regardless_of_preferred() -> None:
    share = _estimate_t3_cost_share(
        "bare_t2_baseline",
        "some_task",
        {},
        preferred_models={"some_task": "tier3"},
    )
    assert share == 0.0


# ── No hardcoded task IDs remain ────────────────────────────────────────


def test_no_sympy_task_id_hardcoding() -> None:
    """Prove the source code doesn't hardcode 16988 or 20639."""
    import inspect
    source = inspect.getsource(_estimate_t3_cost_share)
    assert "16988" not in source
    assert "20639" not in source
    assert "sympy__" not in source.lower()


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
    assert plan.budget_mode == "target_utilization"
    assert plan.target_projected_utilization == 0.80
    assert any("reference_rule: strategy_set_p75" in r for r in plan.reasons)


def test_calibrate_target_utilization_hard_cap_not_frozen_cap_sum(tmp_path: Path) -> None:
    """When target_utilization is set, hard_cap is derived from p75, not frozen plan."""
    fp = tmp_path / "fp.json"
    fp.write_text(json.dumps({"plan": {"task-a": {"base_cap": 10.0, "preferred_model": "tier2"}}}))
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {"task-a": {"bootstrap_difficulty": 50.0}}}))
    plan = calibrate_budget(
        ["task-a"],
        frozen_plan_path=fp,
        value_matrix_path=vm,
        target_utilization=0.80,
        output_path=tmp_path / "bp.json",
    )
    # hard_cap must NOT equal frozen_cap_sum=10.0
    assert plan.hard_cap_usd != 10.0
    assert plan.decision != "BLOCK"


def test_calibrate_target_utilization_reference_is_not_budgetflow_specific(tmp_path: Path) -> None:
    """Reference rule is p75 of all 5 strategies — not budgetflow_full alone."""
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
    assert "budgetflow_full_projected" not in all_reasons
    assert "max_projected" not in all_reasons


def test_target_utilization_below_zero_raises() -> None:
    import pytest
    with pytest.raises(ValueError, match="target_utilization"):
        calibrate_budget(["task-a"], target_utilization=0.0)


def test_target_utilization_above_one_raises() -> None:
    import pytest
    with pytest.raises(ValueError, match="target_utilization"):
        calibrate_budget(["task-a"], target_utilization=1.5)


# ── pressure-shape audit ────────────────────────────────────────────────


def test_pressure_audit_is_passive_only() -> None:
    """Pressure audit writes into plan.reasons but never changes plan.decision."""
    plan = BudgetBindingPlan(
        hard_cap_usd=10.0,
        budget_mode="target_utilization",
        target_projected_utilization=0.80,
    )
    plan.projected_utilization_by_strategy = {
        "bare_t2_baseline": 0.30,
        "bare_t3_baseline": 0.20,
        "enterprise_router_baseline": 0.30,
        "budgetflow_same_router": 0.30,
        "budgetflow_full": 0.40,
    }
    original_decision = plan.decision
    _audit_pressure_shape(plan, ("bare_t2_baseline", "bare_t3_baseline"))
    assert plan.decision == original_decision
    assert any("WARNING" in r for r in plan.reasons)  # T3 < T2 → warning


def test_pressure_audit_healthy_shape_no_warning() -> None:
    """T3 > T2 = expected shape, no warning."""
    plan = BudgetBindingPlan(
        hard_cap_usd=5.0,
        budget_mode="target_utilization",
        target_projected_utilization=0.80,
    )
    plan.projected_utilization_by_strategy = {
        "bare_t2_baseline": 0.30,
        "bare_t3_baseline": 0.85,
        "enterprise_router_baseline": 0.50,
        "budgetflow_full": 0.60,
    }
    _audit_pressure_shape(plan, ())
    warnings = [r for r in plan.reasons if "WARNING" in r]
    assert len(warnings) == 0


def test_calibrate_without_target_uses_frozen_cap_sum(tmp_path: Path) -> None:
    """Without target_utilization, legacy frozen_plan_cap_sum mode is unchanged."""
    fp = tmp_path / "fp.json"
    fp.write_text(json.dumps({"plan": {"task-a": {"base_cap": 3.5, "preferred_model": "tier2"}}}))
    vm = tmp_path / "vm.json"
    vm.write_text(json.dumps({"tasks": {"task-a": {"bootstrap_difficulty": 20.0}}}))
    plan = calibrate_budget(
        ["task-a"],
        frozen_plan_path=fp,
        value_matrix_path=vm,
        output_path=tmp_path / "bp.json",
    )
    assert plan.budget_mode == "frozen_plan_cap_sum"
    assert plan.hard_cap_usd == 3.5

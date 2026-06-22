from __future__ import annotations

from budgetflow.frozen_router_plan_builder import build_router_only_plan


def test_build_router_only_plan_uses_value_effort_without_budget_caps() -> None:
    matrix = {
        "meta": {"name": "unit_matrix"},
        "tasks": {
            "easy": {
                "task_value": {"criticality_value": 1.0},
                "task_effort": {"final_task_effort": 20.0},
            },
            "high_value": {
                "task_value": {"criticality_value": 2.5},
                "task_effort": {"final_task_effort": 25.0},
            },
            "high_effort": {
                "task_value": {"criticality_value": 1.0},
                "task_effort": {"final_task_effort": 320.0},
            },
        },
    }

    plan = build_router_only_plan(
        matrix,
        task_ids=["easy", "high_value", "high_effort"],
        name="unit_router",
    )

    assert plan["meta"]["name"] == "unit_router"
    assert plan["meta"]["preferred_model_rule"] == (
        "tier3 for the top one-third by 0.5*criticality_value_percentile "
        "+ 0.5*task_effort_percentile; tier2 otherwise"
    )
    assert plan["plan"]["easy"]["preferred_model"] == "tier2"
    assert plan["plan"]["high_value"]["preferred_model"] == "tier3"
    assert plan["plan"]["high_effort"]["preferred_model"] == "tier3"
    assert plan["plan"]["high_value"]["priority"] > plan["plan"]["easy"]["priority"]
    assert plan["plan"]["high_effort"]["priority"] > plan["plan"]["easy"]["priority"]
    assert "hard_cap_usd" not in plan["meta"]
    assert "base_cap" not in plan["plan"]["easy"]

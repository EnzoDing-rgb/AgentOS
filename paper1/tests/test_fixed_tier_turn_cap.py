from __future__ import annotations

import pytest

try:
    from budgetflow.adapter.errors import BudgetFlowStagnationError
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
    from budgetflow.types import Backend
except ImportError:
    BudgetFlowLitellmModel = None


def _backend(tier: int) -> Backend:
    return Backend(
        name=f"tier{tier}",
        tier=tier,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.5,
        latency_ms=1,
    )


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_all_tier2_stops_at_catalog_turn_cap() -> None:
    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.step_index = 36
    model.routing = type("Routing", (), {"strategy": "all_tier2"})()
    model._turns_on_current_tier = 35
    model._no_progress_streak = 0

    with pytest.raises(BudgetFlowStagnationError) as excinfo:
        model._enforce_fixed_tier_turn_cap(_backend(2))

    assert excinfo.value.exit_reason == "tier2_turn_cap"
    assert excinfo.value.step_index == 36


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_enterprise_router_tier2_stops_at_catalog_turn_cap() -> None:
    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.step_index = 36
    model.routing = type("Routing", (), {"strategy": "enterprise_router"})()
    model._turns_on_current_tier = 35
    model._no_progress_streak = 0

    with pytest.raises(BudgetFlowStagnationError) as excinfo:
        model._enforce_fixed_tier_turn_cap(_backend(2))

    assert excinfo.value.exit_reason == "tier2_turn_cap"

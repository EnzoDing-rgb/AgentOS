from __future__ import annotations

import pytest

try:
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
except ImportError:
    BudgetFlowLitellmModel = None


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_gold_edit_stop_loss_grace_does_not_depend_on_patch_prep() -> None:
    model = object.__new__(BudgetFlowLitellmModel)
    model.agent_gold_edited = True
    model.agent_phase = "edit_gold"
    model._gold_edit_stop_loss_grace_turns = 0

    assert model._defer_gold_edit_stop_loss(True) is False
    assert model._defer_gold_edit_stop_loss(True) is False
    assert model._defer_gold_edit_stop_loss(True) is True


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_rescue_strongest_turn_is_not_immediately_downgraded() -> None:
    from budgetflow.types import Backend

    model = object.__new__(BudgetFlowLitellmModel)
    tier2 = Backend(
        name="tier2",
        tier=2,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.5,
        latency_ms=1,
    )
    tier3 = Backend(
        name="tier3",
        tier=3,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.7,
        latency_ms=1,
    )
    model.routing = type("Routing", (), {
        "strategy": "budgetflow_segment",
        "backends": [tier2, tier3],
    })()
    model._no_progress_on_current_tier = 99
    model._turns_on_current_tier = 99

    selected = model._apply_progress_escalation(tier3, protect_strongest_this_turn=True)

    assert selected is tier3
    assert model._no_progress_on_current_tier == 0
    assert model._turns_on_current_tier == 0

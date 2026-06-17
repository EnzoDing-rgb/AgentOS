from __future__ import annotations

import pytest

try:
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
except ImportError:
    BudgetFlowLitellmModel = None


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_fixed_tier_baselines_have_no_active_turn_cap() -> None:
    """Bare fixed-tier controls should be governed by budget and step limit."""
    assert not hasattr(BudgetFlowLitellmModel, "_enforce_fixed_tier_turn_cap")

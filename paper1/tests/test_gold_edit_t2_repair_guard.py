from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "external" / "mini-swe-agent" / "src"))

from budgetflow.adapter.backends import build_compare_backends  # noqa: E402
from budgetflow.adapter.errors import BudgetFlowStagnationError  # noqa: E402
from budgetflow.adapter.mini_swe_proxy import (  # noqa: E402
    BudgetFlowLitellmModel,
)
from budgetflow.adapter.strategies import build_routing_context  # noqa: E402
from budgetflow.defaults import GOLD_EDIT_T2_REPAIR_TURN_LIMIT  # noqa: E402
from budgetflow.types import Backend, Stage  # noqa: E402


def _model(strategy: str, backends: list[Backend]) -> BudgetFlowLitellmModel:
    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.routing = build_routing_context(strategy, backends, budget_pressure=0.01)
    model.step_index = 13
    model.agent_gold_edited = True
    model._gold_edit_t2_repair_turns = GOLD_EDIT_T2_REPAIR_TURN_LIMIT
    return model


@pytest.mark.parametrize("strategy", ["budgetflow_full", "budget_only"])
def test_gold_edit_t2_repair_guard_escalates_to_t3_after_limit(strategy: str) -> None:
    model = _model(strategy, build_compare_backends())
    t2 = next(backend for backend in model.routing.backends if backend.tier == 2)

    upgraded = model._apply_gold_edit_repair_guard(t2, Stage.REPAIR)

    assert upgraded.tier == 3
    assert upgraded.name != t2.name


def test_gold_edit_t2_repair_guard_raises_when_no_higher_tier_exists() -> None:
    model = _model("budgetflow_full", [build_compare_backends()[0]])
    t2 = model.routing.backends[0]

    with pytest.raises(BudgetFlowStagnationError) as excinfo:
        model._apply_gold_edit_repair_guard(t2, Stage.REPAIR)

    assert excinfo.value.exit_reason == "gold_edit_t2_repair_limit"

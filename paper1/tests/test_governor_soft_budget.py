from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.governor import BudgetGovernor
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.types import Backend, CostEstimate, GovernorConfig, WorkflowStatus


def _backend() -> Backend:
    return Backend(
        name="tier4",
        tier=4,
        cost_per_input_token=1.0,
        cost_per_output_token=1.0,
        rpm_limit=0,
        concurrency_limit=0,
        mean_output_tokens=1,
        progress_score=0.5,
        latency_ms=1,
    )


def _estimate(cost: float) -> CostEstimate:
    return CostEstimate(
        expected_cost=cost,
        reserved_cost=cost,
        expected_output_tokens=1,
        max_output_tokens=1,
    )


def test_soft_budget_allows_bounded_overrun_reservation() -> None:
    governor = BudgetGovernor(
        GovernorConfig(
            total_budget=100.0,
            default_max_output_tokens=100,
            soft_budget=80.0,
            max_overrun=25.0,
        ),
        WorkflowLedgerStore(),
    )

    reservation = governor.reserve("wf", _backend(), _estimate(95.0))

    assert reservation is not None
    assert governor.last_reserve_failure is None
    assert governor.budget_snapshot()["soft_budget"] == 80.0
    assert governor.budget_snapshot()["absolute_budget"] == 105.0


def test_soft_budget_rejects_reservation_beyond_overrun_guard() -> None:
    governor = BudgetGovernor(
        GovernorConfig(
            total_budget=100.0,
            default_max_output_tokens=100,
            soft_budget=80.0,
            max_overrun=10.0,
        ),
        WorkflowLedgerStore(),
    )

    reservation = governor.reserve("wf", _backend(), _estimate(95.0))

    assert reservation is None
    assert governor.last_reserve_failure == "overrun_guard"


def test_soft_budget_settle_clamps_to_absolute_budget() -> None:
    governor = BudgetGovernor(
        GovernorConfig(
            total_budget=100.0,
            default_max_output_tokens=100,
            soft_budget=80.0,
            max_overrun=10.0,
        ),
        WorkflowLedgerStore(),
    )
    reservation = governor.reserve("wf", _backend(), _estimate(90.0))
    assert reservation is not None

    governor.settle(reservation.reservation_id, actual_cost=120.0, status=WorkflowStatus.RUNNING)

    assert governor.state.spent_budget == 90.0
    assert governor.state.available_budget == 0.0
    assert governor.last_reserve_failure is None

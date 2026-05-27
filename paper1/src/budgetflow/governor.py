from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from .ledger import WorkflowLedgerStore
from .types import Backend, BackendPressure, BudgetState, CostEstimate, GovernorConfig, WorkflowStatus


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    workflow_id: str
    backend_name: str
    reserved_cost: float


class BudgetGovernor:
    """Hard budget reserve/settle. Provider RPM/concurrency left to the real API (Tier 1)."""

    def __init__(self, config: GovernorConfig, ledger: WorkflowLedgerStore) -> None:
        self.config = config
        self.ledger = ledger
        self.state = BudgetState(
            total_budget=config.total_budget,
            available_budget=config.total_budget,
        )
        self._lock = threading.Lock()
        self._active_reservations: dict[str, Reservation] = {}
        self.last_reserve_failure: str | None = None

    def estimate_cost(
        self,
        backend: Backend,
        input_tokens: int,
        max_output_tokens: int | None = None,
        expected_output_tokens: int | None = None,
        reserve_output_tokens: int | None = None,
    ) -> CostEstimate:
        bounded_max_output = max_output_tokens or self.config.default_max_output_tokens
        bounded_expected_output = expected_output_tokens or backend.mean_output_tokens
        bounded_reserve_output = (
            reserve_output_tokens if reserve_output_tokens is not None else bounded_max_output
        )
        expected_cost = (
            input_tokens * backend.cost_per_input_token
            + bounded_expected_output * backend.cost_per_output_token
        )
        reserved_cost = (
            input_tokens * backend.cost_per_input_token
            + bounded_reserve_output * backend.cost_per_output_token
        )
        return CostEstimate(
            expected_cost=expected_cost,
            reserved_cost=reserved_cost,
            expected_output_tokens=bounded_expected_output,
            max_output_tokens=bounded_max_output,
        )

    def budget_snapshot(self) -> dict[str, float]:
        return {
            "total_budget": self.state.total_budget,
            "available_budget": self.state.available_budget,
            "reserved_budget": self.state.reserved_budget,
            "spent_budget": self.state.spent_budget,
        }

    def backend_pressure(self, backend: Backend) -> BackendPressure:
        return BackendPressure(
            rpm_used=0,
            rpm_limit=backend.rpm_limit,
            concurrency_used=0,
            concurrency_limit=backend.concurrency_limit,
        )

    def can_dispatch(self, backend: Backend) -> bool:
        return self.state.available_budget > 0

    def _reserve_block_reason(self, reserved_cost: float) -> str | None:
        if reserved_cost > self.state.available_budget:
            return "budget_exhausted"
        return None

    def reserve(self, workflow_id: str, backend: Backend, estimate: CostEstimate) -> Reservation | None:
        with self._lock:
            block_reason = self._reserve_block_reason(estimate.reserved_cost)
            if block_reason is not None:
                self.last_reserve_failure = block_reason
                return None
            self.last_reserve_failure = None

            self.state.available_budget -= estimate.reserved_cost
            self.state.reserved_budget += estimate.reserved_cost

            reservation = Reservation(
                reservation_id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                backend_name=backend.name,
                reserved_cost=estimate.reserved_cost,
            )
            self._active_reservations[reservation.reservation_id] = reservation
            self.ledger.apply_reservation(workflow_id, estimate.reserved_cost)
            return reservation

    def settle(self, reservation_id: str, actual_cost: float, status: WorkflowStatus) -> Reservation:
        with self._lock:
            reservation = self._active_reservations.pop(reservation_id)
            refund = max(0.0, reservation.reserved_cost - actual_cost)
            self.state.reserved_budget -= reservation.reserved_cost
            self.state.available_budget += refund
            self.state.spent_budget += actual_cost
            self.ledger.settle(
                workflow_id=reservation.workflow_id,
                reserved_cost=reservation.reserved_cost,
                actual_cost=actual_cost,
                status=status,
            )
            return reservation

    def release(self, reservation_id: str, status: WorkflowStatus) -> Reservation:
        with self._lock:
            reservation = self._active_reservations.pop(reservation_id)
            self.state.reserved_budget -= reservation.reserved_cost
            self.state.available_budget += reservation.reserved_cost
            self.ledger.release(
                workflow_id=reservation.workflow_id,
                reserved_cost=reservation.reserved_cost,
                status=status,
            )
            return reservation

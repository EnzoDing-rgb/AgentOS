from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from .ledger import WorkflowLedgerStore
from .types import Backend, BudgetState, CostEstimate, GovernorConfig, WorkflowStatus


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    workflow_id: str
    backend_name: str
    reserved_cost: float


class BudgetGovernor:
    def __init__(self, config: GovernorConfig, ledger: WorkflowLedgerStore) -> None:
        self.config = config
        self.ledger = ledger
        self.state = BudgetState(
            total_budget=config.total_budget,
            available_budget=config.total_budget,
        )
        self._lock = threading.Lock()
        self._active_reservations: dict[str, Reservation] = {}
        self._backend_rpm: dict[str, int] = {}
        self._backend_concurrency: dict[str, int] = {}

    def estimate_cost(
        self,
        backend: Backend,
        input_tokens: int,
        max_output_tokens: int | None = None,
        expected_output_tokens: int | None = None,
    ) -> CostEstimate:
        bounded_max_output = max_output_tokens or self.config.default_max_output_tokens
        bounded_expected_output = expected_output_tokens or backend.mean_output_tokens
        expected_cost = (
            input_tokens * backend.cost_per_input_token
            + bounded_expected_output * backend.cost_per_output_token
        )
        reserved_cost = (
            input_tokens * backend.cost_per_input_token
            + bounded_max_output * backend.cost_per_output_token
        )
        return CostEstimate(
            expected_cost=expected_cost,
            reserved_cost=reserved_cost,
            expected_output_tokens=bounded_expected_output,
            max_output_tokens=bounded_max_output,
        )

    def can_dispatch(self, backend: Backend) -> bool:
        rpm_used = self._backend_rpm.get(backend.name, 0)
        concurrency_used = self._backend_concurrency.get(backend.name, 0)
        return rpm_used < backend.rpm_limit and concurrency_used < backend.concurrency_limit

    def reserve(self, workflow_id: str, backend: Backend, estimate: CostEstimate) -> Reservation | None:
        with self._lock:
            if estimate.reserved_cost > self.state.available_budget:
                return None
            if not self.can_dispatch(backend):
                return None

            self.state.available_budget -= estimate.reserved_cost
            self.state.reserved_budget += estimate.reserved_cost
            self._backend_rpm[backend.name] = self._backend_rpm.get(backend.name, 0) + 1
            self._backend_concurrency[backend.name] = self._backend_concurrency.get(backend.name, 0) + 1

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
            self._backend_concurrency[reservation.backend_name] = max(
                0,
                self._backend_concurrency.get(reservation.backend_name, 0) - 1,
            )
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
            self._backend_concurrency[reservation.backend_name] = max(
                0,
                self._backend_concurrency.get(reservation.backend_name, 0) - 1,
            )
            self.ledger.release(
                workflow_id=reservation.workflow_id,
                reserved_cost=reservation.reserved_cost,
                status=status,
            )
            return reservation

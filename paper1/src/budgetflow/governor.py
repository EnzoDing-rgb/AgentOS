from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from .ledger import WorkflowLedgerStore
from .model_tiers import estimate_token_cost
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
        self.soft_budget = config.soft_budget if config.soft_budget is not None else config.total_budget
        self.absolute_budget = (
            self.soft_budget + max(0.0, config.max_overrun)
            if config.soft_budget is not None
            else config.total_budget
        )
        self.ledger = ledger
        self.state = BudgetState(
            total_budget=self.absolute_budget,
            available_budget=self.absolute_budget,
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
        reserve_input_tokens: int | None = None,
        reserve_output_tokens: int | None = None,
        turn_index: int | None = None,
    ) -> CostEstimate:
        bounded_input = reserve_input_tokens if reserve_input_tokens is not None else input_tokens
        bounded_max_output = max_output_tokens or self.config.default_max_output_tokens
        bounded_expected_output = expected_output_tokens or backend.mean_output_tokens
        bounded_reserve_output = (
            reserve_output_tokens if reserve_output_tokens is not None else bounded_max_output
        )
        expected_cost = self._token_cost(
            backend,
            input_tokens=input_tokens,
            output_tokens=bounded_expected_output,
            turn_index=turn_index,
        )
        reserved_cost = self._token_cost(
            backend,
            input_tokens=bounded_input,
            output_tokens=bounded_reserve_output,
            turn_index=turn_index,
        )
        return CostEstimate(
            expected_cost=expected_cost,
            reserved_cost=reserved_cost,
            expected_output_tokens=bounded_expected_output,
            max_output_tokens=bounded_max_output,
            reserved_input_tokens=bounded_input,
            reserved_output_tokens=bounded_reserve_output,
        )

    def _token_cost(
        self,
        backend: Backend,
        *,
        input_tokens: int,
        output_tokens: int,
        turn_index: int | None = None,
    ) -> float:
        try:
            return estimate_token_cost(
                backend.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                turn_index=turn_index,
            )
        except ValueError:
            return (
                input_tokens * backend.cost_per_input_token
                + output_tokens * backend.cost_per_output_token
            )

    def budget_snapshot(self) -> dict[str, float]:
        return {
            "total_budget": self.state.total_budget,
            "soft_budget": self.soft_budget,
            "absolute_budget": self.absolute_budget,
            "max_overrun": max(0.0, self.absolute_budget - self.soft_budget),
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

    def remaining_budget(self) -> float:
        return max(0.0, self.state.total_budget - self.state.spent_budget - self.state.reserved_budget)

    def _remaining_budget(self) -> float:
        return self.remaining_budget()

    def _sync_available(self) -> None:
        self.state.available_budget = self._remaining_budget()

    def can_dispatch(self, backend: Backend) -> bool:
        return self._remaining_budget() > 0

    def _reserve_block_reason(self, reserved_cost: float) -> str | None:
        if self.state.spent_budget >= self.state.total_budget:
            return "budget_exhausted"
        if reserved_cost > self._remaining_budget():
            return "overrun_guard" if self.soft_budget < self.absolute_budget else "budget_exhausted"
        return None

    def reserve(self, workflow_id: str, backend: Backend, estimate: CostEstimate) -> Reservation | None:
        with self._lock:
            block_reason = self._reserve_block_reason(estimate.reserved_cost)
            if block_reason is not None:
                self.last_reserve_failure = block_reason
                return None
            self.last_reserve_failure = None

            self.state.reserved_budget += estimate.reserved_cost

            reservation = Reservation(
                reservation_id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                backend_name=backend.name,
                reserved_cost=estimate.reserved_cost,
            )
            self._active_reservations[reservation.reservation_id] = reservation
            self.ledger.apply_reservation(workflow_id, estimate.reserved_cost)
            self._sync_available()
            return reservation

    def settle(self, reservation_id: str, actual_cost: float, status: WorkflowStatus) -> Reservation:
        with self._lock:
            reservation = self._active_reservations.pop(reservation_id)
            self.state.reserved_budget -= reservation.reserved_cost

            remaining = self.state.total_budget - self.state.spent_budget
            billable = min(actual_cost, max(0.0, remaining))
            self.state.spent_budget += billable
            self._sync_available()
            self.ledger.settle(
                workflow_id=reservation.workflow_id,
                reserved_cost=reservation.reserved_cost,
                actual_cost=billable,
                status=status,
            )
            return reservation

    def release(self, reservation_id: str, status: WorkflowStatus) -> Reservation:
        with self._lock:
            reservation = self._active_reservations.pop(reservation_id)
            self.state.reserved_budget -= reservation.reserved_cost
            self._sync_available()
            self.ledger.release(
                workflow_id=reservation.workflow_id,
                reserved_cost=reservation.reserved_cost,
                status=status,
            )
            return reservation

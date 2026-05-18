from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from .types import LedgerEntry, WorkflowStatus


class WorkflowLedgerStore:
    def __init__(self) -> None:
        self._entries: dict[str, LedgerEntry] = {}

    def get(self, workflow_id: str) -> LedgerEntry:
        return self._entries.setdefault(workflow_id, LedgerEntry(workflow_id=workflow_id))

    def upsert(self, entry: LedgerEntry) -> LedgerEntry:
        self._entries[entry.workflow_id] = entry
        return entry

    def all(self) -> Iterable[LedgerEntry]:
        return self._entries.values()

    def start_step(self, workflow_id: str, step_index: int, backend_name: str, reservation_id: str) -> LedgerEntry:
        entry = self.get(workflow_id)
        updated = replace(
            entry,
            current_step=step_index,
            current_backend=backend_name,
            status=WorkflowStatus.RUNNING,
            active_reservation_id=reservation_id,
        )
        return self.upsert(updated)

    def apply_reservation(self, workflow_id: str, reserved_cost: float) -> LedgerEntry:
        entry = self.get(workflow_id)
        updated = replace(entry, reserved_cost=entry.reserved_cost + reserved_cost)
        return self.upsert(updated)

    def settle(self, workflow_id: str, reserved_cost: float, actual_cost: float, status: WorkflowStatus) -> LedgerEntry:
        entry = self.get(workflow_id)
        remaining_reserved = max(0.0, entry.reserved_cost - reserved_cost)
        updated = replace(
            entry,
            reserved_cost=remaining_reserved,
            actual_cost=entry.actual_cost + actual_cost,
            status=status,
            active_reservation_id=None,
        )
        return self.upsert(updated)

    def release(self, workflow_id: str, reserved_cost: float, status: WorkflowStatus) -> LedgerEntry:
        entry = self.get(workflow_id)
        remaining_reserved = max(0.0, entry.reserved_cost - reserved_cost)
        updated = replace(
            entry,
            reserved_cost=remaining_reserved,
            status=status,
            active_reservation_id=None,
        )
        return self.upsert(updated)

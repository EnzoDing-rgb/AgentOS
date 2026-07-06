from __future__ import annotations

import time
from dataclasses import dataclass

from .types import LedgerEntry


@dataclass(frozen=True)
class ZombieEvent:
    workflow_id: str
    reason: str
    detected_at: float


class ZombieDetector:
    def __init__(self, timeout_seconds: float, repeat_action_limit: int = 3) -> None:
        self.timeout_seconds = timeout_seconds
        self.repeat_action_limit = repeat_action_limit

    def detect_timeout(self, entry: LedgerEntry, now: float | None = None) -> ZombieEvent | None:
        current_time = now or time.time()
        if entry.last_event_at is None:
            return None
        if current_time - entry.last_event_at <= self.timeout_seconds:
            return None
        return ZombieEvent(
            workflow_id=entry.workflow_id,
            reason="timeout",
            detected_at=current_time,
        )

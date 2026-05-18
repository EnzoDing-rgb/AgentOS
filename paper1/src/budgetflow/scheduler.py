from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import Backend


class SchedulerDecision(str, Enum):
    DISPATCH = "dispatch"
    QUEUE = "queue"
    REJECT = "reject"
    DOWNGRADE = "downgrade"


@dataclass
class WorkflowScheduler:
    queue_limit: int = 0
    queue_depth: int = 0

    def decide(self, preferred: Backend, fallback: Backend | None, can_dispatch_preferred: bool, can_dispatch_fallback: bool) -> SchedulerDecision:
        if can_dispatch_preferred:
            return SchedulerDecision.DISPATCH
        if fallback is not None and can_dispatch_fallback:
            return SchedulerDecision.DOWNGRADE
        if self.queue_depth < self.queue_limit:
            self.queue_depth += 1
            return SchedulerDecision.QUEUE
        return SchedulerDecision.REJECT

    def complete_queued(self) -> None:
        if self.queue_depth > 0:
            self.queue_depth -= 1

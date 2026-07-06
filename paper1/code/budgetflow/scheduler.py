from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class SchedulerDecision(str, Enum):
    DISPATCH = "dispatch"
    QUEUE = "queue"
    REJECT = "reject"


@dataclass
class WorkflowScheduler:
    queue_limit: int = 0
    queue_depth: int = 0

    def decide(self, can_dispatch_preferred: bool) -> SchedulerDecision:
        if can_dispatch_preferred:
            return SchedulerDecision.DISPATCH
        if self.queue_depth < self.queue_limit:
            self.queue_depth += 1
            return SchedulerDecision.QUEUE
        return SchedulerDecision.REJECT

    def complete_queued(self) -> None:
        if self.queue_depth > 0:
            self.queue_depth -= 1

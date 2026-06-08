"""Learn Policy support types.

BudgetFlow core does not own learning algorithms. Built-in Memory can be used
by a Learn Policy or for audit, and customers can replace it with their own
machine-learning policy backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .types import Stage


class CostMemory(Protocol):
    @property
    def records(self) -> list[dict]:
        ...


class RoutingMemory(Protocol):
    def routing_prior_summary(self, instance_id: str, stage: Stage | None = None) -> dict:
        ...


class EscalationMemory(Protocol):
    def routing_prior_summary(self, instance_id: str, stage: Stage | None = None) -> dict:
        ...


@dataclass(frozen=True)
class LearnMemoryBundle:
    """Optional Memory inputs for Learn Policy and audit."""

    cost: CostMemory | None = None
    routing: RoutingMemory | None = None
    escalation: EscalationMemory | None = None
    source: str = ""
    mode: str = "off"

    @property
    def enabled(self) -> bool:
        return self.cost is not None or self.routing is not None or self.escalation is not None

    @classmethod
    def off(cls, reason: str = "") -> LearnMemoryBundle:
        return cls(source=reason, mode="off")

    @classmethod
    def built_in(
        cls,
        *,
        cost: CostMemory | None = None,
        routing: RoutingMemory | None = None,
        escalation: EscalationMemory | None = None,
        source: str = "",
    ) -> LearnMemoryBundle:
        return cls(
            cost=cost,
            routing=routing,
            escalation=escalation,
            source=source,
            mode="built_in",
        )

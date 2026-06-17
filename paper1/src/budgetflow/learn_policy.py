"""Learn Policy support types.

BudgetFlow Mechanism does not own learning algorithms. Built-in Memory can be used
by a Learn Policy or for audit, and customers can replace it with their own
machine-learning policy backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RoutingMemory(Protocol):
    def routing_prior_summary(self, instance_id: str, segment: str | None = None) -> dict:
        ...


class EscalationMemory(Protocol):
    def routing_prior_summary(self, instance_id: str, segment: str | None = None) -> dict:
        ...


@dataclass(frozen=True)
class LearnPolicyInputs:
    """Optional Memory inputs for Learn Policy and audit."""

    routing: RoutingMemory | None = None
    escalation: EscalationMemory | None = None
    source: str = ""
    mode: str = "off"

    @property
    def enabled(self) -> bool:
        return self.routing is not None or self.escalation is not None

    @property
    def routing_enabled(self) -> bool:
        return self.routing is not None or self.escalation is not None

    @property
    def active_views(self) -> tuple[str, ...]:
        views: list[str] = []
        if self.routing is not None:
            views.append("routing")
        if self.escalation is not None:
            views.append("escalation")
        return tuple(views)

    @classmethod
    def off(cls, reason: str = "") -> LearnPolicyInputs:
        return cls(source=reason, mode="off")

    @classmethod
    def built_in(
        cls,
        *,
        routing: RoutingMemory | None = None,
        escalation: EscalationMemory | None = None,
        source: str = "",
    ) -> LearnPolicyInputs:
        return cls(
            routing=routing,
            escalation=escalation,
            source=source,
            mode="built_in",
        )

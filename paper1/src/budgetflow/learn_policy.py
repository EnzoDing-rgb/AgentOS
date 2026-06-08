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

    @property
    def routing_enabled(self) -> bool:
        return self.routing is not None or self.escalation is not None

    @property
    def active_views(self) -> tuple[str, ...]:
        views: list[str] = []
        if self.cost is not None:
            views.append("cost")
        if self.routing is not None:
            views.append("routing")
        if self.escalation is not None:
            views.append("escalation")
        return tuple(views)

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


def combine_memory_views(
    *,
    cost: CostMemory | None = None,
    routing_bundle: LearnMemoryBundle | None = None,
    source: str = "",
) -> LearnMemoryBundle:
    """Build one LearnMemoryBundle from independent memory views."""
    routing_bundle = routing_bundle or LearnMemoryBundle.off()
    combined_source = source or routing_bundle.source
    if source and routing_bundle.source:
        combined_source = f"{source},{routing_bundle.source}"
    return LearnMemoryBundle.built_in(
        cost=cost,
        routing=routing_bundle.routing,
        escalation=routing_bundle.escalation,
        source=combined_source,
    )

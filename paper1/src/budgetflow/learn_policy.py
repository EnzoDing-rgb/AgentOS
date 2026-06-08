"""Learn Policy support types.

BudgetFlow Mechanism does not own learning algorithms. Built-in Memory can be used
by a Learn Policy or for audit, and customers can replace it with their own
machine-learning policy backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

class CostMemory(Protocol):
    @property
    def records(self) -> list[dict]:
        ...


class RoutingMemory(Protocol):
    def routing_prior_summary(self, instance_id: str, segment: str | None = None) -> dict:
        ...


class EscalationMemory(Protocol):
    def routing_prior_summary(self, instance_id: str, segment: str | None = None) -> dict:
        ...


@dataclass(frozen=True)
class LearnPolicyInputs:
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
    def off(cls, reason: str = "") -> LearnPolicyInputs:
        return cls(source=reason, mode="off")

    @classmethod
    def built_in(
        cls,
        *,
        cost: CostMemory | None = None,
        routing: RoutingMemory | None = None,
        escalation: EscalationMemory | None = None,
        source: str = "",
    ) -> LearnPolicyInputs:
        return cls(
            cost=cost,
            routing=routing,
            escalation=escalation,
            source=source,
            mode="built_in",
        )


def combine_learn_policy_inputs(
    *,
    cost: CostMemory | None = None,
    routing_inputs: LearnPolicyInputs | None = None,
    source: str = "",
) -> LearnPolicyInputs:
    """Build one LearnPolicyInputs from independent memory views."""
    routing_inputs = routing_inputs or LearnPolicyInputs.off()
    combined_source = source or routing_inputs.source
    if source and routing_inputs.source:
        combined_source = f"{source},{routing_inputs.source}"
    return LearnPolicyInputs.built_in(
        cost=cost,
        routing=routing_inputs.routing,
        escalation=routing_inputs.escalation,
        source=combined_source,
    )

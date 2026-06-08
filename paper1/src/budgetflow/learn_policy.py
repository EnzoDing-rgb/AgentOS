"""Learn Policy support types.

BudgetFlow core does not own learning algorithms. Built-in Memory can be used
by a Learn Policy or for audit, and customers can replace it with their own
machine-learning policy backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .types import Stage


class RoutingMemory(Protocol):
    def routing_prior_summary(self, instance_id: str, stage: Stage | None = None) -> dict:
        ...


@dataclass(frozen=True)
class LearnMemoryBundle:
    """Optional Memory inputs for Learn Policy and audit."""

    routing: RoutingMemory | None = None
    source: str = ""
    mode: str = "off"

    @property
    def enabled(self) -> bool:
        return self.routing is not None

    @classmethod
    def off(cls, reason: str = "") -> LearnMemoryBundle:
        return cls(routing=None, source=reason, mode="off")

    @classmethod
    def built_in(cls, routing: RoutingMemory, source: str = "") -> LearnMemoryBundle:
        return cls(routing=routing, source=source, mode="built_in")

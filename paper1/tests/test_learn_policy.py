from __future__ import annotations

from budgetflow.learn_policy import LearnMemoryBundle
from budgetflow.types import Stage


class FakeRoutingMemory:
    def routing_prior_summary(self, instance_id: str, stage: Stage | None = None) -> dict:
        return {"instance_id": instance_id, "stage": stage.value if stage else ""}


class FakeCostMemory:
    @property
    def records(self) -> list[dict]:
        return [{"instance_id": "task-a"}]


def test_learn_memory_bundle_defaults_to_off() -> None:
    bundle = LearnMemoryBundle.off("bootstrap")

    assert bundle.enabled is False
    assert bundle.mode == "off"
    assert bundle.source == "bootstrap"
    assert bundle.cost is None
    assert bundle.routing is None
    assert bundle.escalation is None


def test_learn_memory_bundle_can_wrap_built_in_memory_views() -> None:
    cost = FakeCostMemory()
    routing = FakeRoutingMemory()
    escalation = FakeRoutingMemory()
    bundle = LearnMemoryBundle.built_in(
        cost=cost,
        routing=routing,
        escalation=escalation,
        source="policy_memory",
    )

    assert bundle.enabled is True
    assert bundle.mode == "built_in"
    assert bundle.source == "policy_memory"
    assert bundle.cost is cost
    assert bundle.routing is routing
    assert bundle.escalation is escalation
    assert bundle.routing.routing_prior_summary("task-a", Stage.REPAIR)["stage"] == "repair"

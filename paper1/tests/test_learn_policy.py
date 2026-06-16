from __future__ import annotations

from budgetflow.learn_policy import LearnPolicyInputs, combine_learn_policy_inputs
from budgetflow.types import Stage


class FakeRoutingMemory:
    def routing_prior_summary(self, instance_id: str, stage: Stage | None = None) -> dict:
        return {"instance_id": instance_id, "stage": stage.value if stage else ""}


class FakeCostMemory:
    @property
    def records(self) -> list[dict]:
        return [{"instance_id": "task-a"}]


def test_learn_policy_inputs_defaults_to_off() -> None:
    bundle = LearnPolicyInputs.off("bootstrap")

    assert bundle.enabled is False
    assert bundle.mode == "off"
    assert bundle.source == "bootstrap"
    assert bundle.cost is None
    assert bundle.routing is None
    assert bundle.escalation is None


def test_learn_policy_inputs_can_wrap_built_in_memory_views() -> None:
    cost = FakeCostMemory()
    routing = FakeRoutingMemory()
    escalation = FakeRoutingMemory()
    bundle = LearnPolicyInputs.built_in(
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
    assert bundle.active_views == ("cost", "routing", "escalation")
    assert bundle.routing.routing_prior_summary("task-a", Stage.REPAIR)["stage"] == "repair"


def test_learn_policy_inputs_reaches_adaptive_routing_state() -> None:
    from budgetflow.adaptive_routing import AdaptiveRoutingRegistry

    routing = FakeRoutingMemory()
    bundle = LearnPolicyInputs.built_in(
        routing=routing,
        escalation=routing,
        source="unit-routing-memory",
    )
    registry = AdaptiveRoutingRegistry(learn_policy_inputs=bundle)

    state = registry.for_strategy("bootstrap_value", "segment_value_aware")

    assert state is not None
    assert registry.learn_policy_inputs is bundle
    assert registry.policy_memory is routing
    assert state.policy_memory is routing
    assert state.memory_mode == "built_in"


def test_task_level_value_policy_gets_adaptive_routing_state() -> None:
    from budgetflow.adaptive_routing import AdaptiveRoutingRegistry

    routing = FakeRoutingMemory()
    bundle = LearnPolicyInputs.built_in(
        routing=routing,
        escalation=routing,
        source="unit-routing-memory",
    )
    registry = AdaptiveRoutingRegistry(learn_policy_inputs=bundle)

    state = registry.for_strategy("budgetflow_task_level", "value_aware_task_level")

    assert state is not None
    assert state.policy_memory is routing
    assert state.memory_mode == "built_in"


def test_cost_only_memory_does_not_enable_routing_memory_mode() -> None:
    from budgetflow.adaptive_routing import AdaptiveRoutingRegistry

    bundle = combine_learn_policy_inputs(cost=FakeCostMemory(), routing_inputs=LearnPolicyInputs.off("no-routing"))
    registry = AdaptiveRoutingRegistry(learn_policy_inputs=bundle)
    state = registry.for_strategy("bootstrap_value", "segment_value_aware")

    assert bundle.active_views == ("cost",)
    assert registry.memory_mode == "off"
    assert registry.policy_memory is None
    assert state is not None
    assert state.policy_memory is None
    assert state.memory_mode == "off"

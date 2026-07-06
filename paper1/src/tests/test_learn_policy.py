from __future__ import annotations

from budgetflow.learn_policy import LearnPolicyInputs
from budgetflow.types import Stage


class FakeRoutingMemory:
    def routing_prior_summary(self, instance_id: str, stage: Stage | None = None) -> dict:
        return {"instance_id": instance_id, "stage": stage.value if stage else ""}


def test_learn_policy_inputs_defaults_to_off() -> None:
    bundle = LearnPolicyInputs.off("bootstrap")

    assert bundle.enabled is False
    assert bundle.mode == "off"
    assert bundle.source == "bootstrap"
    assert bundle.routing is None
    assert bundle.escalation is None


def test_learn_policy_inputs_can_wrap_built_in_memory_views() -> None:
    routing = FakeRoutingMemory()
    escalation = FakeRoutingMemory()
    bundle = LearnPolicyInputs.built_in(
        routing=routing,
        escalation=escalation,
        source="policy_memory",
    )

    assert bundle.enabled is True
    assert bundle.mode == "built_in"
    assert bundle.source == "policy_memory"
    assert bundle.routing is routing
    assert bundle.escalation is escalation
    assert bundle.active_views == ("routing", "escalation")
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

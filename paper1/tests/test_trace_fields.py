from __future__ import annotations

import pytest

from budgetflow.adapter.mini_swe_proxy import (
    BudgetFlowLitellmModel,
)
from budgetflow.adapter.turn_trace import (
    build_turn_trace,
    protocol_trace_fields,
    provider_trace_fields,
)
from budgetflow.adapter.strategies import build_routing_context
from budgetflow.types import Backend, Stage


def _backend(name: str, tier: int) -> Backend:
    return Backend(name, tier, 0.001 * tier, 0.002 * tier, 60, 1, 1024, 0.5, 100)


def test_turn_trace_has_fields_needed_to_debug_value_routing_and_provider_failures() -> None:
    trace = build_turn_trace(
        step_index=1,
        agent_phase="edit_gold",
        stage=Stage.REPAIR,
        bash_command="git diff",
        input_tokens=100,
        expected_costs={"tier2": 0.01},
        base_pressure=0.1,
        effective_pressure=0.2,
        backend_chosen="tier2",
        escalated_backend="tier3",
        final_backend="tier3",
        backend_tier=3,
        reserve_out=512,
        adaptive=None,
        no_progress_streak=4,
        no_progress_on_tier=3,
        turns_on_tier=2,
        has_progress=True,
        progress_reason="repair_pattern",
        prompt_tokens=100,
        completion_tokens=50,
        actual_cost=0.02,
        billable=0.02,
        response_ok=False,
        error_type="ServiceUnavailableError",
        provider="openai_compatible",
        model="openai/gpt-5.4",
        text_mode=True,
        protocol="text_regex",
        parser="parse_regex_actions",
        provider_status_code=503,
        router_reason="value_triggered_escalation",
        router_branch="budgetflow_value_aware",
        task_value=2.0,
        task_value_multiplier=1.5,
        value_aware_active=True,
        value_triggered_escalation_active=True,
        value_triggered_escalation_turns_remaining=2,
        value_triggered_escalation_opened=True,
        value_triggered_escalation_reason="opened_stagnation_no_progress",
        value_triggered_escalation_action="default",
        value_triggered_escalation_window=3,
    )

    assert trace["turns_on_tier"] == 2
    assert trace["provider"] == "openai_compatible"
    assert trace["protocol"] == "text_regex"
    assert trace["provider_status_code"] == 503
    assert trace["router_branch"] == "budgetflow_value_aware"
    assert trace["task_value_multiplier"] == 1.5
    assert trace["value_triggered_escalation_active"] is True
    assert trace["value_triggered_escalation_turns_remaining"] == 2
    assert trace["value_triggered_escalation_opened"] is True
    assert trace["value_triggered_escalation_action"] == "default"
    assert "value_salvage_active" not in trace


def test_provider_and_protocol_helpers_identify_real_backend_contracts() -> None:
    assert provider_trace_fields("tier2")["provider"] == "openai_compatible"
    assert "gpt-5.4" in provider_trace_fields("tier3")["model"]
    assert protocol_trace_fields("tier3", text_mode=True)["protocol"] == "text_regex"
    assert protocol_trace_fields("tier2", text_mode=False)["protocol"] == "tool_call"


@pytest.mark.parametrize(
    ("task_value", "strategy", "opens"),
    [
        (2.0, "budgetflow_value_aware", True),
        (0.5, "budgetflow_value_aware", False),
        (2.0, "budgetflow_conservative", False),
    ],
)
def test_value_triggered_escalation_only_opens_for_high_value_bfv(task_value: float, strategy: str, opens: bool) -> None:
    t2 = _backend("tier2", 2)
    t3 = _backend("tier3", 3)
    model = object.__new__(BudgetFlowLitellmModel)
    model.routing = build_routing_context(
        strategy,
        [t2, t3],
        budget_pressure=0.01,
        task_value=task_value,
        median_task_value=1.0,
    )
    model._value_triggered_escalation_turns_remaining = 0
    model._value_triggered_escalation_opened = False
    model._value_triggered_escalation_reason = None
    model._value_triggered_escalation_action = "default"
    model._value_triggered_escalation_window = 3
    model._no_progress_on_current_tier = 12
    model._turns_on_current_tier = 12
    model.agent_gold_edited = False
    model.step_index = 12

    class Governor:
        class State:
            total_budget = 1.0

        state = State()

        def remaining_budget(self):
            return 0.8

    model.governor = Governor()

    assert model._maybe_open_value_triggered_escalation("stagnation_no_progress") is opens


def test_value_triggered_escalation_honors_memory_disable_window() -> None:
    t2 = _backend("tier2", 2)
    t3 = _backend("tier3", 3)

    class Adaptive:
        _prior_summary = {
            "value_triggered_escalation_action": "disable_value_triggered_escalation",
            "value_triggered_escalation_window": 0,
        }

    model = object.__new__(BudgetFlowLitellmModel)
    model.routing = build_routing_context(
        "budgetflow_value_aware",
        [t2, t3],
        budget_pressure=0.01,
        adaptive=Adaptive(),
        task_value=2.0,
        median_task_value=1.0,
    )
    model._value_triggered_escalation_turns_remaining = 0
    model._value_triggered_escalation_opened = False
    model._value_triggered_escalation_reason = None
    model._value_triggered_escalation_action = "default"
    model._value_triggered_escalation_window = 3
    model.agent_gold_edited = False
    model.step_index = 12

    class Governor:
        class State:
            total_budget = 1.0

        state = State()

        def remaining_budget(self):
            return 0.8

    model.governor = Governor()

    assert model._maybe_open_value_triggered_escalation("stagnation_no_progress") is False
    assert model._value_triggered_escalation_action == "disable_value_triggered_escalation"
    assert model._value_triggered_escalation_window == 0

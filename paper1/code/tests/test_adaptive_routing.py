from __future__ import annotations

from budgetflow.adaptive_routing import AdaptiveRoutingState, EvidenceRescueState, rescue_state_for_strategy
from budgetflow.types import WorkflowSegment


def _fail_record(**extra) -> dict:
    record = {
        "harness_resolved": False,
        "patch_extracted": False,
        "exit_reason": "stagnation_repeat_command",
        "agent_gold_edited": False,
    }
    record.update(extra)
    return record


def test_runtime_state_resets_between_tasks() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_segment")
    state.rescue.evidence_turns = 10
    state.rescue.window_opened = True
    state.ttl_steps_remaining = 2

    state.reset_task_runtime()

    assert state.rescue.evidence_turns == 0
    assert not state.rescue.window_opened
    assert state.prior_summary_for_trace() is None


def test_starting_tier_can_skip_t1_but_never_starts_t3() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_segment")
    for _ in range(10):
        state.record_task(_fail_record())

    assert state.starting_tier() == 2


def test_t3_rescue_requires_gold_edit_repair_stage_and_headroom() -> None:
    rescue = EvidenceRescueState(trigger_turns=2, window_turns=2, min_headroom_frac=0.20)

    assert rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=False,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) is None
    assert rescue.forced_min_tier(
        segment=WorkflowSegment.CONTEXT,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) is None
    assert rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=10,
        total_budget=100,
    ) is None

    rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    )
    assert rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3


def test_rescue_window_stop_loss_prevents_expensive_spinning() -> None:
    rescue = EvidenceRescueState(trigger_turns=1, window_turns=2, stop_loss_turns=3)

    assert rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3
    assert rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3
    rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    )

    assert rescue.should_stop_loss(gold_edited=True)


def test_rescue_stop_loss_waits_until_after_last_rescue_turn() -> None:
    rescue = EvidenceRescueState(trigger_turns=1, window_turns=3, stop_loss_turns=1)

    for _ in range(3):
        assert rescue.forced_min_tier(
            segment=WorkflowSegment.ACTION,
            gold_edited=True,
            current_tier=2,
            remaining_budget=100,
            total_budget=100,
        ) == 3
        assert not rescue.should_stop_loss(gold_edited=True)

    assert rescue.forced_min_tier(
        segment=WorkflowSegment.ACTION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) is None
    assert rescue.should_stop_loss(gold_edited=True)


def test_value_aware_default_rescue_is_bounded() -> None:
    rescue = rescue_state_for_strategy("segment_value_aware")

    assert rescue.trigger_turns <= 6
    assert rescue.window_turns <= 3
    assert rescue.stop_loss_turns <= 6


def test_value_aware_task_level_learns_but_does_not_switch_in_task() -> None:
    from budgetflow.routing_sets import (
        ADAPTIVE_ROUTINGS,
        IN_TASK_SWITCHING_ROUTINGS,
        VALUE_TRIGGERED_ESCALATION_ROUTINGS,
    )

    assert "value_aware_task_level" in ADAPTIVE_ROUTINGS
    assert "value_aware_task_level" not in IN_TASK_SWITCHING_ROUTINGS
    assert "value_aware_task_level" not in VALUE_TRIGGERED_ESCALATION_ROUTINGS

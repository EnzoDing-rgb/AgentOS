from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.adaptive_routing import AdaptiveRoutingState, EvidenceRescueState, rescue_state_for_strategy
from budgetflow.types import Stage


def _fail_record(**extra) -> dict:
    base = {
        "harness_resolved": False,
        "patch_extracted": False,
        "exit_reason": "stagnation_repeat_command",
        "agent_gold_edited": False,
    }
    base.update(extra)
    return base


def test_weak_window_raises_pressure_and_ttl() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    state.record_task(_fail_record())
    state.record_task(_fail_record(agent_gold_edited=True))
    assert state.pressure_boost == 0.0
    assert state.ttl_steps_remaining > 0
    assert state.min_tier_for_reserve() >= 2


def test_effective_pressure_capped() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_loose")
    state.pressure_boost = 0.5
    assert state.effective_pressure(1.0) <= 1.5


def test_strong_results_decay_boost() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    for _ in range(3):
        state.record_task(_fail_record())
    assert state.ttl_steps_remaining > 0
    assert state.min_tier_for_reserve() >= 2
    for _ in range(5):
        state.record_task({"harness_resolved": True, "patch_extracted": True})
    assert state.pressure_boost == 0.0
    assert state.ttl_steps_remaining == 0


def test_task_runtime_state_resets_rescue_between_tasks() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    state.rescue.evidence_turns = 10
    state.rescue.window_opened = True

    state.reset_task_runtime()

    assert state.rescue.evidence_turns == 0
    assert not state.rescue.window_opened


def test_on_step_ticks_ttl() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    state.ttl_steps_remaining = 2
    state.on_step()
    assert state.ttl_steps_remaining == 1


def test_evidence_rescue_opens_one_bounded_window_after_gold_repair_stalls() -> None:
    rescue = EvidenceRescueState(trigger_turns=3, window_turns=2, min_headroom_frac=0.20)

    assert rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=False,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) is None

    rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    )
    rescue.forced_min_tier(
        stage=Stage.VALIDATION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    )

    assert rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3
    assert rescue.forced_min_tier(
        stage=Stage.VALIDATION,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3
    assert rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) is None


def test_evidence_rescue_respects_budget_headroom() -> None:
    rescue = EvidenceRescueState(trigger_turns=1, window_turns=2, min_headroom_frac=0.20)

    assert rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=10,
        total_budget=100,
    ) is None


def test_evidence_rescue_does_not_consume_window_without_real_gold_edit() -> None:
    rescue = EvidenceRescueState(trigger_turns=2, window_turns=2, min_headroom_frac=0.20)

    for _ in range(5):
        assert rescue.forced_min_tier(
            stage=Stage.REPAIR,
            gold_edited=False,
            current_tier=2,
            remaining_budget=100,
            total_budget=100,
        ) is None

    assert rescue.evidence_turns == 0
    assert not rescue.window_opened

    rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    )
    assert rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3


def test_evidence_rescue_stop_loss_after_window_and_patience() -> None:
    rescue = EvidenceRescueState(trigger_turns=1, window_turns=2, stop_loss_turns=3)

    assert not rescue.should_stop_loss(gold_edited=True)
    assert rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3
    assert rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    ) == 3
    assert not rescue.should_stop_loss(gold_edited=True)

    rescue.forced_min_tier(
        stage=Stage.REPAIR,
        gold_edited=True,
        current_tier=2,
        remaining_budget=100,
        total_budget=100,
    )

    assert rescue.should_stop_loss(gold_edited=True)


def test_auto_v2_rescue_waits_longer_and_uses_shorter_t3_window() -> None:
    current = rescue_state_for_strategy("budgetflow_full")
    v2 = rescue_state_for_strategy("budgetflow_auto_v2")

    assert v2.trigger_turns > current.trigger_turns
    assert v2.window_turns < current.window_turns
    assert v2.stop_loss_turns > current.stop_loss_turns
    assert v2.min_headroom_frac > current.min_headroom_frac


def test_auto_v2_rescue_targets_t3_conservatively() -> None:
    v2 = rescue_state_for_strategy("budgetflow_auto_v2")

    assert v2.rescue_tier == 3
    assert v2.trigger_turns == 12
    assert v2.window_turns == 2
    assert v2.min_headroom_frac == 0.30

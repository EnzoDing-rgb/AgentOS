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


def test_equal_weight_uses_same_rescue_parameters_as_budgetflow_full() -> None:
    current = rescue_state_for_strategy("budgetflow_full")
    equal_weight = rescue_state_for_strategy("budgetflow_equal_weight")

    assert equal_weight.trigger_turns == current.trigger_turns
    assert equal_weight.window_turns == current.window_turns
    assert equal_weight.stop_loss_turns == current.stop_loss_turns
    assert equal_weight.min_headroom_frac == current.min_headroom_frac
    assert equal_weight.rescue_tier == current.rescue_tier


def test_default_rescue_stop_loss_is_tight_after_gold_edit() -> None:
    rescue = rescue_state_for_strategy("budgetflow_value_aware")

    assert rescue.stop_loss_turns <= 6


def test_legacy_auto_v2_alias_uses_equal_weight_rescue_parameters() -> None:
    current = rescue_state_for_strategy("budgetflow_full")
    legacy = rescue_state_for_strategy("budgetflow_auto_v2")

    assert legacy.trigger_turns == current.trigger_turns
    assert legacy.window_turns == current.window_turns
    assert legacy.stop_loss_turns == current.stop_loss_turns
    assert legacy.min_headroom_frac == current.min_headroom_frac
    assert legacy.rescue_tier == current.rescue_tier


# ── T3 must be evidence-triggered (not from history) ─────────────────────────

def test_starting_tier_never_returns_t3_from_history() -> None:
    """Four consecutive fails should NOT push starting_tier to 3."""
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    for _ in range(4):
        state.record_task(_fail_record())
    assert state.starting_tier() == 2  # capped at T2, never T3


def test_starting_tier_returns_t2_after_two_fails() -> None:
    """Two consecutive fails allow skipping T1 but not T2."""
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_loose")
    state.record_task(_fail_record())
    state.record_task(_fail_record())
    assert state.starting_tier() == 2


def test_starting_tier_resets_after_pass() -> None:
    """A resolved task resets the streak to 0 → T1."""
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    state.record_task(_fail_record())
    state.record_task(_fail_record())
    assert state.starting_tier() == 2
    state.record_task({"harness_resolved": True, "patch_extracted": True})
    assert state.starting_tier() == 1


def test_starting_tier_ten_fails_still_t2() -> None:
    """Even with many consecutive fails, starting_tier stays at T2."""
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_loose")
    for _ in range(10):
        state.record_task(_fail_record())
    assert state.starting_tier() == 2


def test_t3_rescue_only_triggers_with_gold_edit_plus_repair() -> None:
    """T3 rescue window requires gold_edited=True AND repair/validation stage."""
    rescue = EvidenceRescueState(trigger_turns=2, window_turns=2, min_headroom_frac=0.10)

    # Without gold edit: no T3
    assert rescue.forced_min_tier(
        stage=Stage.REPAIR, gold_edited=False, current_tier=2,
        remaining_budget=100, total_budget=100,
    ) is None

    # Gold edit in LOCALIZATION stage: no T3 (must be REPAIR or VALIDATION)
    assert rescue.forced_min_tier(
        stage=Stage.LOCALIZATION, gold_edited=True, current_tier=2,
        remaining_budget=100, total_budget=100,
    ) is None


def test_rescue_window_closes_and_stop_loss_fires() -> None:
    """Rescue window is bounded: after window exhausted, stop_loss fires."""
    rescue = EvidenceRescueState(trigger_turns=1, window_turns=2, stop_loss_turns=5)

    assert rescue.forced_min_tier(
        stage=Stage.REPAIR, gold_edited=True, current_tier=2,
        remaining_budget=100, total_budget=100,
    ) == 3
    assert rescue.forced_min_tier(
        stage=Stage.REPAIR, gold_edited=True, current_tier=2,
        remaining_budget=100, total_budget=100,
    ) == 3
    # Window exhausted, evidence turns = 2
    assert rescue.forced_min_tier(
        stage=Stage.REPAIR, gold_edited=True, current_tier=2,
        remaining_budget=100, total_budget=100,
    ) is None
    assert not rescue.should_stop_loss(gold_edited=True)  # stop_loss=5, evidence=3
    rescue.evidence_turns = 5
    assert rescue.should_stop_loss(gold_edited=True)  # now exceeds stop_loss

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.adaptive_routing import AdaptiveRoutingState


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
    assert state.pressure_boost > 0
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
    assert state.pressure_boost > 0
    for _ in range(5):
        state.record_task({"harness_resolved": True, "patch_extracted": True})
    assert state.pressure_boost == 0.0
    assert state.ttl_steps_remaining == 0


def test_on_step_ticks_ttl() -> None:
    state = AdaptiveRoutingState(strategy_name="budgetflow_full_tight")
    state.ttl_steps_remaining = 2
    state.on_step()
    assert state.ttl_steps_remaining == 1

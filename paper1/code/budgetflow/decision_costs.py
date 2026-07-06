"""Shared decision-cost helpers for BudgetFlow routing projections."""

from __future__ import annotations

from typing import Protocol


class DecisionCostModel(Protocol):
    cost_per_input_token: float
    cost_per_output_token: float
    mean_output_tokens: int

    def token_rates_for_input(self, input_tokens: int, turn_index: int | None = None) -> tuple[float, float]: ...


TASK_LEVEL_DECISION_INPUT_TOKENS = 2000
TASK_LEVEL_DECISION_TURN_INDEX = 2


def task_level_decision_per_turn_cost(model: DecisionCostModel) -> float:
    """Normalized per-turn cost used to choose a whole-task model tier.

    Runtime reservations still use the current prompt's token estimate. The
    task-start routing decision must use this stable catalog shape so compiler
    projections and runtime decisions cannot diverge on first-turn token noise.
    """
    input_rate, output_rate = model.token_rates_for_input(
        TASK_LEVEL_DECISION_INPUT_TOKENS,
        turn_index=TASK_LEVEL_DECISION_TURN_INDEX,
    )
    return (
        float(input_rate) * TASK_LEVEL_DECISION_INPUT_TOKENS
        + float(output_rate) * int(model.mean_output_tokens)
    )

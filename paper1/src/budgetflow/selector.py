from __future__ import annotations

from dataclasses import dataclass

from .defaults import PROGRESS_SCALE
from .types import Backend, ProgressTable, Stage, TurnInfo


@dataclass(frozen=True)
class RouterDecision:
    """Structured routing decision — why a tier was selected."""
    backend: Backend
    reason: str
    scores: dict[str, float]
    pressure: float
    branch: str  # "selector" | "budget_only" | "workflow_level" | "all_flash" | "all_pro" | "all_tier2" | "all_t3"


@dataclass(frozen=True)
class SelectionDecision:
    backend: Backend
    score: float
    upgraded: bool


class BudgetFlowSelector:
    def __init__(self, progress_table: ProgressTable) -> None:
        self.progress_table = progress_table

    def select_backend(
        self,
        turn_info: TurnInfo,
        backends: list[Backend],
        budget_pressure: float,
        expected_costs: dict[str, float],
    ) -> SelectionDecision:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        current = ordered[0]
        current_score = 0.0
        upgraded = False

        for next_backend in ordered[1:]:
            delta_progress = self._delta_progress(turn_info.stage, current.name, next_backend.name)
            delta_cost = expected_costs[next_backend.name] - expected_costs[current.name]
            if delta_cost <= 0:
                current = next_backend
                upgraded = True
                continue

            score = turn_info.w_i * (delta_progress * PROGRESS_SCALE / delta_cost)
            if score >= budget_pressure:
                current = next_backend
                current_score = score
                upgraded = True
                continue
            break

        return SelectionDecision(backend=current, score=current_score, upgraded=upgraded)

    def _delta_progress(self, stage: Stage, cheaper_backend: str, stronger_backend: str) -> float:
        stage_table = self.progress_table[stage]
        return stage_table[stronger_backend] - stage_table[cheaper_backend]


def build_zero_calibration_progress_table(backends: list[Backend]) -> ProgressTable:
    ordered = sorted(backends, key=lambda backend: backend.tier)
    # Mock-aligned success probabilities at representative token lengths
    # (localization ~97 tokens, repair ~135 tokens, validation ~109 tokens).
    mock_calibrated_progress = {
        Stage.LOCALIZATION: (0.2872, 0.5427, 0.7712, 0.8941),
        Stage.REPAIR: (0.0509, 0.1497, 0.4263, 0.7414),
        Stage.VALIDATION: (0.1026, 0.2586, 0.5292, 0.8014),
    }
    table: ProgressTable = {
        Stage.LOCALIZATION: {},
        Stage.REPAIR: {},
        Stage.VALIDATION: {},
    }
    for index, backend in enumerate(ordered):
        for stage in table:
            tier_index = min(index, len(mock_calibrated_progress[stage]) - 1)
            table[stage][backend.name] = mock_calibrated_progress[stage][tier_index]
    return table


def build_deepseek_progress_table(backends: list[Backend]) -> ProgressTable:
    """Conservative 2-tier table for Flash/Pro routing.

    Hand-set from stage importance priors, not tuned on eval tasks.
    """
    defaults = {
        Stage.LOCALIZATION: (0.32, 0.44),
        Stage.REPAIR: (0.08, 0.45),
        Stage.VALIDATION: (0.22, 0.42),
    }
    ordered = sorted(backends, key=lambda backend: backend.tier)
    table: ProgressTable = {stage: {} for stage in defaults}
    for index, backend in enumerate(ordered):
        gain_index = min(index, 1)
        for stage, values in defaults.items():
            table[stage][backend.name] = values[gain_index]
    return table

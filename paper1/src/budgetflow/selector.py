from __future__ import annotations

from dataclasses import dataclass

from .types import Backend, ProgressTable, Stage, TurnInfo


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

            score = turn_info.w_i * (delta_progress / delta_cost)
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
    stage_bases = {
        Stage.LOCALIZATION: 0.15,
        Stage.REPAIR: 0.12,
        Stage.VALIDATION: 0.14,
    }
    stage_gains = {
        Stage.LOCALIZATION: (0.0, 0.035, 0.055, 0.068),
        Stage.REPAIR: (0.0, 0.045, 0.095, 0.145),
        Stage.VALIDATION: (0.0, 0.04, 0.078, 0.115),
    }
    table: ProgressTable = {
        Stage.LOCALIZATION: {},
        Stage.REPAIR: {},
        Stage.VALIDATION: {},
    }
    for index, backend in enumerate(ordered):
        gain_index = min(index, len(stage_gains[Stage.LOCALIZATION]) - 1)
        for stage in table:
            table[stage][backend.name] = stage_bases[stage] + stage_gains[stage][gain_index]
    return table

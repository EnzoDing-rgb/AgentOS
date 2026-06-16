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

            # Pressure required to justify this upgrade: higher delta_progress or
            # lower delta_cost → lower threshold → easier to upgrade.
            # As budget depletes / no-progress streaks boost pressure, it crosses
            # the threshold and triggers escalation.
            if delta_progress > 0:
                upgrade_threshold = delta_cost / (delta_progress * PROGRESS_SCALE * turn_info.w_i)
            else:
                upgrade_threshold = float("inf")
            budget_slack = max(0.0, 1.0 - min(1.0, budget_pressure))
            if budget_slack >= upgrade_threshold:
                current = next_backend
                current_score = upgrade_threshold
                upgraded = True
                continue
            break

        return SelectionDecision(backend=current, score=current_score, upgraded=upgraded)

    def _delta_progress(self, stage: Stage, cheaper_backend: str, stronger_backend: str) -> float:
        stage_table = self.progress_table[stage]
        return stage_table[stronger_backend] - stage_table[cheaper_backend]


class ValueAwareSelector(BudgetFlowSelector):
    """BudgetFlow selector with task-value awareness.

    Scales stage w_i by a value_multiplier so that high-value tasks get
    easier T3 access (lower effective upgrade threshold) while low-value
    tasks get more conservative routing.

    Also applies budget conservation (same formula as ConservativeSelector).
    When all tasks have equal value (multiplier=1), behaviour is identical
    to ConservativeSelector.

    multiplier = clamp(task_value / median_task_value, 0.5, 2.0)
    """

    def __init__(self, progress_table: ProgressTable, median_task_value: float = 1.0) -> None:
        super().__init__(progress_table)
        self.median_task_value = median_task_value
        self._last_multiplier: float = 1.0

    @property
    def last_multiplier(self) -> float:
        return self._last_multiplier

    def select_backend(
        self,
        turn_info: TurnInfo,
        backends: list[Backend],
        budget_pressure: float,
        expected_costs: dict[str, float],
        task_value: float | None = None,
    ) -> SelectionDecision:
        tv = task_value if task_value is not None else self.median_task_value
        raw = tv / max(0.001, self.median_task_value)
        value_multiplier = max(0.5, min(2.0, raw))
        self._last_multiplier = value_multiplier

        effective_w_i = turn_info.w_i * value_multiplier

        from dataclasses import replace as _replace

        adjusted_turn = _replace(turn_info, w_i=effective_w_i)

        ordered = sorted(backends, key=lambda backend: backend.tier)
        current = ordered[0]
        current_score = 0.0
        upgraded = False

        for next_backend in ordered[1:]:
            delta_progress = self._delta_progress(adjusted_turn.stage, current.name, next_backend.name)
            delta_cost = expected_costs[next_backend.name] - expected_costs[current.name]
            if delta_cost <= 0:
                current = next_backend
                upgraded = True
                continue

            if delta_progress > 0:
                upgrade_threshold = delta_cost / (delta_progress * PROGRESS_SCALE * adjusted_turn.w_i)
            else:
                upgrade_threshold = float("inf")

            conservation = 1.0 + max(0.0, budget_pressure - 0.3) * 1.5
            effective_threshold = upgrade_threshold * conservation

            budget_slack = max(0.0, 1.0 - min(1.0, budget_pressure))
            if budget_slack >= effective_threshold:
                current = next_backend
                current_score = effective_threshold
                upgraded = True
                continue
            break

        return SelectionDecision(backend=current, score=current_score, upgraded=upgraded)


class ConservativeSelector(BudgetFlowSelector):
    """BudgetFlowSelector with budget-conservation pressure.

    Budget pressure is budget depletion, not progress urgency. As pressure
    rises, stronger-tier access must become harder unless an explicit
    progress/escalation path overrides this selector.
    """

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

            if delta_progress > 0:
                upgrade_threshold = delta_cost / (delta_progress * PROGRESS_SCALE * turn_info.w_i)
            else:
                upgrade_threshold = float("inf")

            # Conservation factor: as budget depletes, make escalation harder.
            # At pressure=0.3: factor=1.0 (no change). At pressure=1.0: factor≈2.05.
            # Slope 1.5 (was 3.0) — 053 per-task data showed 3.0 was too aggressive
            # for small per-task caps, preventing T3 entirely.
            conservation = 1.0 + max(0.0, budget_pressure - 0.3) * 1.5
            effective_threshold = upgrade_threshold * conservation

            budget_slack = max(0.0, 1.0 - min(1.0, budget_pressure))
            if budget_slack >= effective_threshold:
                current = next_backend
                current_score = effective_threshold
                upgraded = True
                continue
            break

        return SelectionDecision(backend=current, score=current_score, upgraded=upgraded)


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

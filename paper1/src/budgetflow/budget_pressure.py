from __future__ import annotations

from .defaults import BUDGET_PRESSURE_INIT, PRESSURE_MAX, UNCAPPED_BUDGET_THRESHOLD
from .governor import BudgetGovernor


def live_budget_pressure(
    governor: BudgetGovernor,
    *,
    init: float = BUDGET_PRESSURE_INIT,
    pressure_max: float = PRESSURE_MAX,
) -> float:
    snap = governor.budget_snapshot()
    total = snap["total_budget"]
    if total <= 0 or total >= UNCAPPED_BUDGET_THRESHOLD:
        return init
    used = (snap["spent_budget"] + snap["reserved_budget"]) / total
    used = min(1.0, max(0.0, used))
    return init + used * (pressure_max - init)

from __future__ import annotations

from dataclasses import dataclass

from ..adaptive_routing import AdaptiveRoutingState
from ..defaults import BUDGET_PRESSURE_INIT, PROGRESS_TABLE, W_I
from ..policies import BudgetOnlyStepRouter, WorkflowLevelRouter
from ..selector import BudgetFlowSelector
from ..types import Backend, ProgressTable, Stage, TurnInfo


@dataclass
class RoutingContext:
    strategy: str
    backends: list[Backend]
    selector: BudgetFlowSelector
    budget_pressure: float
    expected_costs: dict[str, float]
    pressure_max: float | None = None
    adaptive: AdaptiveRoutingState | None = None
    workflow_level_backend: Backend | None = None
    budget_only_router: BudgetOnlyStepRouter | None = None
    workflow_router: WorkflowLevelRouter | None = None


def build_progress_table_from_defaults(backends: list[Backend]) -> ProgressTable:
    ordered = sorted(backends, key=lambda backend: backend.tier)
    table: ProgressTable = {stage: {} for stage in PROGRESS_TABLE}
    for backend in ordered:
        for stage, values in PROGRESS_TABLE.items():
            table[stage][backend.name] = values[backend.name]
    return table


def build_routing_context(
    strategy: str,
    backends: list[Backend],
    budget_pressure: float | None = None,
    *,
    pressure_max: float | None = None,
    adaptive: AdaptiveRoutingState | None = None,
) -> RoutingContext:
    ordered = sorted(backends, key=lambda backend: backend.tier)
    pressure = BUDGET_PRESSURE_INIT if budget_pressure is None else budget_pressure
    selector = BudgetFlowSelector(build_progress_table_from_defaults(backends))
    ctx = RoutingContext(
        strategy=strategy,
        backends=ordered,
        selector=selector,
        budget_pressure=pressure,
        expected_costs={},
        pressure_max=pressure_max,
        adaptive=adaptive,
    )
    if strategy == "workflow_level":
        ctx.workflow_router = WorkflowLevelRouter()
        avg_w = sum(W_I.values()) / len(W_I)
        ctx.workflow_level_backend = ctx.workflow_router.choose_backend(avg_w, ordered, pressure)
    if strategy == "budget_only":
        ctx.budget_only_router = BudgetOnlyStepRouter()
    return ctx


def choose_backend(ctx: RoutingContext, turn: TurnInfo, expected_costs: dict[str, float]) -> Backend:
    ctx.expected_costs = expected_costs
    if ctx.strategy == "all_flash":
        return ctx.backends[0]
    if ctx.strategy == "all_tier2":
        return ctx.backends[1]
    if ctx.strategy == "all_pro":
        # Use T3 (qwen3.6-plus), not T4 (qwen3.7-max).
        # T4 is a budgetflow-only last resort. all_pro is the "standard best" baseline.
        return ctx.backends[2] if len(ctx.backends) >= 3 else ctx.backends[-1]
    if ctx.strategy == "workflow_level":
        assert ctx.workflow_level_backend is not None
        return ctx.workflow_level_backend
    if ctx.strategy == "budget_only":
        assert ctx.budget_only_router is not None
        return ctx.budget_only_router.choose_backend(turn, ctx.backends, ctx.budget_pressure)
    return ctx.selector.select_backend(
        turn_info=turn,
        backends=ctx.backends,
        budget_pressure=ctx.budget_pressure,
        expected_costs=expected_costs,
    ).backend


def stage_weight(stage: Stage) -> float:
    return W_I[stage]

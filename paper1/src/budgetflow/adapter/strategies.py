from __future__ import annotations

from dataclasses import dataclass

from ..adaptive_routing import AdaptiveRoutingState
from ..defaults import (
    BUDGET_PRESSURE_INIT,
    ModelCatalog,
    PROGRESS_TABLE,
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER3_BACKEND,
    TIER_ESCALATION_PATIENCE,
    W_I,
    active_w_i,
    active_w_i_profile_name,
)
from ..policies import BudgetOnlyStepRouter, WorkflowLevelRouter
from ..selector import BudgetFlowSelector, RouterDecision, SelectionDecision
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
    last_decision: RouterDecision | None = None
    last_backend: Backend | None = None


def build_progress_table_from_defaults(backends: list[Backend]) -> ProgressTable:
    ordered = sorted(backends, key=lambda backend: backend.tier)
    table: ProgressTable = {stage: {} for stage in PROGRESS_TABLE}
    canonical_by_tier = {1: TIER1_BACKEND, 2: TIER2_BACKEND, 3: TIER3_BACKEND}
    for backend in ordered:
        for stage, values in PROGRESS_TABLE.items():
            canonical_name = backend.name if backend.name in values else canonical_by_tier.get(backend.tier)
            if canonical_name is None:
                raise KeyError(f"no progress prior for backend={backend.name} tier={backend.tier}")
            table[stage][backend.name] = values[canonical_name]
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


def _backend_by_tier(backends: list[Backend], tier: int) -> Backend:
    return next((backend for backend in backends if backend.tier == tier), backends[-1])


def _budgetflow_max_tier(ctx: RoutingContext) -> int:
    """Maximum tier for budgetflow_full on this step.

    Default cap is T2.  T2→T3 escalation is gated by _apply_progress_escalation
    (per-tier patience), not by the selector.  If the previous step already
    used T3 (meaning escalation already fired), keep T3 to avoid ping-pong.
    When budget pressure is elevated (>= 0.15), lift the cap — the fixed
    selector formula (pressure >= upgrade_threshold) already prefers T2 at
    low pressure and only picks T3 when the cost/progress tradeoff justifies it.
    If adaptive routing recommends a higher starting tier, honour it.
    """
    max_tier: int = 2  # default cap: don't auto-upgrade to T3
    if ctx.last_backend is not None and ctx.last_backend.tier >= 3:
        max_tier = 3  # already escalated, keep T3
    # When budget pressure is moderate, let the selector decide.
    # upgrade_threshold for T2→T3 REPAIR ≈ 0.46, so at 0.15 the selector
    # still won't pick T3 — this just removes the artificial ceiling for
    # later steps when pressure genuinely crosses the threshold.
    if ctx.budget_pressure >= 0.15:
        max_tier = 3
    if ctx.adaptive is not None:
        start_tier = ctx.adaptive.starting_tier()
        if start_tier > max_tier:
            max_tier = start_tier
    return max_tier


def choose_backend(ctx: RoutingContext, turn: TurnInfo, expected_costs: dict[str, float]) -> Backend:
    ctx.expected_costs = expected_costs
    if ctx.strategy in {"budgetflow_equal_weight", "budgetflow_auto_v2"}:
        turn = TurnInfo(
            workflow_id=turn.workflow_id,
            step_index=turn.step_index,
            stage=turn.stage,
            w_i=1.0,
            context_len=turn.context_len,
            tool_name=turn.tool_name,
        )
    if ctx.strategy == "all_flash":
        backend = _backend_by_tier(ctx.backends, 1)
        ctx.last_decision = RouterDecision(
            backend=backend, reason="strategy_all_flash", scores={},
            pressure=ctx.budget_pressure, branch="all_flash",
        )
        return backend
    if ctx.strategy == "all_tier2":
        backend = _backend_by_tier(ctx.backends, 2)
        ctx.last_decision = RouterDecision(
            backend=backend, reason="strategy_all_tier2", scores={},
            pressure=ctx.budget_pressure, branch="all_tier2",
        )
        return backend
    if ctx.strategy in {"all_t3", "all_gpt53", "all_gpt54"}:
        backend = _backend_by_tier(ctx.backends, 3)
        ctx.last_decision = RouterDecision(
            backend=backend, reason="strategy_all_t3", scores={},
            pressure=ctx.budget_pressure, branch="all_t3",
        )
        return backend
    if ctx.strategy == "all_pro":
        backend = ModelCatalog.strongest(ctx.backends)
        ctx.last_decision = RouterDecision(
            backend=backend, reason="strategy_all_pro_strongest", scores={},
            pressure=ctx.budget_pressure, branch="all_pro",
        )
        return backend
    if ctx.strategy == "workflow_level":
        assert ctx.workflow_level_backend is not None
        ctx.last_decision = RouterDecision(
            backend=ctx.workflow_level_backend, reason="workflow_level_precomputed",
            scores={}, pressure=ctx.budget_pressure, branch="workflow_level",
        )
        return ctx.workflow_level_backend
    if ctx.strategy == "budget_only":
        assert ctx.budget_only_router is not None
        decision = ctx.budget_only_router.choose_backend(turn, ctx.backends, ctx.budget_pressure)
        ctx.last_decision = decision
        return decision.backend
    if ctx.strategy == "budgetflow_full":
        # BudgetFlow Full: use selector but cap at default max tier (T2).
        # T2→T3 escalation is gated by _apply_progress_escalation (per-tier
        # patience), not by the selector.
        max_tier = _budgetflow_max_tier(ctx)
        sel = ctx.selector.select_backend(
            turn_info=turn,
            backends=ctx.backends,
            budget_pressure=ctx.budget_pressure,
            expected_costs=expected_costs,
        )
        if sel.backend.tier > max_tier:
            capped = next(
                (b for b in reversed(ctx.backends) if b.tier <= max_tier),
                ctx.backends[0],
            )
            sel = SelectionDecision(backend=capped, score=sel.score, upgraded=False)
        ctx.last_decision = RouterDecision(
            backend=sel.backend,
            reason=f"bf_full_max_tier={max_tier}" if max_tier < 3 else "bf_full_escalated_t3",
            scores={sel.backend.name: sel.score},
            pressure=ctx.budget_pressure,
            branch="budgetflow_full",
        )
        return sel.backend
    sel = ctx.selector.select_backend(
        turn_info=turn,
        backends=ctx.backends,
        budget_pressure=ctx.budget_pressure,
        expected_costs=expected_costs,
    )
    ctx.last_decision = RouterDecision(
        backend=sel.backend, reason=f"selector_score={sel.score:.4f}",
        scores={sel.backend.name: sel.score}, pressure=ctx.budget_pressure,
        branch="selector",
    )
    return sel.backend


def stage_weight(stage: Stage) -> float:
    return active_w_i()[stage]


def current_w_i_profile() -> str:
    return active_w_i_profile_name()

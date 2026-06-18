from __future__ import annotations

from dataclasses import dataclass

from ..adaptive_routing import AdaptiveRoutingState
from ..allocation import AllocationContext
from ..defaults import (
    BUDGET_PRESSURE_INIT,
    ModelCatalog,
    W_I,
    active_w_i,
    active_w_i_profile_name,
    progress_table,
    tier_escalation_patience,
)
from ..frozen_router import FrozenRouterPlan
from ..policies import BudgetOnlyStepRouter, BudgetOnlyT2Router, WorkflowLevelRouter
from ..policy_backend import BootstrapPolicy, PolicyDecision
from ..selector import BudgetFlowSelector, ConservativeSelector, RouterDecision, ValueAwareSelector
from ..tier_frontier import TierFrontier, finite_frontier_score
from ..types import Backend, ProgressTable, Stage, TurnInfo

TASK_BUDGET_STRONGEST_FIT_FRACTION = 1.0
# Task-level T3 starts when each extra expected cost unit buys at least one
# median-task-value unit. Budget pressure is a scarcity multiplier, not an
# absolute veto.
MARGINAL_YIELD_PER_DOLLAR_THRESHOLD = 1.0
TASK_START_PRESSURE_THRESHOLD_MULTIPLIER = 0.5

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
    bootstrap_policy: BootstrapPolicy | None = None
    frozen_plan: FrozenRouterPlan | None = None
    tier_frontier: TierFrontier | None = None
    last_decision: RouterDecision | None = None
    last_policy_decision: PolicyDecision | None = None
    last_backend: Backend | None = None
    max_tier: int | None = None
    max_tier_before_frontier: int | None = None
    tier_frontier_score: float | None = None
    task_level_backend: Backend | None = None
    task_value: float = 1.0
    median_task_value: float = 1.0
    allocation: AllocationContext | None = None

    def __post_init__(self) -> None:
        if self.allocation is not None:
            self.task_value = self.allocation.task_value


def build_progress_table_from_defaults(backends: list[Backend]) -> ProgressTable:
    pt = progress_table()
    table: ProgressTable = {stage: {} for stage in pt}
    defaults_by_tier: dict[int, str] = {}
    for stage, values in pt.items():
        for default_backend in values:
            if default_backend.startswith("tier") and default_backend[4:].isdigit():
                defaults_by_tier[int(default_backend[4:])] = default_backend
    for backend in sorted(backends, key=lambda backend: backend.tier):
        for stage, values in pt.items():
            canonical_name = backend.name if backend.name in values else defaults_by_tier.get(backend.tier)
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
    task_value: float = 1.0,
    median_task_value: float = 1.0,
    frozen_plan: FrozenRouterPlan | None = None,
    allocation: AllocationContext | None = None,
) -> RoutingContext:
    ordered = sorted(backends, key=lambda backend: backend.tier)
    pressure = BUDGET_PRESSURE_INIT if budget_pressure is None else budget_pressure
    selector = BudgetFlowSelector(build_progress_table_from_defaults(backends))
    frontier = TierFrontier.from_catalog()

    ctx = RoutingContext(
        strategy=strategy,
        backends=ordered,
        selector=selector,
        budget_pressure=pressure,
        expected_costs={},
        pressure_max=pressure_max,
        adaptive=adaptive,
        task_value=task_value,
        median_task_value=median_task_value,
        frozen_plan=frozen_plan,
        tier_frontier=frontier,
        allocation=allocation,
    )
    if strategy == "workflow_level":
        ctx.workflow_router = WorkflowLevelRouter()
        avg_w = sum(W_I.values()) / len(W_I)
        ctx.workflow_level_backend = ctx.workflow_router.choose_backend(avg_w, ordered, pressure)
    if strategy == "budget_only":
        ctx.budget_only_router = BudgetOnlyStepRouter()
    if strategy == "budget_only_t2":
        ctx.budget_only_router = BudgetOnlyT2Router()
    if strategy == "budgetflow_segment":
        ctx.bootstrap_policy = BootstrapPolicy(ctx.selector, name=strategy)
    if strategy == "budgetflow_conservative":
        ctx.selector = ConservativeSelector(build_progress_table_from_defaults(backends))
        ctx.bootstrap_policy = BootstrapPolicy(ctx.selector, name=strategy)
    if strategy == "segment_value_aware":
        ctx.selector = ValueAwareSelector(build_progress_table_from_defaults(backends), median_task_value=median_task_value)
        ctx.bootstrap_policy = BootstrapPolicy(ctx.selector, name=strategy)
    # value_aware_task_level: task-boundary ValueAwareSelector. It chooses one
    # backend for the whole task; stage/segment signals stay out of this policy.
    if strategy == "value_aware_task_level":
        ctx.selector = ValueAwareSelector(build_progress_table_from_defaults(backends), median_task_value=median_task_value)
        ctx.bootstrap_policy = BootstrapPolicy(ctx.selector, name=strategy)
    return ctx


def _backend_by_tier(backends: list[Backend], tier: int) -> Backend:
    return next((backend for backend in backends if backend.tier == tier), backends[-1])


def _task_level_reference_backend(backends: list[Backend]) -> Backend:
    ordered = sorted(backends, key=lambda backend: backend.tier)
    return next((backend for backend in ordered if backend.tier == 2), ModelCatalog.second_cheapest(ordered))


def _budgetflow_max_tier(ctx: RoutingContext, stage: Stage) -> int:
    """Maximum tier cap for BudgetFlow policies on this step.

    Uses the current turn's stage-specific tier frontier score as advisory
    input.  The cap defaults to the strongest tier when the frontier score
    indicates a good T3 case (score < 2.0), otherwise stays at the second tier.
    Budget pressure is a scarcity signal: it can make frontier scores more
    conservative, but it must not by itself open the strongest tier. Stuck-task
    urgency is handled by explicit escalation/rescue paths in the runtime.
    """
    cheapest = ModelCatalog.cheapest(ctx.backends)
    strongest = ModelCatalog.strongest(ctx.backends)
    second = ModelCatalog.second_cheapest(ctx.backends)
    frontier = ctx.tier_frontier

    before_default = second.tier
    max_tier_before = max(cheapest.tier, min(before_default, strongest.tier))

    # Default cap uses frontier score — advisory, not binary
    default_cap = second.tier
    if frontier is not None:
        score = frontier.frontier_score(
            stage.value,
            allocation=ctx.allocation,
            budget_pressure=ctx.budget_pressure,
        )
        ctx.tier_frontier_score = score
        if score < 2.0:
            default_cap = strongest.tier
    else:
        # No frontier: conservative default to second tier
        ctx.tier_frontier_score = None
        default_cap = second.tier

    max_tier: int = max(cheapest.tier, min(default_cap, strongest.tier))
    ctx.max_tier_before_frontier = max_tier_before
    if ctx.last_backend is not None and ctx.last_backend.tier > max_tier:
        max_tier = ctx.last_backend.tier

    if ctx.adaptive is not None:
        start_tier = ctx.adaptive.starting_tier()
        if start_tier > max_tier:
            max_tier = start_tier
    ctx.max_tier = max_tier
    return max_tier


def _task_level_max_tier(ctx: RoutingContext) -> int:
    """Budget-safety tier cap for task-level selection.

    This is a budget-safety guardrail, NOT the primary value decision.
    Expected-total-cost dominance in ``_choose_task_level_backend`` can
    override this cap when a stronger tier is cheaper in total expected cost.
    """
    cheapest = ModelCatalog.cheapest(ctx.backends)
    strongest = ModelCatalog.strongest(ctx.backends)
    second = ModelCatalog.second_cheapest(ctx.backends)
    frontier = ctx.tier_frontier

    default_cap = second.tier
    ctx.max_tier_before_frontier = max(cheapest.tier, min(second.tier, strongest.tier))
    if frontier is None:
        ctx.tier_frontier_score = None
    else:
        reference = _backend_by_tier(ctx.backends, frontier.reference_tier)
        progress_delta = max(0.0, strongest.progress_score - reference.progress_score)
        fit_delta = None
        allocation = ctx.allocation
        if allocation is not None and allocation.has_trusted_model_fit:
            fit_delta = allocation.strongest_delta(
                reference_tier=frontier.reference_tier,
                strongest_tier=frontier.strongest_tier,
            )
        if fit_delta is not None and fit_delta > progress_delta:
            progress_delta = fit_delta
        task_value = float(getattr(allocation, "task_value", ctx.task_value) if allocation is not None else ctx.task_value)
        value_gain = progress_delta * max(0.001, task_value) * max(1, frontier.reference_runway_turns)
        incremental_cost_ratio = max(
            max(frontier.strongest_input_ratio, frontier.strongest_output_ratio) - 1.0,
            0.0,
        )
        cost_ratio = max(frontier.strongest_input_ratio, frontier.strongest_output_ratio)
        if value_gain <= 0:
            raw_score = cost_ratio * (1.0 + ctx.budget_pressure)
        else:
            raw_score = incremental_cost_ratio * (1.0 + ctx.budget_pressure * 0.5) / value_gain
        ctx.tier_frontier_score = finite_frontier_score(raw_score, cost_ratio, ctx.budget_pressure)
        if ctx.tier_frontier_score < 2.0:
            default_cap = strongest.tier
    ctx.max_tier = max(cheapest.tier, min(default_cap, strongest.tier))
    return ctx.max_tier


def _tier_model_fit_rate(ctx: RoutingContext, tier: int, backend_name: str) -> float:
    """Return per-tier ModelFit rate for task-level expected-cost calculation.

    Prefers calibrated per-tier Model Fit carried by AllocationContext.
    Falls back to the catalog progress_score for the backend. The runtime may
    carry the same workload-level fit map on every task; task identity is not
    part of this lookup.
    """
    allocation = ctx.allocation
    if allocation is not None and allocation.has_trusted_model_fit:
        key = f"tier{tier}"
        fit = allocation.model_fit.get(key) if allocation.model_fit else None
        if fit is not None and fit > 0:
            return float(fit)
    for backend in ctx.backends:
        if backend.name == backend_name:
            return max(backend.progress_score, 0.001)
    return 0.001


def _task_effort_units(ctx: RoutingContext) -> float:
    """Return the effort scale used by task-level expected-cost math."""
    allocation = ctx.allocation
    if allocation is not None and allocation.has_effort and allocation.task_effort is not None:
        return max(1.0, float(allocation.task_effort))
    if ctx.tier_frontier is not None:
        return max(1.0, float(ctx.tier_frontier.reference_runway_turns))
    return 1.0


def _expected_total_cost(
    ctx: RoutingContext,
    backend_name: str,
    tier: int,
    per_turn_cost: float,
) -> float:
    """Expected total cost = expected turns * per-turn cost.

    expected_turns = task_effort / model_fit_rate, where task_effort is the
    estimated runway needed and model_fit_rate is the tier's progress rate.

    When task_effort is unavailable, defaults to the tier frontier reference
    runway so the formula still produces a meaningful comparison.
    """
    fit = _tier_model_fit_rate(ctx, tier, backend_name)
    effort = _task_effort_units(ctx)
    expected_turns = effort / max(fit, 0.001)
    return expected_turns * per_turn_cost


def _expected_cost_fits_task_budget(
    allocation: AllocationContext | None,
    cost: float,
    *,
    fraction: float = TASK_BUDGET_STRONGEST_FIT_FRACTION,
) -> bool:
    if allocation is None or allocation.planned_task_budget is None:
        return True
    budget = max(0.0, float(allocation.planned_task_budget))
    if budget <= 0:
        return False
    return cost <= budget * max(0.0, min(1.0, fraction))


def _task_start_t3_score(
    ctx: RoutingContext,
    reference: Backend,
    strongest_total_cost: float,
    reference_total_cost: float,
    *,
    cost_estimate_available: bool,
) -> tuple[float, dict[str, float | str | bool]]:
    allocation = ctx.allocation
    has_trusted_fit = bool(allocation is not None and allocation.has_trusted_model_fit)
    task_value = float(getattr(allocation, "task_value", ctx.task_value) if allocation is not None else ctx.task_value)
    task_effort = (
        float(allocation.task_effort)
        if allocation is not None and allocation.has_effort and allocation.task_effort is not None
        else 0.0
    )
    median = max(0.001, float(ctx.median_task_value or 1.0))
    value_ratio = task_value / median
    pressure_penalty = max(0.0, min(1.5, float(ctx.budget_pressure or 0.0)))
    budget_allows = _expected_cost_fits_task_budget(
        allocation,
        strongest_total_cost,
        fraction=TASK_BUDGET_STRONGEST_FIT_FRACTION,
    )
    reference_fit = _tier_model_fit_rate(ctx, reference.tier, reference.name)
    strongest_fit = _tier_model_fit_rate(ctx, ModelCatalog.strongest(ctx.backends).tier, ModelCatalog.strongest(ctx.backends).name)
    fit_gain = max(0.0, strongest_fit - reference_fit)
    extra_expected_cost = max(0.0, strongest_total_cost - reference_total_cost)
    extra_cost_ratio = max(
        0.0,
        (strongest_total_cost - reference_total_cost) / max(reference_total_cost, 0.000001),
    )
    effort_units = _task_effort_units(ctx)
    reference_unit_cost = reference_total_cost / max(effort_units, 0.000001)
    strongest_unit_cost = strongest_total_cost / max(effort_units, 0.000001)
    extra_unit_cost = max(0.0, strongest_unit_cost - reference_unit_cost)
    if strongest_total_cost <= reference_total_cost:
        marginal_yield = float("inf") if fit_gain > 0 else 0.0
    else:
        marginal_yield = task_value * fit_gain / max(extra_expected_cost, 0.000001)
    threshold = (
        MARGINAL_YIELD_PER_DOLLAR_THRESHOLD
        * median
        * (1.0 + TASK_START_PRESSURE_THRESHOLD_MULTIPLIER * pressure_penalty)
    )
    score = marginal_yield - threshold
    expected_value_gain = task_value * fit_gain
    details: dict[str, float | str | bool] = {
        "task_value": task_value,
        "task_effort": task_effort,
        "value_ratio": value_ratio,
        "budget_pressure": float(ctx.budget_pressure or 0.0),
        "budget_allows_strongest": 1.0 if budget_allows else 0.0,
        "has_trusted_model_fit": 1.0 if has_trusted_fit else 0.0,
        "cost_estimate_available": 1.0 if cost_estimate_available else 0.0,
        "reference_fit": reference_fit,
        "strongest_fit": strongest_fit,
        "fit_gain": fit_gain,
        "reference_expected_total_cost": reference_total_cost,
        "strongest_expected_total_cost": strongest_total_cost,
        "extra_expected_cost": extra_expected_cost,
        "reference_unit_cost": reference_unit_cost,
        "strongest_unit_cost": strongest_unit_cost,
        "extra_unit_cost": extra_unit_cost,
        "expected_value_gain": expected_value_gain,
        "extra_cost_ratio": extra_cost_ratio,
        "marginal_yield_per_dollar": marginal_yield if marginal_yield != float("inf") else 999999.0,
        "budget_pressure_threshold": threshold,
        "planned_task_budget": (
            float(allocation.planned_task_budget)
            if allocation is not None and allocation.planned_task_budget is not None
            else 0.0
        ),
        "rule": "marginal_expected_value_per_dollar",
    }
    return (
        score
        if cost_estimate_available and budget_allows and has_trusted_fit and fit_gain > 0
        else -1.0
    ), details


def _choose_task_level_backend(ctx: RoutingContext, expected_costs: dict[str, float]) -> Backend:
    """Choose one backend for the whole task using expected total cost.

    Compares expected total cost (not per-step cost) across tiers so a
    cheaper-per-step tier that needs many more turns is correctly seen as
    more expensive in total.  Budget slack still gates stronger-tier access.
    """
    if ctx.task_level_backend is not None:
        backend = ctx.task_level_backend
        ctx.last_decision = RouterDecision(
            backend=backend,
            reason=f"bf_task_fixed_{backend.name}",
            scores={backend.name: ctx.tier_frontier_score or 0.0},
            pressure=ctx.budget_pressure,
            branch="value_aware_task_level",
        )
        return backend

    max_tier = _task_level_max_tier(ctx)
    # Current task-level policy chooses one model for the task from the active
    # reference frontier: T2 by default, or Strongest Model when marginal
    # value justifies it. T1 remains available to other policies and future
    # extensions, but it is not part of this mainline task-level decision.
    reference = _task_level_reference_backend(ctx.backends)
    ordered = [backend for backend in sorted(ctx.backends, key=lambda backend: backend.tier) if backend.tier >= reference.tier]
    if not ordered:
        ordered = sorted(ctx.backends, key=lambda backend: backend.tier)
    current = ordered[0]
    current_score = 0.0

    # Pre-compute expected total cost for each tier.
    total_costs: dict[str, float] = {}
    for backend in ordered:
        per_turn = expected_costs.get(backend.name, 0.0)
        total_costs[backend.name] = _expected_total_cost(ctx, backend.name, backend.tier, per_turn)

    strongest = ModelCatalog.strongest(ctx.backends)
    cost_estimate_available = (
        expected_costs.get(current.name, 0.0) > 0
        and expected_costs.get(strongest.name, 0.0) > 0
    )
    task_start_score, task_start_details = _task_start_t3_score(
        ctx,
        current,
        total_costs.get(strongest.name, 0.0),
        total_costs.get(current.name, 0.0),
        cost_estimate_available=cost_estimate_available,
    )
    if (
        task_start_score >= 0.0
        and float(task_start_details["marginal_yield_per_dollar"])
        >= float(task_start_details["budget_pressure_threshold"])
    ):
        current = strongest
        current_score = task_start_score
        ctx.task_level_backend = current
        ctx.last_decision = RouterDecision(
            backend=current,
            reason="bf_task_start_marginal_yield_t3",
            scores={current.name: current_score},
            pressure=ctx.budget_pressure,
            branch="value_aware_task_level",
        )
        if ctx.bootstrap_policy is not None:
            ctx.last_policy_decision = PolicyDecision(
                backend=current.name,
                reason="task_level_fixed_task_start",
                scores={k: float(v) if isinstance(v, (int, float)) else v for k, v in task_start_details.items()},
            )
        return current

    for next_backend in ordered[1:]:
        if not cost_estimate_available:
            # Cost dominance is only meaningful when both reference and
            # strongest costs were estimated for this turn. Missing estimates
            # must not make the strongest tier look free.
            break
        # Compare expected total cost, not per-step cost.
        delta_total_cost = total_costs.get(next_backend.name, 0.0) - total_costs.get(current.name, 0.0)

        if next_backend.tier > max_tier and delta_total_cost > 0:
            # Above max_tier cap AND costs more in total: budget-safety block.
            # When the stronger tier is cheaper in total (delta_total_cost <= 0),
            # expected-cost dominance overrides the cap — the cap is budget safety,
            # not the primary value decision.
            break

        if delta_total_cost <= 0:
            # Stronger tier is cheaper in total expected cost — dominate.
            current = next_backend
            current_score = 0.0
            continue
        # If the stronger tier costs more in expected total and failed the
        # task-start marginal Yield/$ check above, keep the current task-level
        # reference tier. Do not apply the old budget-slack upgrade heuristic.
        break

    ctx.task_level_backend = current
    strongest_tier = ModelCatalog.strongest(ctx.backends).tier
    ctx.last_decision = RouterDecision(
        backend=current,
        reason=(
            f"bf_task_fixed_max_tier={max_tier}"
            if max_tier < strongest_tier
            else "bf_task_fixed_strongest_allowed"
        ),
        scores={current.name: current_score},
        pressure=ctx.budget_pressure,
        branch="value_aware_task_level",
    )
    if ctx.bootstrap_policy is not None:
        scores: dict[str, float | str | bool] = {
            "selection_score": current_score,
            **task_start_details,
        }
        ctx.last_policy_decision = PolicyDecision(
            backend=current.name,
            reason="task_level_fixed",
            scores=scores,
        )
    return current


def choose_backend(ctx: RoutingContext, turn: TurnInfo, expected_costs: dict[str, float]) -> Backend:
    ctx.expected_costs = expected_costs
    if ctx.strategy in {"budgetflow_equal_weight"}:
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
    if ctx.strategy == "all_t3":
        backend = ModelCatalog.strongest(ctx.backends)
        ctx.last_decision = RouterDecision(
            backend=backend, reason="strategy_all_t3_strongest", scores={},
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
    if ctx.strategy in {"budget_only", "budget_only_t2"}:
        assert ctx.budget_only_router is not None
        decision = ctx.budget_only_router.choose_backend(turn, ctx.backends, ctx.budget_pressure)
        ctx.last_decision = decision
        return decision.backend
    if ctx.strategy == "value_aware_task_level":
        return _choose_task_level_backend(ctx, expected_costs)

    if ctx.strategy in {"budgetflow_segment", "budgetflow_conservative", "segment_value_aware"}:
        max_tier = _budgetflow_max_tier(ctx, turn.stage)
        policy = ctx.bootstrap_policy
        if policy is None:
            raise RuntimeError(f"strategy {ctx.strategy!r} requires a BootstrapPolicy")
        policy_kwargs: dict = dict(
            turn_info=turn,
            backends=ctx.backends,
            budget_pressure=ctx.budget_pressure,
            expected_costs=expected_costs,
            segment=turn.segment if ctx.strategy != "value_aware_task_level" else None,
        )
        if ctx.strategy in {"segment_value_aware", "value_aware_task_level"}:
            policy_kwargs["task_value"] = ctx.task_value
        policy_decision = policy.choose_backend(**policy_kwargs)
        ctx.last_policy_decision = policy_decision
        chosen = next(
            (b for b in ctx.backends if b.name == policy_decision.backend),
            ctx.backends[0],
        )
        sel_score = policy_decision.scores.get("selection_score", 0.0)

        if chosen.tier > max_tier:
            chosen = next(
                (b for b in reversed(ctx.backends) if b.tier <= max_tier),
                ctx.backends[0],
            )
        branch_map = {
            "budgetflow_conservative": "budgetflow_conservative",
            "segment_value_aware": "segment_value_aware",
            "budgetflow_segment": "budgetflow_segment",
            "value_aware_task_level": "value_aware_task_level",
        }
        reason_map = {
            "budgetflow_conservative": "bf_cons",
            "segment_value_aware": "bf_va",
            "budgetflow_segment": "bf_full",
            "value_aware_task_level": "bf_task",
        }
        branch = branch_map.get(ctx.strategy, "budgetflow_segment")
        reason_prefix = reason_map.get(ctx.strategy, "bf_full")
        ctx.last_decision = RouterDecision(
            backend=chosen,
            reason=f"{reason_prefix}_max_tier={max_tier}" if max_tier < ModelCatalog.strongest(ctx.backends).tier else f"{reason_prefix}_strongest_allowed",
            scores={chosen.name: sel_score},
            pressure=ctx.budget_pressure,
            branch=branch,
        )
        return chosen

    # ── Mechanism-first strategies ──────────────────────────────────────────
    if ctx.strategy == "bare_t3":
        backend = ModelCatalog.strongest(ctx.backends)
        ctx.last_decision = RouterDecision(
            backend=backend, reason="bare_t3_fixed",
            scores={}, pressure=ctx.budget_pressure, branch="bare_t3",
        )
        return backend

    if ctx.strategy == "enterprise_router":
        backend = _backend_from_frozen_plan(ctx, turn)
        ctx.last_decision = RouterDecision(
            backend=backend, reason="enterprise_router_frozen_plan",
            scores={}, pressure=ctx.budget_pressure, branch="enterprise_router",
        )
        return backend

    if ctx.strategy == "budgetflow_same_router":
        chosen = _backend_from_frozen_plan(ctx, turn)
        ctx.last_decision = RouterDecision(
            backend=chosen,
            reason="bf_same_router_frozen_plan",
            scores={chosen.name: 0.0},
            pressure=ctx.budget_pressure,
            branch="budgetflow_same_router",
        )
        return chosen

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


def _backend_from_frozen_plan(ctx: RoutingContext, turn: TurnInfo) -> Backend:
    if ctx.frozen_plan is None:
        raise ValueError(
            f"{ctx.strategy} requires a frozen router plan; workflow={turn.workflow_id}"
        )
    entry = ctx.frozen_plan.lookup(turn.workflow_id)
    if entry is None:
        raise ValueError(
            f"missing frozen plan entry for workflow={turn.workflow_id} "
            f"strategy={ctx.strategy}"
        )
    preferred = next(
        (b for b in ctx.backends if b.name == entry.preferred_model),
        None,
    )
    if preferred is None:
        raise ValueError(
            f"unknown preferred_model={entry.preferred_model!r} "
            f"for workflow={turn.workflow_id} strategy={ctx.strategy}"
        )
    return preferred


def stage_weight(stage: Stage) -> float:
    return active_w_i()[stage]


def current_w_i_profile() -> str:
    return active_w_i_profile_name()

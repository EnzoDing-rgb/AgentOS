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
        if allocation is not None and allocation.has_model_fit:
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
    if allocation is not None and allocation.has_model_fit:
        key = f"tier{tier}"
        fit = allocation.model_fit.get(key) if allocation.model_fit else None
        if fit is not None and fit > 0:
            return float(fit)
    for backend in ctx.backends:
        if backend.name == backend_name:
            return max(backend.progress_score, 0.001)
    return 0.001


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
    effort = 1.0
    allocation = ctx.allocation
    if allocation is not None and allocation.has_effort and allocation.task_effort is not None:
        effort = max(1.0, float(allocation.task_effort))
    elif ctx.tier_frontier is not None:
        effort = float(ctx.tier_frontier.reference_runway_turns)
    expected_turns = effort / max(fit, 0.001)
    return expected_turns * per_turn_cost


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
    median = max(0.001, float(ctx.median_task_value or 1.0))
    value_multiplier = max(0.5, min(2.0, float(ctx.task_value or median) / median))
    if hasattr(ctx.selector, "_last_multiplier"):
        ctx.selector._last_multiplier = value_multiplier
    ordered = sorted(ctx.backends, key=lambda backend: backend.tier)
    current = ordered[0]
    current_score = 0.0

    # Pre-compute expected total cost for each tier.
    total_costs: dict[str, float] = {}
    for backend in ordered:
        per_turn = expected_costs.get(backend.name, 0.0)
        total_costs[backend.name] = _expected_total_cost(ctx, backend.name, backend.tier, per_turn)

    for next_backend in ordered[1:]:
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

        current_fit = _tier_model_fit_rate(ctx, current.tier, current.name)
        next_fit = _tier_model_fit_rate(ctx, next_backend.tier, next_backend.name)
        fit_gain = max(0.0, next_fit - current_fit) * value_multiplier

        if fit_gain <= 0:
            # Fit is monotonic with tier: if this tier has no gain over current,
            # higher tiers won't either (catalog invariant).
            break
        upgrade_score = delta_total_cost / fit_gain
        budget_slack = max(0.0, 1.0 - min(1.0, ctx.budget_pressure))
        if budget_slack >= upgrade_score:
            current = next_backend
            current_score = upgrade_score
            continue
        # This tier doesn't justify its total-cost increment. A higher tier
        # might still dominate (higher fit gain may outweigh the cost jump).
        # Continue scanning — don't break here.

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
        ctx.last_policy_decision = PolicyDecision(
            backend=current.name,
            reason="task_level_fixed",
            scores={"selection_score": current_score},
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

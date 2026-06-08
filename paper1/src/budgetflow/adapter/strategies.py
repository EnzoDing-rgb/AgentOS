from __future__ import annotations

from dataclasses import dataclass

from ..adaptive_routing import AdaptiveRoutingState
from ..defaults import (
    BUDGET_PRESSURE_INIT,
    ModelCatalog,
    PROGRESS_TABLE,
    TIER_ESCALATION_PATIENCE,
    W_I,
    active_w_i,
    active_w_i_profile_name,
)
from ..policies import BudgetOnlyStepRouter, BudgetOnlyT2Router, WorkflowLevelRouter
from ..policy_backend import BootstrapPolicy, PolicyDecision
from ..selector import BudgetFlowSelector, ConservativeSelector, RouterDecision, ValueAwareSelector
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
    task_level_backend: Backend | None = None
    budget_only_router: BudgetOnlyStepRouter | None = None
    workflow_router: WorkflowLevelRouter | None = None
    bootstrap_policy: BootstrapPolicy | None = None
    last_decision: RouterDecision | None = None
    last_policy_decision: PolicyDecision | None = None
    last_backend: Backend | None = None
    task_value: float = 1.0
    median_task_value: float = 1.0


def build_progress_table_from_defaults(backends: list[Backend]) -> ProgressTable:
    table: ProgressTable = {stage: {} for stage in PROGRESS_TABLE}
    defaults_by_tier: dict[int, str] = {}
    for stage, values in PROGRESS_TABLE.items():
        for default_backend in values:
            # The default backend names are stable tier ids ("tier1", ...).
            if default_backend.startswith("tier") and default_backend[4:].isdigit():
                defaults_by_tier[int(default_backend[4:])] = default_backend
    for backend in sorted(backends, key=lambda backend: backend.tier):
        for stage, values in PROGRESS_TABLE.items():
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
        task_value=task_value,
        median_task_value=median_task_value,
    )
    if strategy == "workflow_level":
        ctx.workflow_router = WorkflowLevelRouter()
        avg_w = sum(W_I.values()) / len(W_I)
        ctx.workflow_level_backend = ctx.workflow_router.choose_backend(avg_w, ordered, pressure)
    if strategy == "budget_only":
        ctx.budget_only_router = BudgetOnlyStepRouter()
    if strategy == "budget_only_t2":
        ctx.budget_only_router = BudgetOnlyT2Router()
    if strategy == "budgetflow_full":
        ctx.bootstrap_policy = BootstrapPolicy(ctx.selector, name=strategy)
    if strategy == "budgetflow_conservative":
        ctx.selector = ConservativeSelector(build_progress_table_from_defaults(backends))
        ctx.bootstrap_policy = BootstrapPolicy(ctx.selector, name=strategy)
    if strategy == "budgetflow_value_aware":
        ctx.selector = ValueAwareSelector(build_progress_table_from_defaults(backends), median_task_value=median_task_value)
        ctx.bootstrap_policy = BootstrapPolicy(ctx.selector, name=strategy)
    if strategy == "value_aware_task_level":
        selector = ValueAwareSelector(build_progress_table_from_defaults(backends), median_task_value=median_task_value)
        avg_w = sum(active_w_i().values()) / len(active_w_i())
        task_turn = TurnInfo(
            workflow_id="task_level_init",
            step_index=0,
            stage=Stage.REPAIR,
            w_i=avg_w,
            context_len=0,
        )
        expected_costs = {
            backend.name: backend.mean_output_tokens * backend.cost_per_output_token
            for backend in ordered
        }
        selected = selector.select_backend(
            turn_info=task_turn,
            backends=ordered,
            budget_pressure=pressure,
            expected_costs=expected_costs,
            task_value=task_value,
        )
        ctx.selector = selector
        ctx.task_level_backend = selected.backend
    return ctx


def _backend_by_tier(backends: list[Backend], tier: int) -> Backend:
    return next((backend for backend in backends if backend.tier == tier), backends[-1])


def _budgetflow_max_tier(ctx: RoutingContext) -> int:
    """Maximum tier for budgetflow_full / budgetflow_conservative on this step.

    Default cap is the second available tier when present. Further escalation is
    gated by _apply_progress_escalation (per-tier patience), not by the selector.
    If the previous step already used a higher tier, keep it to avoid ping-pong.
    When budget pressure is elevated, lift the cap — the fixed selector formula
    (pressure >= upgrade_threshold) already prefers T2 at low pressure and only
    picks the strongest tier when the cost/progress tradeoff justifies it.
    If adaptive routing recommends a higher starting tier, honour it.

    Conservative variant uses a lower pressure threshold (0.05 vs 0.15) because
    the ConservativeSelector's conservation factor already makes T3 escalation
    progressively harder.  The hard cap would double-penalize T3 access.
    """
    cheapest = ModelCatalog.cheapest(ctx.backends)
    strongest = ModelCatalog.strongest(ctx.backends)
    default_cap = ModelCatalog.second_cheapest(ctx.backends).tier
    max_tier: int = max(cheapest.tier, min(default_cap, strongest.tier))
    if ctx.last_backend is not None and ctx.last_backend.tier > max_tier:
        max_tier = ctx.last_backend.tier
    # Conservative selector has its own restraint mechanism — let it access
    # the strongest tier earlier to avoid double-penalizing escalation decisions.
    strongest_threshold: float = 0.05 if ctx.strategy in ("budgetflow_conservative", "budgetflow_value_aware") else 0.15
    if ctx.budget_pressure >= strongest_threshold:
        max_tier = strongest.tier
    if ctx.adaptive is not None:
        start_tier = ctx.adaptive.starting_tier()
        if start_tier > max_tier:
            max_tier = start_tier
    return max_tier


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
    if ctx.strategy == "value_aware_task_level":
        assert ctx.task_level_backend is not None
        ctx.last_decision = RouterDecision(
            backend=ctx.task_level_backend,
            reason="value_aware_task_level_precomputed",
            scores={ctx.task_level_backend.name: 0.0},
            pressure=ctx.budget_pressure,
            branch="value_aware_task_level",
        )
        return ctx.task_level_backend
    if ctx.strategy in {"budget_only", "budget_only_t2"}:
        assert ctx.budget_only_router is not None
        decision = ctx.budget_only_router.choose_backend(turn, ctx.backends, ctx.budget_pressure)
        ctx.last_decision = decision
        return decision.backend
    if ctx.strategy in {"budgetflow_full", "budgetflow_conservative", "budgetflow_value_aware"}:
        max_tier = _budgetflow_max_tier(ctx)
        policy = ctx.bootstrap_policy
        if policy is None:
            raise RuntimeError(f"strategy {ctx.strategy!r} requires a BootstrapPolicy")
        policy_kwargs: dict = dict(
            turn_info=turn,
            backends=ctx.backends,
            budget_pressure=ctx.budget_pressure,
            expected_costs=expected_costs,
        )
        if ctx.strategy == "budgetflow_value_aware":
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
            "budgetflow_value_aware": "budgetflow_value_aware",
            "budgetflow_full": "budgetflow_full",
        }
        reason_map = {
            "budgetflow_conservative": "bf_cons",
            "budgetflow_value_aware": "bf_va",
            "budgetflow_full": "bf_full",
        }
        branch = branch_map.get(ctx.strategy, "budgetflow_full")
        reason_prefix = reason_map.get(ctx.strategy, "bf_full")
        ctx.last_decision = RouterDecision(
            backend=chosen,
            reason=f"{reason_prefix}_max_tier={max_tier}" if max_tier < ModelCatalog.strongest(ctx.backends).tier else f"{reason_prefix}_strongest_allowed",
            scores={chosen.name: sel_score},
            pressure=ctx.budget_pressure,
            branch=branch,
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


def stage_weight(stage: Stage) -> float:
    return active_w_i()[stage]


def current_w_i_profile() -> str:
    return active_w_i_profile_name()

"""Experiment setup helpers for compare runs."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from typing import Literal

from budgetflow.defaults import BUDGET_PRESSURE_INIT, PRESSURE_MAX
from budgetflow.experiments.compare_cli import PRESET_TASKS
from budgetflow.experiments.compare_config import (
    CompareStrategy,
    effective_policy_jobs,
    load_strategy_set,
    normalize_strategy,
    order_tasks_easy_first,
    paper_mainline_strategies,
    strategy_catalog,
)
from budgetflow.lite_tasks import load_compare_easy_tasks, load_compare_medium_tasks, load_swebench_lite_tasks

TraceConsole = Literal["quiet", "milestones", "verbose"]

DIAGNOSTIC_3X3_IDS = (
    "sympy__sympy-13480",
    "sympy__sympy-20212",
    "sympy__sympy-16988",
)
DIAGNOSTIC_3X3_STRATEGIES = (
    "bare_t3_baseline",
    "enterprise_router_baseline",
    "budgetflow_same_enterprise_router",
)

@dataclass(frozen=True)
class CompareBudgetPlan:
    constrained: float
    pressure_init: float
    pressure_max: float
    max_overrun: float
    source: str = "pre_registered_experiment_budget"


@dataclass(frozen=True)
class StrategySelection:
    strategies: tuple[CompareStrategy, ...]
    policy_jobs: int
    jobs_upgraded: bool


@dataclass(frozen=True)
class BatchBudgetModes:
    batch_caps: dict[str, float | None]
    budget_modes: dict[str, str]
    use_fixed_per_task_cap: bool
    use_dynamic_task_caps: bool
    planned_dynamic_cap: float | None
    effective_frozen_caps: dict[str, float] | None = None


def resolve_task_count(args: Namespace) -> int:
    tasks_n = args.limit if args.limit is not None else PRESET_TASKS[args.preset]
    if args.task_set == "medium":
        tasks_n = args.limit if args.limit is not None else 15
    return tasks_n


def _resolve_task_ids(args: Namespace) -> list[str] | None:
    """Return instance IDs from --ids or known presets, or None."""
    if args.ids:
        return [s.strip() for s in args.ids.split(",") if s.strip()]
    if args.preset == "3x3":
        return list(DIAGNOSTIC_3X3_IDS)
    return None


def resolve_budget_plan(
    args: Namespace, *, tasks_n: int,
    frozen_plan_path: str | None = None,
    task_ids: list[str] | None = None,
) -> CompareBudgetPlan:
    constrained = args.budget
    pressure_init = args.pressure_init
    pressure_max = args.pressure_max
    pressure_init = BUDGET_PRESSURE_INIT if pressure_init is None else pressure_init
    pressure_max = PRESSURE_MAX if pressure_max is None else pressure_max
    source = "cli" if constrained is not None else "pre_registered_experiment_budget"
    if args.budget_scale != 1.0:
        constrained = (constrained or 100.0) * args.budget_scale
    # Priority when --budget is not explicitly set:
    #   1. --budget-plan hard_cap_usd (code-generated from calibrate_budget)
    #   2. --frozen-plan selected cap sum (legacy, only when budget plan absent)
    if constrained is None:
        budget_plan_path = getattr(args, "budget_plan", None)
        if budget_plan_path:
            import json as _json
            from pathlib import Path
            bp = _json.loads(Path(budget_plan_path).read_text())
            bp_hard_cap = float(bp.get("hard_cap_usd", 0.0) or 0.0)
            if bp_hard_cap > 0:
                constrained = bp_hard_cap
                source = f"budget_plan:{bp.get('budget_mode', 'unknown')}"
        elif frozen_plan_path and task_ids:
            from budgetflow.frozen_router import load_frozen_plan
            plan = load_frozen_plan(frozen_plan_path)
            constrained = plan.selected_cap_sum(task_ids)
            source = "frozen_plan_cap_sum"
    return CompareBudgetPlan(
        constrained=100.0 if constrained is None else constrained,
        pressure_init=pressure_init,
        pressure_max=pressure_max,
        max_overrun=max(0.0, args.max_overrun),
        source=source,
    )


def trace_console_from_args(args: Namespace) -> TraceConsole:
    if args.trace_verbose:
        return "verbose"
    if args.trace_quiet:
        return "quiet"
    return "milestones"


def select_strategies(args: Namespace) -> StrategySelection:
    all_strategies = strategy_catalog()
    if args.strategies:
        wanted_raw = {s.strip() for s in args.strategies.split(",") if s.strip()}
    elif getattr(args, "strategy_set", None):
        strategies = load_strategy_set(args.strategy_set)
        policy_jobs = effective_policy_jobs(args.jobs, len(strategies))
        return StrategySelection(
            strategies=strategies,
            policy_jobs=policy_jobs,
            jobs_upgraded=bool(args.jobs is not None and len(strategies) > 1 and args.jobs < len(strategies)),
        )
    elif args.ids:
        strategies = paper_mainline_strategies()
        policy_jobs = effective_policy_jobs(args.jobs, len(strategies))
        return StrategySelection(
            strategies=strategies,
            policy_jobs=policy_jobs,
            jobs_upgraded=bool(args.jobs is not None and len(strategies) > 1 and args.jobs < len(strategies)),
        )
    elif args.preset == "3x3":
        wanted_raw = set(DIAGNOSTIC_3X3_STRATEGIES)
    else:
        strategies = paper_mainline_strategies()
        policy_jobs = effective_policy_jobs(args.jobs, len(strategies))
        return StrategySelection(
            strategies=strategies,
            policy_jobs=policy_jobs,
            jobs_upgraded=bool(args.jobs is not None and len(strategies) > 1 and args.jobs < len(strategies)),
        )
    if wanted_raw:
        wanted = {normalize_strategy(name) for name in wanted_raw}
        catalog_names = {s.name for s in all_strategies}
        missing = {name for name in wanted_raw if normalize_strategy(name) not in catalog_names}
        if missing:
            raise SystemExit(f"unknown strategies: {sorted(missing)}")
        strategies = tuple(s for s in all_strategies if s.name in wanted)
        if not strategies:
            raise SystemExit("no strategies selected")
    else:
        strategies = all_strategies
    policy_jobs = effective_policy_jobs(args.jobs, len(strategies))
    return StrategySelection(
        strategies=strategies,
        policy_jobs=policy_jobs,
        jobs_upgraded=bool(args.jobs is not None and len(strategies) > 1 and args.jobs < len(strategies)),
    )


def load_tasks_for_compare(args: Namespace, *, tasks_n: int) -> list:
    if args.ids:
        ids = tuple(s.strip() for s in args.ids.split(",") if s.strip())
        tasks = load_swebench_lite_tasks(instance_ids=ids)
    elif args.task_set == "medium":
        tasks = load_compare_medium_tasks(tasks_n)
    elif args.preset == "3x3":
        tasks = load_swebench_lite_tasks(instance_ids=DIAGNOSTIC_3X3_IDS)
    else:
        tasks = load_compare_easy_tasks(tasks_n)
    return order_tasks_easy_first(tasks, task_set=args.task_set)


def build_batch_budget_modes(
    *,
    strategies: tuple[CompareStrategy, ...],
    per_task_cap: float | None,
    auto_budget_task_caps: dict[str, float] | None,
    constrained_budget: float,
    frozen_task_caps: dict[str, float] | None = None,
    budget_mode: str | None = None,
) -> BatchBudgetModes:
    """Assign equal shared batch caps to all paper mainline strategies.

    Every strategy gets the same ``constrained_budget`` as a policy-local
    shared batch hard cap.  Per-task frozen caps and dynamic auto-budget caps
    are explicit diagnostic modes — they only activate when the user passes
    ``--per-task-cap`` or ``--auto-budget``.

    Frozen router plans provide ``preferred_model`` and ``effort`` priors
    (via ``effective_frozen_caps``), but do NOT change the budget cap for
    enterprise_router / budgetflow_same_enterprise_router strategies.
    """
    use_fixed_per_task_cap = per_task_cap is not None and per_task_cap > 0
    use_dynamic_task_caps = auto_budget_task_caps is not None
    planned_dynamic_cap = sum(auto_budget_task_caps.values()) if auto_budget_task_caps else None

    # Frozen plan priors (preferred_model, effort) are available to all
    # strategies, but do not change the shared cap.
    effective_frozen_caps: dict[str, float] | None = None
    if frozen_task_caps:
        effective_frozen_caps = dict(frozen_task_caps)

    def _cap_for(s: CompareStrategy) -> float | None:
        if not s.budgeted:
            return None
        if use_fixed_per_task_cap:
            return per_task_cap
        if use_dynamic_task_caps:
            return planned_dynamic_cap
        return constrained_budget

    def _mode_for(s: CompareStrategy) -> str:
        if not s.budgeted:
            return "unconstrained"
        if use_fixed_per_task_cap:
            return "per_task_cap"
        if use_dynamic_task_caps:
            return "dynamic_task_caps"
        return "shared_batch_hard_budget"

    batch_caps: dict[str, float | None] = {s.name: _cap_for(s) for s in strategies}
    budget_modes: dict[str, str] = {s.name: _mode_for(s) for s in strategies}
    return BatchBudgetModes(
        batch_caps=batch_caps,
        budget_modes=budget_modes,
        use_fixed_per_task_cap=use_fixed_per_task_cap,
        use_dynamic_task_caps=use_dynamic_task_caps,
        planned_dynamic_cap=planned_dynamic_cap,
        effective_frozen_caps=effective_frozen_caps,
    )

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
    normalize_strategy,
    order_tasks_easy_first,
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
    "budget_only_tight",
    "budgetflow_conservative_tight",
    "budgetflow_value_aware_tight",
)

SEGMENT_CONTROL_DIAGNOSTIC_STRATEGIES = (
    "budget_only_tight",
    "budgetflow_conservative_tight",
    "budgetflow_value_aware_tight",
    "value_aware_task_level_tight",
)


@dataclass(frozen=True)
class CompareBudgetPlan:
    loose: float
    tight: float
    pressure_init: float
    pressure_max: float
    max_overrun: float

    @property
    def budget_caps(self) -> dict[str, float]:
        return {"loose": self.loose, "tight": self.tight}


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


def resolve_task_count(args: Namespace) -> int:
    tasks_n = args.limit if args.limit is not None else PRESET_TASKS[args.preset]
    if args.task_set == "medium":
        tasks_n = args.limit if args.limit is not None else 15
    return tasks_n


def resolve_budget_plan(args: Namespace, *, tasks_n: int) -> CompareBudgetPlan:
    loose = args.loose
    tight = args.tight
    pressure_init = args.pressure_init
    pressure_max = args.pressure_max
    pressure_init = BUDGET_PRESSURE_INIT if pressure_init is None else pressure_init
    pressure_max = PRESSURE_MAX if pressure_max is None else pressure_max
    if args.tight_scale != 1.0:
        tight = (tight or 100.0) * args.tight_scale
    if args.loose_scale != 1.0:
        loose = (loose or 400.0) * args.loose_scale
    return CompareBudgetPlan(
        loose=400.0 if loose is None else loose,
        tight=100.0 if tight is None else tight,
        pressure_init=pressure_init,
        pressure_max=pressure_max,
        max_overrun=max(0.0, args.max_overrun),
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
    elif args.preset == "3x3":
        wanted_raw = set(DIAGNOSTIC_3X3_STRATEGIES)
    elif args.preset == "segment-control":
        wanted_raw = set(SEGMENT_CONTROL_DIAGNOSTIC_STRATEGIES)
    else:
        wanted_raw = set()
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
    elif args.preset in {"3x3", "segment-control"}:
        tasks = load_swebench_lite_tasks(instance_ids=DIAGNOSTIC_3X3_IDS)
    else:
        tasks = load_compare_easy_tasks(tasks_n)
    return order_tasks_easy_first(tasks, task_set=args.task_set)


def build_batch_budget_modes(
    *,
    strategies: tuple[CompareStrategy, ...],
    per_task_cap: float | None,
    auto_budget_task_caps: dict[str, float] | None,
    budget_caps: dict[str, float],
) -> BatchBudgetModes:
    use_fixed_per_task_cap = per_task_cap is not None and per_task_cap > 0
    use_dynamic_task_caps = auto_budget_task_caps is not None
    planned_dynamic_cap = sum(auto_budget_task_caps.values()) if auto_budget_task_caps else None
    batch_caps: dict[str, float | None] = {
        s.name: (
            per_task_cap
            if use_fixed_per_task_cap
            else planned_dynamic_cap
            if use_dynamic_task_caps and s.budget_tier is not None
            else None if s.budget_tier is None else budget_caps[s.budget_tier]
        )
        for s in strategies
    }
    budget_modes: dict[str, str] = {
        s.name: (
            "per_task_cap"
            if use_fixed_per_task_cap and s.budget_tier is not None
            else "dynamic_task_caps"
            if use_dynamic_task_caps and s.budget_tier is not None
            else "shared"
        )
        for s in strategies
    }
    return BatchBudgetModes(
        batch_caps=batch_caps,
        budget_modes=budget_modes,
        use_fixed_per_task_cap=use_fixed_per_task_cap,
        use_dynamic_task_caps=use_dynamic_task_caps,
        planned_dynamic_cap=planned_dynamic_cap,
    )

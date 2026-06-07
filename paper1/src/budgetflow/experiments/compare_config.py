"""Configuration helpers for mini-SWE policy comparison runs."""

from __future__ import annotations

from dataclasses import dataclass

from budgetflow.defaults import (
    MODEL_CATALOG,
    TIER1_BACKEND,
    TIER3_BACKEND,
    active_w_i_profile_name,
)

UNCAPPED_BUDGET = 1_000_000.0


def fmt_usd(value: float | None) -> str:
    """Adaptive USD formatting for real-dollar costs."""
    if value is None:
        return "uncapped"
    if value == 0:
        return "0"
    if value < 0.01:
        return f"{value:.6f}"
    if value < 1.0:
        return f"{value:.4f}"
    return f"{value:.2f}"


@dataclass(frozen=True)
class CompareStrategy:
    name: str
    routing: str
    budget_tier: str | None  # None = uncapped (all_pro)


DEFAULT_STRATEGIES: tuple[CompareStrategy, ...] = (
    CompareStrategy("all_t1_tight", "all_flash", "tight"),
    CompareStrategy("all_t1_loose", "all_flash", "loose"),
    CompareStrategy("budget_only_tight", "budget_only", "tight"),
    CompareStrategy("stage_blind_tight", "stage_blind", "tight"),
    CompareStrategy("budgetflow_full_tight", "budgetflow_full", "tight"),
    CompareStrategy("budgetflow_equal_weight_tight", "budgetflow_equal_weight", "tight"),
    CompareStrategy("budget_only_loose", "budget_only", "loose"),
    CompareStrategy("stage_blind_loose", "stage_blind", "loose"),
    CompareStrategy("budgetflow_full_loose", "budgetflow_full", "loose"),
    CompareStrategy("budgetflow_equal_weight_loose", "budgetflow_equal_weight", "loose"),
    CompareStrategy("all_pro", "all_pro", None),
    CompareStrategy("budget_only_t2_tight", "budget_only_t2", "tight"),
    CompareStrategy("budget_only_t2_loose", "budget_only_t2", "loose"),
    CompareStrategy("budgetflow_conservative_tight", "budgetflow_conservative", "tight"),
    CompareStrategy("budgetflow_conservative_loose", "budgetflow_conservative", "loose"),
    CompareStrategy("budgetflow_value_aware_tight", "budgetflow_value_aware", "tight"),
    CompareStrategy("budgetflow_value_aware_loose", "budgetflow_value_aware", "loose"),
    CompareStrategy("value_aware_task_level_tight", "value_aware_task_level", "tight"),
    CompareStrategy("value_aware_task_level_loose", "value_aware_task_level", "loose"),
)

DIAGNOSTIC_STRATEGIES: tuple[CompareStrategy, ...] = (
    CompareStrategy("all_t3", "all_t3", None),
    CompareStrategy("budget_tight_dummy", "all_flash", "tight"),
)


def normalize_strategy(name: str) -> str:
    """Validate strategy names without historical alias rewriting."""
    return name


def strategy_catalog() -> tuple[CompareStrategy, ...]:
    return DEFAULT_STRATEGIES + DIAGNOSTIC_STRATEGIES


def effective_policy_jobs(requested_jobs: int | None, strategy_count: int) -> int:
    """Policy comparisons run policy-parallel; tasks remain serial per policy."""
    if strategy_count < 1:
        raise ValueError("strategy_count must be positive")
    if requested_jobs is None:
        return strategy_count
    return max(1, requested_jobs, strategy_count)


def required_backends_for_strategies(strategies: tuple[CompareStrategy, ...]) -> list[str]:
    required: set[str] = set()
    tier2_backend = MODEL_CATALOG.tier(MODEL_CATALOG.backends(), 2).name
    for cfg in strategies:
        if cfg.routing == "all_flash":
            required.add(TIER1_BACKEND)
        elif cfg.routing in {"all_tier2"}:
            required.add(tier2_backend)
        elif cfg.routing in {"all_pro", "all_t3"}:
            required.add(TIER3_BACKEND)
        else:
            required.update({backend.name for backend in MODEL_CATALOG.backends()})
    return [backend.name for backend in MODEL_CATALOG.backends() if backend.name in required]


def w_i_profile_for_record(routing: str) -> str:
    """JSONL field: stage_blind forces w_i=1 at query time."""
    if routing == "stage_blind":
        return "flat_forced"
    if routing == "budgetflow_equal_weight":
        return "equal_weight"
    if routing == "value_aware_task_level":
        return "task_level_value_aware"
    return active_w_i_profile_name()


def batch_budget_cap(cfg: CompareStrategy, budget_caps: dict[str, float]) -> float:
    if cfg.budget_tier is None:
        return UNCAPPED_BUDGET
    return budget_caps[cfg.budget_tier]


def task_difficulty_key(task) -> tuple[int, int, int, str]:
    """Lower = easier (heuristic)."""
    return (
        len(task.patch.splitlines()),
        len(task.fail_to_pass),
        len(task.pass_to_pass),
        str(task.instance_id),
    )


def order_tasks_easy_first(tasks: list, *, task_set: str) -> list:
    if task_set != "medium":
        return list(tasks)
    return sorted(tasks, key=task_difficulty_key)


def task_descriptor(task) -> str:
    return (
        f"{task.instance_id}"
        f"(patch={len(task.patch.splitlines())},"
        f"f2p={len(task.fail_to_pass)},"
        f"p2p={len(task.pass_to_pass)})"
    )


def workspace_key(cfg: CompareStrategy, instance_id: str) -> str:
    safe = cfg.name.replace("/", "_")
    return f"{safe}_{instance_id}"

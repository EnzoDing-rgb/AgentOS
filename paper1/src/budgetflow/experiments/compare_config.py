"""Configuration helpers for mini-SWE policy comparison runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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
    budgeted: bool = True


PAPER1_ROOT = Path(__file__).resolve().parents[3]
PAPER_MAINLINE_STRATEGY_SET_PATH = PAPER1_ROOT / "docs" / "config" / "paper_mainline_strategies.v1.json"


# Registry of canonical strategy implementations.  Paper membership and order
# live in docs/config/paper_mainline_strategies.v1.json so launch, budget, and
# readiness code cannot drift into different policy sets.
CORE_STRATEGIES: tuple[CompareStrategy, ...] = (
    CompareStrategy("bare_t2_baseline", "all_tier2"),
    CompareStrategy("bare_t3_baseline", "bare_t3"),
    CompareStrategy("enterprise_router_baseline", "enterprise_router"),
    CompareStrategy("budgetflow_same_enterprise_router", "budgetflow_same_router"),
    CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
    CompareStrategy("budgetflow_segment", "segment_value_aware"),
)

DIAGNOSTIC_STRATEGIES: tuple[CompareStrategy, ...] = (
    CompareStrategy("budget_only_baseline", "budget_only"),
    CompareStrategy("all_strongest_model", "all_t3", budgeted=False),
    CompareStrategy("all_t1_baseline", "all_flash"),
    CompareStrategy("budget_only_t2_baseline", "budget_only_t2"),
    CompareStrategy("bootstrap_conservative_diagnostic", "budgetflow_conservative"),
    CompareStrategy("segment_blind_control", "stage_blind"),
    CompareStrategy("equal_weight_control", "budgetflow_equal_weight"),
)


def registered_strategy_catalog() -> tuple[CompareStrategy, ...]:
    return CORE_STRATEGIES + DIAGNOSTIC_STRATEGIES


def _strategy_registry() -> dict[str, CompareStrategy]:
    return {strategy.name: strategy for strategy in registered_strategy_catalog()}


def load_strategy_set(path: Path | str | None = None) -> tuple[CompareStrategy, ...]:
    """Load a versioned strategy set by canonical strategy name.

    The config file is membership only. Routing semantics stay in the code
    registry above, which keeps paper-run configuration orthogonal to mechanism
    implementation.
    """
    strategy_set_path = Path(path) if path is not None else PAPER_MAINLINE_STRATEGY_SET_PATH
    data = json.loads(strategy_set_path.read_text())
    names = [str(item.get("name", "")).strip() for item in data.get("strategies", [])]
    if not names:
        raise ValueError(f"strategy set {strategy_set_path} has no strategies")
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"strategy set {strategy_set_path} has duplicate strategies: {duplicates}")
    registry = _strategy_registry()
    missing = [name for name in names if name not in registry]
    if missing:
        raise ValueError(f"strategy set {strategy_set_path} references unknown strategies: {missing}")
    return tuple(registry[name] for name in names)


def paper_mainline_strategies() -> tuple[CompareStrategy, ...]:
    return load_strategy_set(PAPER_MAINLINE_STRATEGY_SET_PATH)


def paper_mainline_strategy_names() -> tuple[str, ...]:
    return tuple(strategy.name for strategy in paper_mainline_strategies())


# Default paid comparison: Claim 1 task-level BudgetFlow plus Claim 2 segment
# enhancement and the diagnostic mirrors, all under the same hard budget.
DEFAULT_STRATEGIES: tuple[CompareStrategy, ...] = paper_mainline_strategies()


# Backward-facing import name for tests/tools that ask for non-mainline
# diagnostics.  It intentionally excludes paper-mainline strategies.
CONTROL_STRATEGIES: tuple[CompareStrategy, ...] = DIAGNOSTIC_STRATEGIES


def normalize_strategy(name: str) -> str:
    """Validate strategy names without historical alias rewriting."""
    return name


def strategy_catalog() -> tuple[CompareStrategy, ...]:
    return registered_strategy_catalog()


def mechanism_strategy_names() -> frozenset[str]:
    return frozenset({s.name for s in DEFAULT_STRATEGIES})


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
        if cfg.routing in {"all_flash", "all_t1"}:
            required.add(TIER1_BACKEND)
        elif cfg.routing in {"all_tier2"}:
            required.add(tier2_backend)
        elif cfg.routing in {"all_pro", "all_t3", "bare_t3"}:
            required.add(TIER3_BACKEND)
        else:
            required.update({backend.name for backend in MODEL_CATALOG.backends()})
    return [backend.name for backend in MODEL_CATALOG.backends() if backend.name in required]


def w_i_profile_for_record(routing: str) -> str:
    """JSONL field: stage_blind forces w_i=1 at query time."""
    if routing in {"bare_t3", "enterprise_router", "budgetflow_same_router"}:
        return "mechanism_isolation"
    if routing == "stage_blind":
        return "flat_forced"
    if routing == "budgetflow_equal_weight":
        return "equal_weight"
    if routing == "value_aware_task_level":
        return "task_level_value_aware"
    return active_w_i_profile_name()


def batch_budget_cap(cfg: CompareStrategy, constrained_budget: float) -> float:
    if not cfg.budgeted:
        return UNCAPPED_BUDGET
    return constrained_budget


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


def task_set_kind(*, task_set: str, ids: str | None = None) -> str:
    if ids:
        return "custom"
    if task_set == "easy":
        return "familiar"
    if task_set == "medium":
        return "unseen"
    return "unknown"


def workspace_key(cfg: CompareStrategy, instance_id: str) -> str:
    safe = cfg.name.replace("/", "_")
    return f"{safe}_{instance_id}"

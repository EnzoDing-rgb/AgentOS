"""No-paid value sensitivity and observed-tier oracle for Claim 1 audits."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from budgetflow.metrics_reporting import build_standard_metrics


class Claim1Task(Protocol):
    strategy: str
    instance_id: str
    score_status: str
    task_value: float
    total_cost: float
    batch_budget_cap: float


@dataclass(frozen=True)
class ValueProfile:
    name: str
    values: dict[str, float]
    note: str


@dataclass(frozen=True)
class OracleAction:
    task_id: str
    tier: str
    cost: float
    value: float
    resolved: int


@dataclass(frozen=True)
class OracleResult:
    resolved: int
    spend: float
    total_resolved_value: float
    total_resolved_value_per_dollar: float
    t2_count: int
    t3_count: int
    skipped_count: int
    actions: tuple[OracleAction, ...]


def load_value_profiles(value_matrix_path: Path, task_order: list[str]) -> list[ValueProfile]:
    artifact = json.loads(value_matrix_path.read_text())
    tasks = artifact.get("tasks")
    if not isinstance(tasks, dict):
        raise ValueError(f"value matrix {value_matrix_path} missing tasks object")

    profiles: list[ValueProfile] = [
        ValueProfile(
            name="equal",
            values={task_id: 1.0 for task_id in task_order},
            note="Every task has value 1.0; this reduces Total Resolved Value to Resolved Count.",
        )
    ]

    criticality_values: dict[str, float] = {}
    criticality_levels: dict[str, str] = {}
    for task_id in task_order:
        task = tasks.get(task_id)
        if not isinstance(task, dict):
            raise ValueError(f"value matrix {value_matrix_path} missing task {task_id}")
        value_map = task.get("task_value")
        if isinstance(value_map, dict) and "criticality_value" in value_map:
            criticality_values[task_id] = float(value_map["criticality_value"])
        elif isinstance(task.get("values"), dict) and "criticality_value" in task["values"]:
            criticality_values[task_id] = float(task["values"]["criticality_value"])
        level = task.get("criticality_level")
        if isinstance(level, str):
            criticality_levels[task_id] = level

    if len(criticality_values) == len(task_order):
        profiles.append(
            ValueProfile(
                name="criticality_value",
                values=criticality_values,
                note="Frozen pre-registered Task Value profile.",
            )
        )

    if len(criticality_levels) == len(task_order):
        profiles.append(
            ValueProfile(
                name="compressed_criticality",
                values={
                    task_id: {"normal": 1.0, "high": 1.25, "critical": 1.5}.get(
                        criticality_levels[task_id], 1.0
                    )
                    for task_id in task_order
                },
                note="Smaller value spread; tests whether the result needs a large critical-task multiplier.",
            )
        )
        profiles.append(
            ValueProfile(
                name="expanded_criticality",
                values={
                    task_id: {"normal": 1.0, "high": 2.0, "critical": 5.0}.get(
                        criticality_levels[task_id], 1.0
                    )
                    for task_id in task_order
                },
                note="Larger value spread; tests whether protecting critical tasks changes the conclusion.",
            )
        )
    return profiles


def report_value_lookup(value_profiles: list[ValueProfile]) -> dict[str, float] | None:
    for profile in value_profiles:
        if profile.name == "criticality_value":
            return profile.values
    for profile in value_profiles:
        if profile.name == "equal":
            return profile.values
    return None


def value_sensitivity_lines(
    by_strategy: dict[str, list[Claim1Task]],
    value_profiles: list[ValueProfile],
    *,
    task_count: int,
) -> list[str]:
    lines = [
        "## Value Sensitivity",
        "",
        "Same resolved/not-resolved rows and same spend, rescored under alternate frozen Task Value profiles.",
        "",
        "| Value Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |",
        "|---|---|---:|---:|---:|---:|",
    ]
    profile_results: dict[str, dict[str, dict[str, float | int]]] = {}
    for profile in value_profiles:
        profile_results[profile.name] = {}
        for strategy, tasks in by_strategy.items():
            stats = recompute_strategy_metrics(tasks, profile.values, task_count=task_count)
            profile_results[profile.name][strategy] = stats
            lines.append(
                f"| {profile.name} | {strategy} | "
                f"{stats['resolved_count']}/{task_count} | "
                f"${stats['total_spend']:.2f} | "
                f"{stats['total_resolved_value']:.2f} | "
                f"{stats['total_resolved_value_per_dollar']:.2f} |"
            )

    lines.append("")
    lines.append("### BudgetFlow Margin Under Value Sensitivity")
    lines.append("")
    lines.append("| Value Profile | Best Control By Value | BudgetFlow Value Delta | Best Control By Value/$ | BudgetFlow Value/$ Delta |")
    lines.append("|---|---|---:|---|---:|")
    for profile in value_profiles:
        results = profile_results[profile.name]
        if "budgetflow_task_level" not in results:
            continue
        bf = results["budgetflow_task_level"]
        controls = {strategy: stats for strategy, stats in results.items() if strategy != "budgetflow_task_level"}
        if not controls:
            continue
        best_value_name, best_value = max(
            controls.items(),
            key=lambda item: (
                float(item[1]["total_resolved_value"]),
                float(item[1]["total_resolved_value_per_dollar"]),
            ),
        )
        best_eff_name, best_eff = max(
            controls.items(),
            key=lambda item: (
                float(item[1]["total_resolved_value_per_dollar"]),
                float(item[1]["total_resolved_value"]),
            ),
        )
        lines.append(
            f"| {profile.name} | {best_value_name} | "
            f"{float(bf['total_resolved_value']) - float(best_value['total_resolved_value']):+.2f} | "
            f"{best_eff_name} | "
            f"{float(bf['total_resolved_value_per_dollar']) - float(best_eff['total_resolved_value_per_dollar']):+.2f} |"
        )

    permutation = permutation_sensitivity_lines(by_strategy, value_profiles, task_count=task_count)
    if permutation:
        lines.append("")
        lines.extend(permutation)
    return lines


def recompute_strategy_metrics(
    tasks: list[Claim1Task],
    values: dict[str, float],
    *,
    task_count: int,
) -> dict[str, float | int]:
    resolved_count = sum(1 for task in tasks if task.score_status == "pass")
    spend = sum(task.total_cost for task in tasks)
    resolved_value = sum(
        values.get(task.instance_id, task.task_value)
        for task in tasks
        if task.score_status == "pass"
    )
    return build_standard_metrics(
        resolved_count=resolved_count,
        total_tasks=task_count,
        total_spend=spend,
        total_resolved_value=resolved_value,
    )


def permutation_sensitivity_lines(
    by_strategy: dict[str, list[Claim1Task]],
    value_profiles: list[ValueProfile],
    *,
    task_count: int,
    samples: int = 64,
) -> list[str]:
    main = next((profile for profile in value_profiles if profile.name == "criticality_value"), None)
    if main is None or "budgetflow_task_level" not in by_strategy:
        return []
    task_ids = sorted(main.values)
    value_bag = [main.values[task_id] for task_id in task_ids]
    margins: list[float] = []
    wins = 0
    for seed in range(samples):
        shuffled = stable_shuffle(value_bag, seed=seed)
        permuted_values = {task_id: shuffled[index] for index, task_id in enumerate(task_ids)}
        bf = recompute_strategy_metrics(
            by_strategy["budgetflow_task_level"],
            permuted_values,
            task_count=task_count,
        )
        control_values = [
            recompute_strategy_metrics(tasks, permuted_values, task_count=task_count)
            for strategy, tasks in by_strategy.items()
            if strategy != "budgetflow_task_level"
        ]
        if not control_values:
            continue
        best_control = max(float(stats["total_resolved_value"]) for stats in control_values)
        margin = float(bf["total_resolved_value"]) - best_control
        margins.append(margin)
        if margin > 0:
            wins += 1
    if not margins:
        return []
    margins_sorted = sorted(margins)

    def pct(q: float) -> float:
        index = min(len(margins_sorted) - 1, max(0, round((len(margins_sorted) - 1) * q)))
        return margins_sorted[index]

    return [
        "### Value Permutation Diagnostic",
        "",
        "This shuffles the same criticality-value multiset across the fixed task list. It is a diagnostic for value-placement dependence, not a replacement for the frozen main ValueSource.",
        "",
        "| Samples | BudgetFlow Wins | Min Margin | P25 | Median | P75 | Max Margin |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {len(margins)} | {wins}/{len(margins)} | {min(margins):+.2f} | {pct(0.25):+.2f} | {pct(0.50):+.2f} | {pct(0.75):+.2f} | {max(margins):+.2f} |",
    ]


def stable_shuffle(values: list[float], *, seed: int) -> list[float]:
    return [
        value
        for _, value in sorted(
            (
                hashlib.sha256(f"{seed}:{index}:{value}".encode()).hexdigest(),
                value,
            )
            for index, value in enumerate(values)
        )
    ]


def resolve_budget_cap(tasks: list[Claim1Task], budget_cap: float | None) -> float:
    if budget_cap is not None and budget_cap > 0:
        return budget_cap
    return max((task.batch_budget_cap for task in tasks), default=0.0)


def observed_tier_oracle_lines(
    task_order: list[str],
    by_key: dict[tuple[str, str], Claim1Task],
    value_profiles: list[ValueProfile],
    *,
    budget_cap: float,
) -> list[str]:
    if budget_cap <= 0.0:
        return [
            "## Static Observed-Tier Oracle",
            "",
            "- Skipped: no shared hard budget cap found in rows or budget plan.",
        ]
    if not all(
        ("bare_t2_baseline", task_id) in by_key and ("bare_t3_baseline", task_id) in by_key
        for task_id in task_order
    ):
        return [
            "## Static Observed-Tier Oracle",
            "",
            "- Skipped: complete pure T2 and pure T3 rows are required for all tasks.",
        ]

    lines = [
        "## Static Observed-Tier Oracle",
        "",
        "No-paid upper-bound replay: using the completed pure T2 and pure T3 rows, choose the best per-task tier/skip combination under the same shared hard budget. This is stronger than a deployable static router because it sees observed outcomes after the fact.",
        "",
        f"- Shared hard budget: ${budget_cap:.4f}.",
        "",
        "| Value Profile | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar | T2 | T3 | Skip |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in value_profiles:
        result = compute_observed_tier_oracle(
            task_order,
            by_key,
            profile.values,
            budget_cap=budget_cap,
        )
        lines.append(
            f"| {profile.name} | {result.resolved}/{len(task_order)} | "
            f"${result.spend:.2f} | "
            f"{result.total_resolved_value:.2f} | "
            f"{result.total_resolved_value_per_dollar:.2f} | "
            f"{result.t2_count} | {result.t3_count} | {result.skipped_count} |"
        )
    return lines


def compute_observed_tier_oracle(
    task_order: list[str],
    by_key: dict[tuple[str, str], Claim1Task],
    values: dict[str, float],
    *,
    budget_cap: float,
) -> OracleResult:
    scale = 10_000
    cap_units = int(round(budget_cap * scale))
    states: dict[int, tuple[float, int, tuple[OracleAction, ...]]] = {0: (0.0, 0, ())}
    for task_id in task_order:
        actions = oracle_actions_for_task(task_id, by_key, values)
        next_states = dict(states)
        for spend_units, state in states.items():
            state_value, state_resolved, state_actions = state
            for action in actions:
                action_units = int(round(action.cost * scale))
                candidate_units = spend_units + action_units
                if candidate_units > cap_units:
                    continue
                candidate = (
                    round(state_value + action.value, 6),
                    state_resolved + action.resolved,
                    state_actions + (action,),
                )
                previous = next_states.get(candidate_units)
                if previous is None or oracle_state_better(candidate, previous):
                    next_states[candidate_units] = candidate
        states = prune_oracle_states(next_states)

    best_units, best_state = max(
        states.items(),
        key=lambda item: (item[1][0], item[1][1], -item[0]),
    )
    total_value, resolved, actions = best_state
    spend = best_units / scale
    t2_count = sum(1 for action in actions if action.tier == "T2")
    t3_count = sum(1 for action in actions if action.tier == "T3")
    skipped_count = len(task_order) - len(actions)
    return OracleResult(
        resolved=resolved,
        spend=round(spend, 6),
        total_resolved_value=round(total_value, 6),
        total_resolved_value_per_dollar=round(total_value / spend, 6) if spend > 0 else 0.0,
        t2_count=t2_count,
        t3_count=t3_count,
        skipped_count=skipped_count,
        actions=actions,
    )


def oracle_actions_for_task(
    task_id: str,
    by_key: dict[tuple[str, str], Claim1Task],
    values: dict[str, float],
) -> list[OracleAction]:
    actions: list[OracleAction] = []
    for strategy, tier in (("bare_t2_baseline", "T2"), ("bare_t3_baseline", "T3")):
        task = by_key[(strategy, task_id)]
        if task.score_status != "pass" or task.total_cost <= 0.0:
            continue
        actions.append(
            OracleAction(
                task_id=task_id,
                tier=tier,
                cost=task.total_cost,
                value=values.get(task_id, task.task_value),
                resolved=1,
            )
        )
    return actions


def oracle_state_better(
    candidate: tuple[float, int, tuple[OracleAction, ...]],
    previous: tuple[float, int, tuple[OracleAction, ...]],
) -> bool:
    return (candidate[0], candidate[1]) > (previous[0], previous[1])


def prune_oracle_states(
    states: dict[int, tuple[float, int, tuple[OracleAction, ...]]]
) -> dict[int, tuple[float, int, tuple[OracleAction, ...]]]:
    pruned: dict[int, tuple[float, int, tuple[OracleAction, ...]]] = {}
    best_value = -1.0
    best_resolved = -1
    for spend_units in sorted(states):
        value, resolved, actions = states[spend_units]
        if value > best_value or (value == best_value and resolved > best_resolved):
            pruned[spend_units] = (value, resolved, actions)
            best_value = value
            best_resolved = resolved
    return pruned

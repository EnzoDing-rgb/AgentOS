"""No-paid Claim 1 evidence audit for completed compare JSONL runs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from budgetflow.experiments.claim1_value_sensitivity import (
    load_value_profiles,
    observed_tier_oracle_lines,
    report_value_lookup,
    resolve_budget_cap,
    value_sensitivity_lines,
)
from budgetflow.metrics_reporting import build_standard_metrics
from budgetflow.recost import recost_record


DEFAULT_STRATEGY_ORDER = (
    "bare_t2_baseline",
    "bare_t3_baseline",
    "routellm_learned_router_baseline",
    "budget_only_baseline",
    "budgetflow_task_level",
)

KV_PROFILES = (
    ("KV0", 0.0),
    ("KV50", 0.5),
    ("KV90", 0.9),
    ("KV98", 0.98),
    ("KV99", 0.99),
)

CAP_EPSILON = 1e-6


@dataclass(frozen=True)
class StrategyTask:
    strategy: str
    instance_id: str
    task_index: int
    score_status: str
    harness_resolved: bool
    harness_trust: str
    patch_extracted: bool
    task_value: float
    resolved_value: float
    total_cost: float
    batch_budget_cap: float
    llm_turns: int
    first_tier: int | None
    tier_mix: str
    exit_reason: str
    abort_reason: str
    true_fail_reason: str
    failure_class: str
    detail: str


@dataclass(frozen=True)
class ReplayResult:
    attempted: int
    spend: float
    resolved: int
    resolved_value: float
    next_index: int
    attempted_task_ids: tuple[str, ...]
    stop_reason: str


@dataclass(frozen=True)
class TailUpperBoundResult:
    added_tasks: int
    added_spend: float
    added_value: float
    total_spend: float
    total_value: float
    actions: tuple[str, ...]


def load_latest_rows(jsonl_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with jsonl_path.open() as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line_no"] = line_no
            rows.append(row)
    return _dedupe_latest_rows(rows)


def _dedupe_latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    paid_cost_by_key: dict[tuple[str, str], float] = defaultdict(float)
    paid_usage_by_key: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "backend_picks": [],
            "turn_traces": [],
            "prompt_tokens_total": 0,
            "completion_tokens_total": 0,
            "llm_turns": 0,
        }
    )
    for row in rows:
        key = (str(row.get("strategy") or ""), str(row.get("instance_id") or ""))
        if str(row.get("score_status") or "") in {"pass", "true_fail", "abort"}:
            try:
                cost = float(row.get("total_cost") or 0.0)
            except (TypeError, ValueError):
                cost = 0.0
            if cost > 0.0:
                paid_cost_by_key[key] += cost
                usage = paid_usage_by_key[key]
                usage["backend_picks"].extend(row.get("backend_picks") or [])
                usage["turn_traces"].extend(row.get("turn_traces") or [])
                usage["prompt_tokens_total"] += _int_field(row, "prompt_tokens_total")
                usage["completion_tokens_total"] += _int_field(row, "completion_tokens_total")
                usage["llm_turns"] += _int_field(row, "llm_turns")
        previous = latest.get(key)
        if previous is None or int(row.get("_line_no") or 0) > int(previous.get("_line_no") or 0):
            latest[key] = row
    deduped = []
    for key, row in latest.items():
        merged = dict(row)
        if key in paid_cost_by_key:
            merged["total_cost"] = paid_cost_by_key[key]
            usage = paid_usage_by_key[key]
            merged["_paid_backend_picks"] = list(usage["backend_picks"])
            merged["_paid_turn_traces"] = list(usage["turn_traces"])
            merged["_paid_prompt_tokens_total"] = usage["prompt_tokens_total"]
            merged["_paid_completion_tokens_total"] = usage["completion_tokens_total"]
            merged["_paid_llm_turns"] = usage["llm_turns"]
        deduped.append(merged)
    return deduped


def _int_field(row: dict[str, Any], field: str) -> int:
    try:
        return int(row.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def row_to_task(row: dict[str, Any]) -> StrategyTask:
    picks = [str(pick) for pick in (row.get("backend_picks") or []) if pick]
    first_tier = _parse_tier(picks[0]) if picks else None
    tier_counts: dict[int, int] = defaultdict(int)
    for pick in picks:
        tier = _parse_tier(pick)
        if tier is not None:
            tier_counts[tier] += 1
    tier_mix = ",".join(f"T{tier}:{count}" for tier, count in sorted(tier_counts.items())) or "-"
    return StrategyTask(
        strategy=str(row.get("strategy") or ""),
        instance_id=str(row.get("instance_id") or ""),
        task_index=int(row.get("task_index_in_batch") or 0),
        score_status=str(row.get("score_status") or ""),
        harness_resolved=row.get("harness_resolved") in (True, "True", "true"),
        harness_trust=str(row.get("harness_trust") or ""),
        patch_extracted=bool(row.get("patch_extracted")),
        task_value=float(row.get("task_value") or 0.0),
        resolved_value=float(row.get("resolved_value") or 0.0),
        total_cost=float(row.get("total_cost") or 0.0),
        batch_budget_cap=float(row.get("batch_budget_cap") or 0.0),
        llm_turns=int(row.get("llm_turns") or 0),
        first_tier=first_tier,
        tier_mix=tier_mix,
        exit_reason=str(row.get("exit_reason") or ""),
        abort_reason=str(row.get("abort_reason") or ""),
        true_fail_reason=str(row.get("true_fail_reason") or ""),
        failure_class=str(row.get("failure_class") or ""),
        detail=str(row.get("detail") or ""),
    )


def _parse_tier(text: str) -> int | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def build_report(
    rows: list[dict[str, Any]],
    *,
    title: str,
    task_order_override: list[str] | None = None,
    task_order_source: str | None = None,
    value_matrix_path: Path | None = None,
    budget_cap: float | None = None,
) -> str:
    tasks = [row_to_task(row) for row in rows]
    strategies = _strategy_order({task.strategy for task in tasks})
    if task_order_override:
        task_order = task_order_override
        order_source = task_order_source or "explicit_override"
    else:
        task_order, order_source = _task_order(tasks, strategies)
    by_key = {(task.strategy, task.instance_id): task for task in tasks}
    by_strategy: dict[str, list[StrategyTask]] = {
        strategy: [task for task in tasks if task.strategy == strategy]
        for strategy in strategies
    }
    raw_by_key = {
        (str(row.get("strategy") or ""), str(row.get("instance_id") or "")): row
        for row in rows
    }

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("This is a no-paid audit of completed JSONL rows. It does not re-score patches or edit historical artifacts.")
    lines.append("")
    lines.extend(_summary_table(by_strategy, task_count=len(task_order)))
    lines.append("")
    lines.extend(_execution_coverage(by_strategy, task_count=len(task_order)))
    lines.append("")
    value_profiles = load_value_profiles(value_matrix_path, task_order) if value_matrix_path else []
    value_lookup = report_value_lookup(value_profiles)
    if value_profiles:
        lines.extend(value_sensitivity_lines(by_strategy, value_profiles, task_count=len(task_order)))
        lines.append("")
        lines.extend(
            observed_tier_oracle_lines(
                task_order,
                by_key,
                value_profiles,
                budget_cap=resolve_budget_cap(tasks, budget_cap),
            )
        )
        lines.append("")
    lines.extend(_task_level_frontier_diagnostic(task_order, by_key, strategies, value_lookup=value_lookup))
    lines.append("")
    lines.extend(_runtime_costsource_audit(rows))
    lines.append("")
    lines.extend(_kv_cache_sensitivity(rows, value_lookup=value_lookup, task_count=len(task_order)))
    lines.append("")
    lines.extend(
        _dynamic_kv_replay(
            task_order,
            by_key,
            raw_by_key,
            strategies,
            budget_cap=resolve_budget_cap(tasks, budget_cap),
            value_lookup=value_lookup,
        )
    )
    lines.append("")
    lines.extend(
        _budget_cap_sensitivity(
            task_order,
            by_key,
            strategies,
            budget_cap=resolve_budget_cap(tasks, budget_cap),
            value_lookup=value_lookup,
        )
    )
    lines.append("")
    lines.extend(_scoring_evidence(by_strategy))
    lines.append("")
    lines.extend(_order_audit(task_order, by_key, strategies, order_source=order_source, value_lookup=value_lookup))
    lines.append("")
    lines.extend(_matrix(task_order, by_key, strategies, value_lookup=value_lookup))
    lines.append("")
    lines.extend(_routing_spin_diagnostics(task_order, by_key, strategies))
    lines.append("")
    lines.extend(_policy_diffs(task_order, by_key))
    lines.append("")
    return "\n".join(lines)


def _strategy_order(strategies: set[str]) -> list[str]:
    known = [strategy for strategy in DEFAULT_STRATEGY_ORDER if strategy in strategies]
    unknown = sorted(strategies - set(known))
    return known + unknown


def _task_order(tasks: list[StrategyTask], strategies: list[str]) -> tuple[list[str], str]:
    all_task_ids = {task.instance_id for task in tasks}
    by_strategy: dict[str, list[StrategyTask]] = defaultdict(list)
    for task in tasks:
        by_strategy[task.strategy].append(task)

    preferred = [
        "bare_t3_baseline",
        "bare_t2_baseline",
        "routellm_learned_router_baseline",
        "budget_only_baseline",
        "budgetflow_task_level",
    ]
    for strategy in preferred:
        strategy_tasks = by_strategy.get(strategy, [])
        if len({task.instance_id for task in strategy_tasks}) == len(all_task_ids):
            return _ordered_ids(strategy_tasks), strategy

    best_strategy = max(
        strategies,
        key=lambda strategy: len({task.instance_id for task in by_strategy.get(strategy, [])}),
    )
    return _ordered_ids(by_strategy.get(best_strategy, [])), best_strategy


def _ordered_ids(tasks: list[StrategyTask]) -> list[str]:
    return [
        task.instance_id
        for task in sorted(
            tasks,
            key=lambda task: (
                task.task_index if task.task_index > 0 else 10_000,
                task.instance_id,
            ),
        )
    ]


def _summary_table(by_strategy: dict[str, list[StrategyTask]], *, task_count: int) -> list[str]:
    lines = [
        "## Strategy Summary",
        "",
        "| Strategy | Lane State | Rows | Scoreable | Abort | Resolved | Rate (planned) | Rate (scoreable) | Spend | Cost / Resolved | Total Resolved Value | Total Resolved Value / Dollar |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy, tasks in by_strategy.items():
        resolved = sum(1 for task in tasks if task.score_status == "pass")
        aborts = sum(1 for task in tasks if task.score_status == "abort")
        scoreable = sum(1 for task in tasks if task.score_status in {"pass", "true_fail"})
        spend = sum(task.total_cost for task in tasks)
        value = sum(task.resolved_value for task in tasks)
        metrics = build_standard_metrics(
            resolved_count=resolved,
            total_tasks=task_count,
            total_spend=spend,
            total_resolved_value=value,
        )
        scoreable_rate = resolved / scoreable if scoreable > 0 else 0.0
        lines.append(
            f"| {strategy} | {_lane_state(tasks, task_count=task_count)} | "
            f"{len(tasks)}/{task_count} | "
            f"{scoreable}/{task_count} | "
            f"{aborts} | "
            f"{resolved}/{task_count} | "
            f"{metrics['resolved_rate'] * 100:.1f}% | "
            f"{scoreable_rate * 100:.1f}% | "
            f"${metrics['total_spend']:.2f} | "
            f"${metrics['cost_per_resolved_task']:.2f} | "
            f"{metrics['total_resolved_value']:.2f} | "
            f"{metrics['total_resolved_value_per_dollar']:.2f} |"
        )
    return lines


def _execution_coverage(by_strategy: dict[str, list[StrategyTask]], *, task_count: int) -> list[str]:
    lines = [
        "## Execution Coverage",
        "",
        "This separates planned tasks from tasks that actually consumed model budget. Zero-cost rows are usually budget-exhaustion placeholders, not failed model attempts.",
        "",
        "| Strategy | Planned | Rows Written | Paid Attempts | Zero-Cost Rows | Missing Rows | Paid Resolved | Total Resolved | Spend |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy, tasks in by_strategy.items():
        unique_rows = {task.instance_id for task in tasks}
        paid = [task for task in tasks if _is_paid_attempt(task)]
        zero_cost = [task for task in tasks if task.total_cost <= 1e-6]
        lines.append(
            f"| {strategy} | "
            f"{task_count} | "
            f"{len(unique_rows)} | "
            f"{len(paid)} | "
            f"{len(zero_cost)} | "
            f"{max(0, task_count - len(unique_rows))} | "
            f"{sum(1 for task in paid if task.score_status == 'pass')} | "
            f"{sum(1 for task in tasks if task.score_status == 'pass')} | "
            f"${sum(task.total_cost for task in tasks):.2f} |"
        )
    return lines


def _is_paid_attempt(task: StrategyTask) -> bool:
    return task.total_cost > 1e-6 and task.llm_turns > 0


def _task_level_frontier_diagnostic(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    strategies: list[str],
    *,
    value_lookup: dict[str, float] | None,
) -> list[str]:
    if "bare_t2_baseline" not in strategies or "bare_t3_baseline" not in strategies:
        return [
            "## Task-Level Frontier Diagnostic",
            "",
            "- Skipped: pure T2 and pure T3 rows are required.",
        ]

    buckets = {
        "T2 cheaper pass": [],
        "T3 cheaper pass": [],
        "T2-only pass": [],
        "T3-only pass": [],
        "both fail": [],
    }
    skipped = 0
    for task_id in task_order:
        t2 = by_key.get(("bare_t2_baseline", task_id))
        t3 = by_key.get(("bare_t3_baseline", task_id))
        if t2 is None or t3 is None or not _is_paid_attempt(t2) or not _is_paid_attempt(t3):
            skipped += 1
            continue
        t2_pass = t2.score_status == "pass"
        t3_pass = t3.score_status == "pass"
        if t2_pass and t3_pass:
            bucket = "T2 cheaper pass" if t2.total_cost <= t3.total_cost else "T3 cheaper pass"
        elif t2_pass:
            bucket = "T2-only pass"
        elif t3_pass:
            bucket = "T3-only pass"
        else:
            bucket = "both fail"
        buckets[bucket].append((task_id, t2, t3))

    comparable = sum(len(items) for items in buckets.values())
    lines = [
        "## Task-Level Frontier Diagnostic",
        "",
        "Pure T2 vs pure T3 counterfactuals on tasks where both tiers actually consumed model budget. This answers whether the batch contains a real T2-can-win frontier, rather than treating cheaper per-token pricing as enough.",
        "",
        f"- Comparable paid T2/T3 tasks: {comparable}/{len(task_order)}; skipped for missing or zero-cost tier row: {skipped}.",
        "",
        "| Frontier Bucket | Tasks | Total Value | Avg T2 Cost | Avg T3 Cost | Avg T2 Turns | Avg T3 Turns | Examples |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for bucket, items in buckets.items():
        values = [_display_task_value(task_id, by_key, strategies, value_lookup) for task_id, _, _ in items]
        t2_costs = [t2.total_cost for _, t2, _ in items]
        t3_costs = [t3.total_cost for _, _, t3 in items]
        t2_turns = [t2.llm_turns for _, t2, _ in items]
        t3_turns = [t3.llm_turns for _, _, t3 in items]
        examples = ", ".join(f"`{task_id}`" for task_id, _, _ in items[:4]) or "-"
        lines.append(
            f"| {bucket} | "
            f"{len(items)} | "
            f"{sum(values):.2f} | "
            f"${_mean(t2_costs):.2f} | "
            f"${_mean(t3_costs):.2f} | "
            f"{_mean(t2_turns):.1f} | "
            f"{_mean(t3_turns):.1f} | "
            f"{examples} |"
        )

    t2_win = len(buckets["T2 cheaper pass"]) + len(buckets["T2-only pass"])
    t3_win = len(buckets["T3 cheaper pass"]) + len(buckets["T3-only pass"])
    lines.append("")
    if comparable == 0:
        lines.append("- Interpretation: no comparable paid frontier rows; this run cannot diagnose T2 vs T3 task-level opportunity.")
    elif t2_win == 0:
        lines.append("- Interpretation: this run shows no paid task where pure T2 both resolves and beats the observed T3 alternative. BudgetFlow has little Claim 1 room to win by preferring T2 on this batch.")
    else:
        lines.append(
            f"- Interpretation: T2 has {t2_win} task-level opportunities and T3 has {t3_win}; "
            "BudgetFlow can win only if it captures the T2 opportunities without missing T3-only or T3-cheaper passes."
        )
    return lines


def _mean(values: list[float] | list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _kv_cache_sensitivity(
    rows: list[dict[str, Any]],
    *,
    value_lookup: dict[str, float] | None,
    task_count: int,
) -> list[str]:
    lines = [
        "## KV Cache Sensitivity",
        "",
        "No-paid CostSource sensitivity: outcomes stay fixed while repeated input-token cost is recomputed for T2/T3 turns. This does not simulate additional tasks becoming runnable under a cheaper runtime.",
        "",
        "| KV Profile | Strategy | Resolved | Spend | Total Resolved Value | Total Resolved Value / Dollar |",
        "|---|---|---:|---:|---:|---:|",
    ]
    profile_results: dict[str, dict[str, dict[str, float | int]]] = {}
    for profile_name, discount in KV_PROFILES:
        by_strategy: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"resolved": 0, "spend": 0.0, "value": 0.0}
        )
        for row in rows:
            strategy = str(row.get("strategy") or "")
            if not strategy:
                continue
            recosted_spend = _kv_recosted_cost(row, discount)
            stats = by_strategy[strategy]
            stats["spend"] = float(stats["spend"]) + recosted_spend
            if str(row.get("score_status") or "") == "pass":
                stats["resolved"] = int(stats["resolved"]) + 1
                stats["value"] = float(stats["value"]) + _row_task_value(row, value_lookup)
        profile_results[profile_name] = {}
        for strategy in _strategy_order(set(by_strategy)):
            stats = by_strategy[strategy]
            metrics = build_standard_metrics(
                resolved_count=int(stats["resolved"]),
                total_tasks=task_count,
                total_spend=float(stats["spend"]),
                total_resolved_value=float(stats["value"]),
            )
            profile_results[profile_name][strategy] = metrics
            lines.append(
                f"| {profile_name} | {strategy} | "
                f"{metrics['resolved_count']}/{task_count} | "
                f"${metrics['total_spend']:.2f} | "
                f"{metrics['total_resolved_value']:.2f} | "
                f"{metrics['total_resolved_value_per_dollar']:.2f} |"
            )
    lines.append("")
    lines.append("### BudgetFlow Margin Under KV Sensitivity")
    lines.append("")
    lines.append("| KV Profile | Best Control By Value/$ | BudgetFlow Value/$ Delta | BudgetFlow vs Pure T3 Value/$ Delta |")
    lines.append("|---|---|---:|---:|")
    for profile_name in profile_results:
        results = profile_results[profile_name]
        bf = results.get("budgetflow_task_level")
        if bf is None:
            continue
        controls = {
            strategy: stats
            for strategy, stats in results.items()
            if strategy != "budgetflow_task_level"
        }
        if not controls:
            continue
        best_name, best = max(
            controls.items(),
            key=lambda item: (
                float(item[1]["total_resolved_value_per_dollar"]),
                float(item[1]["total_resolved_value"]),
            ),
        )
        t3 = results.get("bare_t3_baseline")
        t3_delta = (
            float(bf["total_resolved_value_per_dollar"])
            - float(t3["total_resolved_value_per_dollar"])
            if t3 is not None
            else 0.0
        )
        lines.append(
            f"| {profile_name} | {best_name} | "
            f"{float(bf['total_resolved_value_per_dollar']) - float(best['total_resolved_value_per_dollar']):+.2f} | "
            f"{t3_delta:+.2f} |"
        )
    return lines


def _runtime_costsource_audit(rows: list[dict[str, Any]]) -> list[str]:
    catalog_counts: dict[str, int] = defaultdict(int)
    policy_counts: dict[tuple[float | str, int | str, float | str], int] = defaultdict(int)
    input_fraction_counts: dict[float | str, int] = defaultdict(int)
    turn_count = 0
    for row in rows:
        catalog_path = ""
        catalog = row.get("catalog")
        if isinstance(catalog, dict):
            catalog_path = str(catalog.get("catalog_path") or "")
        catalog_path = catalog_path or str(row.get("catalog_path") or "")
        if catalog_path:
            catalog_counts[catalog_path] += 1
        for trace in _paid_turn_traces(row):
            if not isinstance(trace, dict):
                continue
            turn_count += 1
            policy = trace.get("turn_cache_policy")
            if isinstance(policy, dict):
                key = (
                    _rounded_float_or_text(policy.get("input_kv_cache_discount")),
                    int(policy.get("input_discount_after_turn") or 0),
                    _rounded_float_or_text(policy.get("min_input_cost_fraction")),
                )
            else:
                key = ("missing", "missing", "missing")
            policy_counts[key] += 1
            input_fraction_counts[_rounded_float_or_text(trace.get("turn_cache_input_fraction"))] += 1

    lines = [
        "## Runtime CostSource Audit",
        "",
    ]
    if catalog_counts:
        lines.append(
            "- Runtime catalog paths: "
            + "; ".join(f"`{path}` ({count} rows)" for path, count in sorted(catalog_counts.items()))
            + "."
        )
    if turn_count == 0:
        lines.append("- No paid turn traces were available for runtime KV-cache inspection.")
        return lines
    policy_text = "; ".join(
        f"input_kv_cache_discount={key[0]}, after_turn={key[1]}, min_input_cost_fraction={key[2]} ({count} turns)"
        for key, count in sorted(policy_counts.items(), key=lambda item: (-item[1], str(item[0])))
    )
    fraction_text = "; ".join(
        f"{fraction} ({count} turns)"
        for fraction, count in sorted(input_fraction_counts.items(), key=lambda item: (-item[1], str(item[0])))
    )
    lines.append(f"- Runtime turn-cache policy observed on paid turns: {policy_text}.")
    lines.append(f"- Runtime charged input fractions observed on paid turns: {fraction_text}.")
    if len(policy_counts) == 1 and next(iter(policy_counts))[0] == 0.0:
        lines.append("- Interpretation: this run used runtime KV-cache discount 0.0; KV sensitivity below is no-paid recosting, not the executed runtime policy.")
    return lines


def _paid_turn_traces(row: dict[str, Any]) -> list[Any]:
    paid_traces = row.get("_paid_turn_traces")
    if isinstance(paid_traces, list) and paid_traces:
        return paid_traces
    traces = row.get("turn_traces")
    return traces if isinstance(traces, list) else []


def _rounded_float_or_text(value: Any) -> float | str:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return "missing"


def _row_for_kv_recost(row: dict[str, Any]) -> dict[str, Any]:
    recost_row = dict(row)
    paid_backend_picks = row.get("_paid_backend_picks")
    if isinstance(paid_backend_picks, list) and paid_backend_picks:
        recost_row["backend_picks"] = paid_backend_picks
        recost_row["turn_traces"] = row.get("_paid_turn_traces") or []
        recost_row["prompt_tokens_total"] = row.get("_paid_prompt_tokens_total") or 0
        recost_row["completion_tokens_total"] = row.get("_paid_completion_tokens_total") or 0
        recost_row["llm_turns"] = row.get("_paid_llm_turns") or len(paid_backend_picks)
    return recost_row


def _sensitivity_cost_or_original(recosted: dict[str, Any], original: dict[str, Any]) -> float:
    try:
        original_cost = float(original.get("total_cost") or 0.0)
    except (TypeError, ValueError):
        original_cost = 0.0
    try:
        recosted_cost = float(recosted.get("total_cost") or 0.0)
    except (TypeError, ValueError):
        recosted_cost = 0.0
    if original_cost > 0.0 and recosted_cost <= 0.0:
        return original_cost
    return recosted_cost


def _kv_recosted_cost(row: dict[str, Any], discount: float) -> float:
    if discount <= 0.0:
        try:
            return float(row.get("total_cost") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    recosted = recost_record(
        _row_for_kv_recost(row),
        t3_target_ratio=5.0,
        input_kv_cache_discount=discount,
        min_input_cost_fraction=max(0.0, 1.0 - discount),
    )
    return _sensitivity_cost_or_original(recosted, row)


def _dynamic_kv_replay(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    raw_by_key: dict[tuple[str, str], dict[str, Any]],
    strategies: list[str],
    *,
    budget_cap: float,
    value_lookup: dict[str, float] | None,
) -> list[str]:
    if budget_cap <= 0.0:
        return [
            "## Dynamic KV Replay",
            "",
            "- Skipped: no shared hard budget cap found in rows or budget plan.",
        ]

    lines = [
        "## Dynamic KV Replay",
        "",
        "No-paid sequential replay under cheaper KV profiles. The fixed-policy table replays each policy's observed task order and observed outcomes with recosted rows; it does not invent outcomes for tasks that never ran. The BudgetFlow tail upper-bound then asks how much extra value could be recovered if cheaper KV let the already-observed BudgetFlow lane reach later tasks and we fill those later tasks with pure T2/T3 observed counterfactuals.",
        "",
        f"- Shared hard budget: ${budget_cap:.4f}.",
        "",
        "### Fixed-Policy Replay",
        "",
        "| KV Profile | Strategy | Covered Rows | Spend | Resolved | Total Resolved Value | Stop Reason |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    replay_by_profile: dict[str, dict[str, ReplayResult]] = {}
    cost_cache = _kv_cost_cache(raw_by_key)
    for profile_name, discount in KV_PROFILES:
        replay_by_profile[profile_name] = {}
        for strategy in strategies:
            result = _replay_observed_strategy_with_costs(
                strategy,
                task_order,
                by_key,
                raw_by_key,
                cost_cache,
                discount=discount,
                cap=budget_cap,
                value_lookup=value_lookup,
            )
            replay_by_profile[profile_name][strategy] = result
            lines.append(
                f"| {profile_name} | {strategy} | "
                f"{result.attempted}/{len(task_order)} | "
                f"${result.spend:.2f} | "
                f"{result.resolved}/{len(task_order)} | "
                f"{result.resolved_value:.2f} | "
                f"{result.stop_reason} |"
            )

    if "budgetflow_task_level" in strategies:
        lines.append("")
        lines.append("### BudgetFlow Tail Upper-Bound")
        lines.append("")
        lines.append(
            "This is an optimistic diagnostic, not a deployable policy: after replaying BudgetFlow's observed rows under each KV profile, it spends any remaining budget on later tasks using observed pure T2/T3 pass outcomes and recosted costs."
        )
        lines.append("")
        lines.append("| KV Profile | BF Fixed Value | Added Tail Tasks | Added Tail Value | Added Tail Spend | Upper-Bound Value | Upper-Bound Spend | Tail Actions |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
        for profile_name, discount in KV_PROFILES:
            bf_result = replay_by_profile[profile_name].get("budgetflow_task_level")
            if bf_result is None:
                continue
            tail = _budgetflow_tail_upper_bound(
                bf_result,
                task_order,
                by_key,
                raw_by_key,
                cost_cache,
                discount=discount,
                cap=budget_cap,
                value_lookup=value_lookup,
            )
            actions = ", ".join(tail.actions[:5]) if tail.actions else "-"
            if len(tail.actions) > 5:
                actions += ", ..."
            lines.append(
                f"| {profile_name} | "
                f"{bf_result.resolved_value:.2f} | "
                f"{tail.added_tasks} | "
                f"{tail.added_value:.2f} | "
                f"${tail.added_spend:.2f} | "
                f"{tail.total_value:.2f} | "
                f"${tail.total_spend:.2f} | "
                f"{actions} |"
            )
    lines.append("")
    lines.extend(_claim1_runtime_recommendation(task_order, by_key, replay_by_profile, budget_cap=budget_cap))
    return lines


def _kv_cost_cache(raw_by_key: dict[tuple[str, str], dict[str, Any]]) -> dict[tuple[str, str, float], float]:
    cache: dict[tuple[str, str, float], float] = {}
    for (strategy, task_id), row in raw_by_key.items():
        for _, discount in KV_PROFILES:
            cache[(strategy, task_id, discount)] = _kv_recosted_cost(row, discount)
    return cache


def _replay_observed_strategy_with_costs(
    strategy: str,
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    raw_by_key: dict[tuple[str, str], dict[str, Any]],
    cost_cache: dict[tuple[str, str, float], float],
    *,
    discount: float,
    cap: float,
    value_lookup: dict[str, float] | None,
) -> ReplayResult:
    spend = 0.0
    resolved = 0
    resolved_value = 0.0
    attempted_ids: list[str] = []
    next_index = len(task_order)
    stop_reason = "completed_observed_order"
    for index, task_id in enumerate(task_order):
        task = by_key.get((strategy, task_id))
        raw = raw_by_key.get((strategy, task_id))
        if task is None or raw is None:
            next_index = index
            stop_reason = "missing_row"
            break
        if not _is_paid_attempt(task):
            next_index = index
            stop_reason = "zero_cost_placeholder"
            break
        row_cost = cost_cache.get((strategy, task_id, discount), task.total_cost)
        if row_cost > max(0.0, cap - spend) + CAP_EPSILON:
            next_index = index
            stop_reason = "budget_cap"
            break
        attempted_ids.append(task_id)
        spend += row_cost
        if task.score_status == "pass":
            resolved += 1
            resolved_value += _display_task_value(task_id, by_key, list(DEFAULT_STRATEGY_ORDER), value_lookup)
    return ReplayResult(
        attempted=len(attempted_ids),
        spend=round(spend, 6),
        resolved=resolved,
        resolved_value=round(resolved_value, 6),
        next_index=next_index,
        attempted_task_ids=tuple(attempted_ids),
        stop_reason=stop_reason,
    )


def _budgetflow_tail_upper_bound(
    bf_result: ReplayResult,
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    raw_by_key: dict[tuple[str, str], dict[str, Any]],
    cost_cache: dict[tuple[str, str, float], float],
    *,
    discount: float,
    cap: float,
    value_lookup: dict[str, float] | None,
) -> TailUpperBoundResult:
    remaining = max(0.0, cap - bf_result.spend)
    spend = 0.0
    value = 0.0
    actions: list[str] = []
    already_attempted = set(bf_result.attempted_task_ids)
    for task_id in task_order[bf_result.next_index:]:
        if task_id in already_attempted:
            continue
        options = _observed_passing_tier_options(task_id, by_key, raw_by_key, cost_cache, discount)
        if not options:
            continue
        tier, cost = min(options, key=lambda item: (item[1], item[0]))
        if cost > max(0.0, remaining - spend):
            continue
        spend += cost
        task_value = _display_task_value(task_id, by_key, list(DEFAULT_STRATEGY_ORDER), value_lookup)
        value += task_value
        actions.append(f"`{task_id}` {tier} ${cost:.2f}")
    return TailUpperBoundResult(
        added_tasks=len(actions),
        added_spend=round(spend, 6),
        added_value=round(value, 6),
        total_spend=round(bf_result.spend + spend, 6),
        total_value=round(bf_result.resolved_value + value, 6),
        actions=tuple(actions),
    )


def _observed_passing_tier_options(
    task_id: str,
    by_key: dict[tuple[str, str], StrategyTask],
    raw_by_key: dict[tuple[str, str], dict[str, Any]],
    cost_cache: dict[tuple[str, str, float], float],
    discount: float,
) -> list[tuple[str, float]]:
    options: list[tuple[str, float]] = []
    for strategy, tier in (("bare_t2_baseline", "T2"), ("bare_t3_baseline", "T3")):
        task = by_key.get((strategy, task_id))
        if task is None or task.score_status != "pass" or not _is_paid_attempt(task):
            continue
        if (strategy, task_id) not in raw_by_key:
            continue
        options.append((tier, cost_cache.get((strategy, task_id, discount), task.total_cost)))
    return options


def _claim1_runtime_recommendation(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    replay_by_profile: dict[str, dict[str, ReplayResult]],
    *,
    budget_cap: float,
) -> list[str]:
    lines = [
        "### Task-Boundary Runtime Implication",
        "",
    ]
    t3 = replay_by_profile.get("KV0", {}).get("bare_t3_baseline")
    bf = replay_by_profile.get("KV0", {}).get("budgetflow_task_level")
    comparable_t2_win = 0
    comparable_t3_win = 0
    for task_id in task_order:
        t2_task = by_key.get(("bare_t2_baseline", task_id))
        t3_task = by_key.get(("bare_t3_baseline", task_id))
        if t2_task is None or t3_task is None or not _is_paid_attempt(t2_task) or not _is_paid_attempt(t3_task):
            continue
        if t2_task.score_status == "pass" and (t3_task.score_status != "pass" or t2_task.total_cost <= t3_task.total_cost):
            comparable_t2_win += 1
        if t3_task.score_status == "pass" and (t2_task.score_status != "pass" or t3_task.total_cost < t2_task.total_cost):
            comparable_t3_win += 1
    if t3 is not None and t3.attempted == len(task_order) and t3.spend <= budget_cap and (bf is None or t3.resolved_value >= bf.resolved_value):
        lines.append(
            "- Current evidence supports a compiler-level strongest-frontier fallback: when projected pure T3 can cover the remaining batch inside the shared cap, BudgetFlow should be allowed to choose the T3 frontier instead of forcing T2 savings. In this run, pure T3 covered the full batch under the cap and beat BudgetFlow on Total Resolved Value."
        )
    elif comparable_t2_win > 0:
        lines.append(
            "- Current evidence still has a task-boundary allocation problem: T2 wins some tasks, so a pure-T3 fallback should be gated by projected full-batch coverage and not replace value-aware allocation under scarcity."
        )
    else:
        lines.append(
            "- Current evidence does not justify a lower-level stop or segment-routing change for Claim 1. First fix the compiler/frontier decision: use value-aware T2/T3 allocation only when pure T3 cannot cover the remaining batch under the shared cap."
        )
    lines.append(f"- Comparable paid frontier counts: T2-favorable {comparable_t2_win}, T3-favorable {comparable_t3_win}.")
    return lines


def _budget_cap_sensitivity(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    strategies: list[str],
    *,
    budget_cap: float,
    value_lookup: dict[str, float] | None,
) -> list[str]:
    if budget_cap <= 0.0:
        return [
            "## Budget Cap Sensitivity",
            "",
            "- Skipped: no shared hard budget cap found in rows or budget plan.",
        ]
    lines = [
        "## Budget Cap Sensitivity",
        "",
        "No-paid replay over the fixed task order: each strategy keeps completed rows until the replay cap is exhausted. Outcomes and Task Value stay fixed.",
        "",
        "| Cap | Strategy | Attempted | Spend | Total Resolved Value | Total Resolved Value / Dollar |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for cap in _cap_grid(budget_cap):
        for strategy in strategies:
            attempted, spend, resolved_value = _replay_strategy_at_cap(
                strategy,
                task_order,
                by_key,
                cap=cap,
                value_lookup=value_lookup,
            )
            value_per_dollar = resolved_value / spend if spend > 0.0 else 0.0
            lines.append(
                f"| ${cap:.2f} | {strategy} | "
                f"{attempted}/{len(task_order)} | "
                f"${spend:.2f} | "
                f"{resolved_value:.2f} | "
                f"{value_per_dollar:.2f} |"
            )
    return lines


def _cap_grid(budget_cap: float) -> list[float]:
    seen: set[float] = set()
    caps: list[float] = []
    for fraction in (0.30, 0.40, 0.50, 0.60, 0.75, 1.0):
        cap = round(float(budget_cap) * fraction, 2)
        if cap <= 0.0 or cap in seen:
            continue
        seen.add(cap)
        caps.append(cap)
    return caps


def _replay_strategy_at_cap(
    strategy: str,
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    *,
    cap: float,
    value_lookup: dict[str, float] | None,
) -> tuple[int, float, float]:
    attempted = 0
    spend = 0.0
    resolved_value = 0.0
    for task_id in task_order:
        task = by_key.get((strategy, task_id))
        if task is None:
            continue
        if task.total_cost > max(0.0, cap - spend):
            break
        attempted += 1
        spend += task.total_cost
        if task.score_status == "pass":
            resolved_value += (
                value_lookup.get(task_id, task.task_value)
                if value_lookup is not None
                else task.resolved_value
            )
    return attempted, round(spend, 6), round(resolved_value, 6)


def _row_task_value(row: dict[str, Any], value_lookup: dict[str, float] | None) -> float:
    task_id = str(row.get("instance_id") or "")
    if value_lookup is not None and task_id in value_lookup:
        return float(value_lookup[task_id])
    return float(row.get("task_value") or 0.0)


def _lane_state(tasks: list[StrategyTask], *, task_count: int) -> str:
    row_count = len(tasks)
    abort_count = sum(1 for task in tasks if task.score_status == "abort")
    spend = sum(task.total_cost for task in tasks)
    cap = max((task.batch_budget_cap for task in tasks), default=0.0)
    if row_count >= task_count:
        return "complete" if abort_count == 0 else "complete_with_aborts"
    if cap > 0.0 and spend >= cap * 0.999:
        return "budget_exhausted"
    return "partial_incomplete"


def _scoring_evidence(by_strategy: dict[str, list[StrategyTask]]) -> list[str]:
    lines = [
        "## Scoring Evidence",
        "",
        "| Strategy | Trusted Pass | Trusted True Fail | No-Patch True Fail | Abort | Suspect |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for strategy, tasks in by_strategy.items():
        buckets = defaultdict(int)
        for task in tasks:
            buckets[_evidence_bucket(task)] += 1
        lines.append(
            f"| {strategy} | "
            f"{buckets['trusted_pass']} | "
            f"{buckets['trusted_true_fail']} | "
            f"{buckets['no_patch_true_fail']} | "
            f"{buckets['abort']} | "
            f"{buckets['suspect']} |"
        )
    lines.append("")
    lines.append(
        "Suspect means the row should be inspected before paper use: a pass without trusted harness evidence, "
        "or a non-pass row carrying resolved-looking harness evidence."
    )
    return lines


def _evidence_bucket(task: StrategyTask) -> str:
    if task.score_status == "pass":
        if task.harness_resolved and task.harness_trust in {"trusted", ""}:
            return "trusted_pass"
        return "suspect"
    if task.score_status == "abort":
        return "abort"
    if _has_resolved_looking_evidence(task):
        return "suspect"
    if task.patch_extracted and task.harness_trust == "trusted":
        return "trusted_true_fail"
    if not task.patch_extracted:
        return "no_patch_true_fail"
    return "suspect"


def _has_resolved_looking_evidence(task: StrategyTask) -> bool:
    if task.harness_resolved:
        return True
    return "fail_after=pass" in task.detail and "pass_to_pass=pass" in task.detail


def _order_audit(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    strategies: list[str],
    *,
    order_source: str,
    value_lookup: dict[str, float] | None = None,
) -> list[str]:
    bf = "budgetflow_task_level"
    t3 = "bare_t3_baseline"
    value_by_task = {
        task_id: _display_task_value(task_id, by_key, strategies, value_lookup)
        for task_id in task_order
    }
    high_value = {task_id for task_id, value in value_by_task.items() if value >= 1.5}
    early = set(task_order[: max(1, len(task_order) // 3)])
    mid = set(task_order[max(1, len(task_order) // 3): max(2, 2 * len(task_order) // 3)])
    late = set(task_order[max(2, 2 * len(task_order) // 3):])

    def _resolved(strategy: str, task_ids: set[str]) -> tuple[int, float]:
        resolved = [
            by_key[(strategy, task_id)]
            for task_id in task_ids
            if (strategy, task_id) in by_key and by_key[(strategy, task_id)].score_status == "pass"
        ]
        return len(resolved), sum(
            _display_task_value(task.instance_id, by_key, strategies, value_lookup)
            for task in resolved
        )

    lines = [
        "## Task Order Audit",
        "",
        f"- Task count: {len(task_order)}.",
        f"- Task order source: `{order_source}`.",
        f"- High-value tasks (Task Value >= 1.5): {len(high_value)}; early={len(high_value & early)}, mid={len(high_value & mid)}, late={len(high_value & late)}.",
    ]
    if bf in strategies and t3 in strategies:
        bf_high_n, bf_high_v = _resolved(bf, high_value)
        t3_high_n, t3_high_v = _resolved(t3, high_value)
        lines.append(
            f"- On high-value tasks, BudgetFlow resolves {bf_high_n} tasks / value {bf_high_v:.2f}; "
            f"pure T3 resolves {t3_high_n} tasks / value {t3_high_v:.2f}."
        )
        for label, task_ids in (("early", early), ("middle", mid), ("late", late)):
            bf_n, bf_v = _resolved(bf, task_ids)
            t3_n, t3_v = _resolved(t3, task_ids)
            lines.append(
                f"- {label.title()} third: BudgetFlow {bf_n} resolved / value {bf_v:.2f}; "
                f"pure T3 {t3_n} resolved / value {t3_v:.2f}."
            )
    return lines


def _matrix(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    strategies: list[str],
    *,
    value_lookup: dict[str, float] | None = None,
) -> list[str]:
    lines = [
        "## Per-Task Matrix",
        "",
        "| # | Task | Value | " + " | ".join(_short_strategy(strategy) for strategy in strategies) + " |",
        "|---:|---|---:|" + "|".join("---:" for _ in strategies) + "|",
    ]
    for index, task_id in enumerate(task_order, 1):
        value = _display_task_value(task_id, by_key, strategies, value_lookup)
        cells = []
        for strategy in strategies:
            task = by_key.get((strategy, task_id))
            if task is None:
                cells.append("-")
                continue
            status = "P" if task.score_status == "pass" else "A" if task.score_status == "abort" else "F"
            tier = f"T{task.first_tier}" if task.first_tier is not None else "-"
            cells.append(f"{status} {task.total_cost:.2f} {tier}")
        lines.append(f"| {index} | `{task_id}` | {value:.2f} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("Cell format: `P/F/A cost first-tier`.")
    return lines


def _display_task_value(
    task_id: str,
    by_key: dict[tuple[str, str], StrategyTask],
    strategies: list[str],
    value_lookup: dict[str, float] | None,
) -> float:
    if value_lookup is not None and task_id in value_lookup:
        return value_lookup[task_id]
    return max(
        (by_key[(strategy, task_id)].task_value for strategy in strategies if (strategy, task_id) in by_key),
        default=0.0,
    )


def _policy_diffs(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
) -> list[str]:
    bf = "budgetflow_task_level"
    t3 = "bare_t3_baseline"
    lines = [
        "## BudgetFlow vs Pure T3 Diffs",
        "",
    ]
    if not any((bf, task_id) in by_key for task_id in task_order) or not any((t3, task_id) in by_key for task_id in task_order):
        lines.append("- Missing BudgetFlow or pure T3 rows; diff skipped.")
        return lines
    bf_only: list[StrategyTask] = []
    t3_only: list[StrategyTask] = []
    both: list[StrategyTask] = []
    neither = 0
    for task_id in task_order:
        bf_task = by_key.get((bf, task_id))
        t3_task = by_key.get((t3, task_id))
        if bf_task is None or t3_task is None:
            continue
        bf_pass = bf_task.score_status == "pass"
        t3_pass = t3_task.score_status == "pass"
        if bf_pass and not t3_pass:
            bf_only.append(bf_task)
        elif t3_pass and not bf_pass:
            t3_only.append(t3_task)
        elif bf_pass and t3_pass:
            both.append(bf_task)
        else:
            neither += 1
    lines.append(f"- Both pass: {len(both)} tasks.")
    lines.append(f"- BudgetFlow-only pass: {len(bf_only)} tasks, value {sum(t.resolved_value for t in bf_only):.2f}.")
    lines.append(f"- Pure-T3-only pass: {len(t3_only)} tasks, value {sum(t.resolved_value for t in t3_only):.2f}.")
    lines.append(f"- Neither pass: {neither} tasks.")
    if bf_only:
        lines.append("- BudgetFlow-only tasks: " + ", ".join(f"`{t.instance_id}`({t.resolved_value:.2f})" for t in bf_only))
    if t3_only:
        lines.append("- Pure-T3-only tasks: " + ", ".join(f"`{t.instance_id}`({t.resolved_value:.2f})" for t in t3_only))
    return lines


def _routing_spin_diagnostics(
    task_order: list[str],
    by_key: dict[tuple[str, str], StrategyTask],
    strategies: list[str],
) -> list[str]:
    lines = [
        "## Routing And Spin Diagnostics",
        "",
        "| Strategy | Rows | T3 Start | T3 Start Pass | T3 Start True Fail | T3 Start Abort | T3 Start Other | All-T2 Rows | All-T2 Turns | Extra All-T2 Turns vs Pure T3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy in strategies:
        rows = [by_key[(strategy, task_id)] for task_id in task_order if (strategy, task_id) in by_key]
        t3_start = [task for task in rows if task.first_tier == 3]
        all_t2 = [task for task in rows if _tier_counts(task) and set(_tier_counts(task)) == {2}]
        all_t2_turns = sum(task.llm_turns for task in all_t2)
        comparable_all_t2 = [
            task for task in all_t2 if ("bare_t3_baseline", task.instance_id) in by_key
        ]
        pure_t3_turns = 0
        for task in comparable_all_t2:
            pure_t3_turns += by_key[("bare_t3_baseline", task.instance_id)].llm_turns
        comparable_all_t2_turns = sum(task.llm_turns for task in comparable_all_t2)
        extra_turns = comparable_all_t2_turns - pure_t3_turns if comparable_all_t2 else 0
        lines.append(
            f"| {strategy} | {len(rows)} | "
            f"{len(t3_start)} | "
            f"{sum(1 for task in t3_start if task.score_status == 'pass')} | "
            f"{sum(1 for task in t3_start if task.score_status == 'true_fail')} | "
            f"{sum(1 for task in t3_start if task.score_status == 'abort')} | "
            f"{sum(1 for task in t3_start if task.score_status not in {'pass', 'true_fail', 'abort'})} | "
            f"{len(all_t2)} | "
            f"{all_t2_turns} | "
            f"{extra_turns:.1f} |"
        )

    bf = "budgetflow_task_level"
    if bf in strategies:
        bf_rows = [by_key[(bf, task_id)] for task_id in task_order if (bf, task_id) in by_key]
        bf_t3 = [task for task in bf_rows if task.first_tier == 3]
        bf_t2 = [task for task in bf_rows if _tier_counts(task) and set(_tier_counts(task)) == {2}]
        lines.append("")
        lines.append(
            f"- BudgetFlow T3-start rows: {len(bf_t3)}; "
            f"resolved {sum(1 for task in bf_t3 if task.score_status == 'pass')}; "
            f"true-fail {sum(1 for task in bf_t3 if task.score_status == 'true_fail')}; "
            f"abort {sum(1 for task in bf_t3 if task.score_status == 'abort')}."
        )
        comparable_t2 = [
            task for task in bf_t2 if ("bare_t3_baseline", task.instance_id) in by_key
        ]
        if comparable_t2:
            bf_turns = sum(task.llm_turns for task in comparable_t2)
            t3_turns = sum(
                by_key[("bare_t3_baseline", task.instance_id)].llm_turns
                for task in comparable_t2
            )
            lines.append(
                f"- BudgetFlow all-T2 rows on tasks with pure T3 rows: {len(comparable_t2)}; "
                f"turns {bf_turns} vs pure T3 {t3_turns}."
            )
    return lines


def _tier_counts(task: StrategyTask) -> dict[int, int]:
    counts: dict[int, int] = {}
    if not task.tier_mix or task.tier_mix == "-":
        return counts
    for part in task.tier_mix.split(","):
        if ":" not in part:
            continue
        tier_text, count_text = part.split(":", 1)
        tier = _parse_tier(tier_text)
        if tier is None:
            continue
        try:
            counts[tier] = int(count_text)
        except ValueError:
            continue
    return counts


def _short_strategy(strategy: str) -> str:
    return {
        "bare_t2_baseline": "T2",
        "bare_t3_baseline": "T3",
        "routellm_learned_router_baseline": "Route",
        "budget_only_baseline": "Budget-only",
        "budgetflow_task_level": "BF",
    }.get(strategy, strategy)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a no-paid Claim 1 matrix/order audit from compare JSONL")
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--budget-plan", type=Path, default=None, help="optional budget_plan.json; task_ids define the fixed task order")
    parser.add_argument(
        "--value-matrix",
        type=Path,
        default=None,
        help="optional frozen value matrix; enables value sensitivity and observed-tier oracle sections",
    )
    parser.add_argument(
        "--budget-cap",
        type=float,
        default=None,
        help="optional shared hard budget cap for observed-tier oracle; defaults to budget plan hard_cap_usd or row batch_budget_cap",
    )
    parser.add_argument("--title", default="Claim 1 Matrix And Task Order Audit")
    args = parser.parse_args(argv)

    rows = load_latest_rows(args.jsonl)
    task_order_override = None
    task_order_source = None
    budget_cap = args.budget_cap
    if args.budget_plan:
        budget_plan = json.loads(args.budget_plan.read_text())
        task_order_override = [str(task_id) for task_id in budget_plan.get("task_ids", [])]
        task_order_source = str(args.budget_plan)
        if budget_cap is None and budget_plan.get("hard_cap_usd") is not None:
            budget_cap = float(budget_plan["hard_cap_usd"])
    report = build_report(
        rows,
        title=args.title,
        task_order_override=task_order_override,
        task_order_source=task_order_source,
        value_matrix_path=args.value_matrix,
        budget_cap=budget_cap,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

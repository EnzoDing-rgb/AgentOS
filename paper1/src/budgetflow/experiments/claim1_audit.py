"""No-paid Claim 1 evidence audit for completed compare JSONL runs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from budgetflow.metrics_reporting import build_standard_metrics


DEFAULT_STRATEGY_ORDER = (
    "bare_t2_baseline",
    "bare_t3_baseline",
    "routellm_learned_router_baseline",
    "budget_only_baseline",
    "budgetflow_task_level",
)


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
    for row in rows:
        key = (str(row.get("strategy") or ""), str(row.get("instance_id") or ""))
        if str(row.get("score_status") or "") in {"pass", "true_fail", "abort"}:
            try:
                cost = float(row.get("total_cost") or 0.0)
            except (TypeError, ValueError):
                cost = 0.0
            if cost > 0.0:
                paid_cost_by_key[key] += cost
        previous = latest.get(key)
        if previous is None or int(row.get("_line_no") or 0) > int(previous.get("_line_no") or 0):
            latest[key] = row
    deduped = []
    for key, row in latest.items():
        merged = dict(row)
        if key in paid_cost_by_key:
            merged["total_cost"] = paid_cost_by_key[key]
        deduped.append(merged)
    return deduped


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

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("This is a no-paid audit of completed JSONL rows. It does not re-score patches or edit historical artifacts.")
    lines.append("")
    lines.extend(_summary_table(by_strategy, task_count=len(task_order)))
    lines.append("")
    lines.extend(_scoring_evidence(by_strategy))
    lines.append("")
    lines.extend(_order_audit(task_order, by_key, strategies, order_source=order_source))
    lines.append("")
    lines.extend(_matrix(task_order, by_key, strategies))
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
) -> list[str]:
    bf = "budgetflow_task_level"
    t3 = "bare_t3_baseline"
    value_by_task = {
        task_id: max(
            (by_key[(strategy, task_id)].task_value for strategy in strategies if (strategy, task_id) in by_key),
            default=0.0,
        )
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
        return len(resolved), sum(task.resolved_value for task in resolved)

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
) -> list[str]:
    lines = [
        "## Per-Task Matrix",
        "",
        "| # | Task | Value | " + " | ".join(_short_strategy(strategy) for strategy in strategies) + " |",
        "|---:|---|---:|" + "|".join("---:" for _ in strategies) + "|",
    ]
    for index, task_id in enumerate(task_order, 1):
        value = max(
            (by_key[(strategy, task_id)].task_value for strategy in strategies if (strategy, task_id) in by_key),
            default=0.0,
        )
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
    parser.add_argument("--title", default="Claim 1 Matrix And Task Order Audit")
    args = parser.parse_args(argv)

    rows = load_latest_rows(args.jsonl)
    task_order_override = None
    task_order_source = None
    if args.budget_plan:
        budget_plan = json.loads(args.budget_plan.read_text())
        task_order_override = [str(task_id) for task_id in budget_plan.get("task_ids", [])]
        task_order_source = str(args.budget_plan)
    report = build_report(
        rows,
        title=args.title,
        task_order_override=task_order_override,
        task_order_source=task_order_source,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

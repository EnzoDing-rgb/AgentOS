"""Build router-only frozen plans from pre-registered value matrices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STRONGEST_TRANCHE_FRACTION = 1.0 / 3.0
PREFERRED_MODEL_RULE = (
    "tier3 for the top one-third by 0.5*manual_value_percentile "
    "+ 0.5*bootstrap_effort_percentile; tier2 otherwise"
)


def _percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Return deterministic empirical percentile ranks in [0, 1]."""
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 1.0}

    sorted_items = sorted(values.items(), key=lambda item: (item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    denominator = float(len(sorted_items) - 1)
    while index < len(sorted_items):
        value = sorted_items[index][1]
        end = index
        while end + 1 < len(sorted_items) and sorted_items[end + 1][1] == value:
            end += 1
        avg_rank = (index + end) / 2.0
        percentile = avg_rank / denominator
        for item_index in range(index, end + 1):
            ranks[sorted_items[item_index][0]] = percentile
        index = end + 1
    return ranks


def build_router_only_plan(
    value_matrix: dict[str, Any],
    *,
    task_ids: list[str],
    name: str,
) -> dict[str, Any]:
    tasks = value_matrix.get("tasks")
    if not isinstance(tasks, dict) or not tasks:
        raise ValueError("value matrix must contain a non-empty tasks object")
    plan: dict[str, dict[str, int | str]] = {}
    missing: list[str] = []
    manual_values: dict[str, float] = {}
    effort_values: dict[str, float] = {}
    for task_id in task_ids:
        entry = tasks.get(task_id)
        if not isinstance(entry, dict):
            missing.append(task_id)
            continue
        task_value = entry.get("task_value") if isinstance(entry.get("task_value"), dict) else {}
        task_effort = entry.get("task_effort") if isinstance(entry.get("task_effort"), dict) else {}
        manual_value = float(task_value.get("manual_value", task_value.get("equal", 1.0)) or 1.0)
        bootstrap_effort = float(task_effort.get("bootstrap_heuristic", 0.0) or 0.0)
        manual_values[task_id] = manual_value
        effort_values[task_id] = bootstrap_effort
    if missing:
        preview = ", ".join(missing[:8])
        suffix = "" if len(missing) <= 8 else f", ... +{len(missing) - 8} more"
        raise ValueError(f"value matrix missing selected tasks: {preview}{suffix}")

    value_ranks = _percentile_ranks(manual_values)
    effort_ranks = _percentile_ranks(effort_values)
    router_scores = {
        task_id: 0.5 * value_ranks[task_id] + 0.5 * effort_ranks[task_id]
        for task_id in task_ids
    }
    strongest_slots = max(1, round(len(task_ids) * STRONGEST_TRANCHE_FRACTION))
    strongest_slots = min(strongest_slots, len(task_ids))
    ranked = sorted(
        task_ids,
        key=lambda task_id: (
            router_scores[task_id],
            manual_values[task_id],
            effort_values[task_id],
            task_id,
        ),
        reverse=True,
    )
    cutoff_score = router_scores[ranked[strongest_slots - 1]]

    for task_id in task_ids:
        preferred_model = "tier3" if router_scores[task_id] >= cutoff_score else "tier2"
        plan[task_id] = {
            "preferred_model": preferred_model,
            "priority": int(round(router_scores[task_id] * 100.0)),
        }
    return {
        "meta": {
            "name": name,
            "source_class": "router_only_pre_registered_value_effort_formula",
            "value_matrix": str(value_matrix.get("meta", {}).get("name") or "value_matrix"),
            "description": (
                "Router-only frozen plan. No caps, learning, runtime progress, "
                "or outcome feedback. Budget comes only from Budget Compiler budget_plan."
            ),
            "task_order": task_ids,
            "preferred_model_rule": PREFERRED_MODEL_RULE,
            "strongest_tranche_fraction": STRONGEST_TRANCHE_FRACTION,
            "note": "Retired cap fields are intentionally omitted.",
        },
        "plan": plan,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build router-only frozen plan from value matrix")
    parser.add_argument("--value-matrix", required=True)
    parser.add_argument("--task-ids", required=True, help="comma-separated selected task IDs")
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    task_ids = [part.strip() for part in args.task_ids.split(",") if part.strip()]
    if not task_ids:
        raise SystemExit("--task-ids did not contain any IDs")
    matrix_path = Path(args.value_matrix)
    matrix = json.loads(matrix_path.read_text())
    plan = build_router_only_plan(matrix, task_ids=task_ids, name=args.name)
    plan["meta"]["value_matrix"] = str(matrix_path)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}: entries={len(plan['plan'])} rule={PREFERRED_MODEL_RULE}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

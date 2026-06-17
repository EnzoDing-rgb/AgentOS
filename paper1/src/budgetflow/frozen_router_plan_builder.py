"""Build router-only frozen plans from pre-registered value matrices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PREFERRED_MODEL_RULE = "tier3 if manual_value>=0.95 or bootstrap_effort>=300 else tier2"


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
    for task_id in task_ids:
        entry = tasks.get(task_id)
        if not isinstance(entry, dict):
            missing.append(task_id)
            continue
        task_value = entry.get("task_value") if isinstance(entry.get("task_value"), dict) else {}
        task_effort = entry.get("task_effort") if isinstance(entry.get("task_effort"), dict) else {}
        manual_value = float(task_value.get("manual_value", task_value.get("equal", 1.0)) or 1.0)
        bootstrap_effort = float(task_effort.get("bootstrap_heuristic", 0.0) or 0.0)
        preferred_model = "tier3" if manual_value >= 0.95 or bootstrap_effort >= 300.0 else "tier2"
        plan[task_id] = {
            "preferred_model": preferred_model,
            "priority": int(round(manual_value * 100.0)),
        }
    if missing:
        preview = ", ".join(missing[:8])
        suffix = "" if len(missing) <= 8 else f", ... +{len(missing) - 8} more"
        raise ValueError(f"value matrix missing selected tasks: {preview}{suffix}")
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

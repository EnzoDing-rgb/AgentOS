"""Build value-blind RouteLLM-inspired frozen router plans.

The builder is offline-only. It may use pre-execution task features,
Estimated Task Token Demand, and frozen historical T2/T3 outcomes. It must not
read Task Value or budget fields. Runtime consumes the output through the
standard FrozenRouterPlan path.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from budgetflow.adapters.swebench_task import SwebenchTaskAdapter
from budgetflow.lite_tasks import load_swebench_lite_tasks


VALUE_LEAKAGE_KEYS = frozenset({
    "task_value",
    "criticality_level",
    "criticality_value",
    "resolved_value",
    "total_resolved_value",
    "value_profile",
    "value_source",
    "value_source_kind",
    "value_matrix",
})
BUDGET_LEAKAGE_KEYS = frozenset({
    "batch_budget_cap",
    "batch_spent",
    "batch_available",
    "budget_available",
    "planned_task_budget",
    "effective_task_budget",
})
FEATURE_NAMES = (
    "patch_lines",
    "f2p_count",
    "p2p_count",
    "problem_length",
    "gold_file_count",
    "estimated_task_token_demand",
)


@dataclass(frozen=True)
class RouterTrainingExample:
    instance_id: str
    features: dict[str, float]
    label: int


def task_features(task: Any) -> dict[str, float]:
    """Return value-blind pre-execution features for a SWE-bench task."""
    adapter = SwebenchTaskAdapter()
    base = adapter.features(task).as_record()
    workflow = getattr(task, "workflow", None)
    estimated_token_demand = 0.0
    if workflow is not None:
        estimated_token_demand = sum(
            float(getattr(step, "input_tokens", 0) or 0)
            for step in getattr(workflow, "steps", ())
        )
    if estimated_token_demand <= 0:
        estimated_token_demand = _metadata_token_demand(task)
    return {
        "patch_lines": float(base.get("patch_lines", 0) or 0),
        "f2p_count": float(base.get("f2p_count", 0) or 0),
        "p2p_count": float(base.get("p2p_count", 0) or 0),
        "problem_length": float(base.get("problem_length", 0) or 0),
        "gold_file_count": float(len(getattr(task, "gold_files", ()) or ())),
        "estimated_task_token_demand": float(estimated_token_demand),
    }


def _metadata_token_demand(task: Any) -> float:
    problem_words = len(str(getattr(task, "problem_statement", "") or "").split())
    patch_lines = len(str(getattr(task, "patch", "") or "").splitlines())
    f2p = len(getattr(task, "fail_to_pass", ()) or ())
    p2p = len(getattr(task, "pass_to_pass", ()) or ())
    gold_files = len(getattr(task, "gold_files", ()) or ())
    return 280.0 + problem_words * 1.5 + patch_lines * 6.0 + f2p * 20.0 + p2p * 8.0 + gold_files * 18.0


def validate_value_blind_feature_record(record: dict[str, Any]) -> None:
    """Reject records that would leak Task Value or budget state into training."""
    leaked = sorted((VALUE_LEAKAGE_KEYS | BUDGET_LEAKAGE_KEYS) & set(record))
    if leaked:
        raise ValueError(f"learned-router feature record contains leakage fields: {leaked}")


def load_historical_labels(jsonl_paths: Iterable[str | Path]) -> dict[str, int]:
    """Return labels where 1 means T3 resolved and T2 did not for the same task."""
    outcomes: dict[str, dict[int, bool]] = defaultdict(dict)
    for path in jsonl_paths:
        if not path:
            continue
        with Path(path).open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                task_id = str(row.get("instance_id") or "")
                if not task_id:
                    continue
                tier = _row_start_tier(row)
                if tier not in {2, 3}:
                    continue
                score_status = str(row.get("score_status") or "")
                outcomes[task_id][tier] = score_status == "pass"
    labels: dict[str, int] = {}
    for task_id, by_tier in outcomes.items():
        if 2 not in by_tier or 3 not in by_tier:
            continue
        labels[task_id] = 1 if by_tier[3] and not by_tier[2] else 0
    return labels


def _row_start_tier(row: dict[str, Any]) -> int | None:
    routing = str(row.get("routing") or "")
    strategy = str(row.get("strategy") or "")
    if routing == "all_tier2" or strategy == "bare_t2_baseline":
        return 2
    if routing in {"bare_t3", "all_t3", "all_pro"} or strategy == "bare_t3_baseline":
        return 3
    picks = row.get("backend_picks") or []
    if isinstance(picks, list) and picks:
        text = str(picks[0]).lower()
        if "tier2" in text:
            return 2
        if "tier3" in text:
            return 3
    return None


def build_training_examples(tasks: Iterable[Any], labels: dict[str, int]) -> list[RouterTrainingExample]:
    examples: list[RouterTrainingExample] = []
    for task in tasks:
        task_id = str(getattr(task, "instance_id", "") or "")
        if task_id not in labels:
            continue
        features = task_features(task)
        validate_value_blind_feature_record(features)
        examples.append(RouterTrainingExample(task_id, features, int(labels[task_id])))
    return examples


def load_training_tasks_for_labels(
    labels: dict[str, int],
    *,
    excluded_task_ids: set[str] | frozenset[str],
) -> list[Any]:
    """Load labeled historical tasks while excluding the evaluation task set."""
    training_ids = tuple(
        task_id for task_id in labels
        if task_id not in excluded_task_ids
    )
    if not training_ids:
        return []
    return load_swebench_lite_tasks(instance_ids=training_ids)


def score_tasks(
    tasks: Iterable[Any],
    *,
    training_examples: list[RouterTrainingExample] | None = None,
) -> tuple[dict[str, float], str]:
    task_list = list(tasks)
    if training_examples and len({ex.label for ex in training_examples}) >= 2 and len(training_examples) >= 6:
        try:
            return _sklearn_scores(task_list, training_examples), "sklearn_logistic_regression"
        except Exception as exc:  # pragma: no cover - fallback is the safety path
            return _fallback_scores(task_list), f"fallback_estimated_token_demand_after_sklearn_error:{type(exc).__name__}"
    return _fallback_scores(task_list), "fallback_estimated_token_demand"


def _sklearn_scores(tasks: list[Any], examples: list[RouterTrainingExample]) -> dict[str, float]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x_train = [[ex.features[name] for name in FEATURE_NAMES] for ex in examples]
    y_train = [ex.label for ex in examples]
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced", random_state=0),
    )
    model.fit(x_train, y_train)
    x_eval = [[task_features(task)[name] for name in FEATURE_NAMES] for task in tasks]
    probabilities = model.predict_proba(x_eval)
    class_index = list(model.classes_).index(1)
    return {
        str(getattr(task, "instance_id")): float(probabilities[index][class_index])
        for index, task in enumerate(tasks)
    }


def _fallback_scores(tasks: list[Any]) -> dict[str, float]:
    demand = {
        str(getattr(task, "instance_id")): task_features(task)["estimated_task_token_demand"]
        for task in tasks
    }
    return _percentile_ranks(demand)


def _percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 1.0}
    sorted_items = sorted(values.items(), key=lambda item: (item[1], item[0]))
    ranks: dict[str, float] = {}
    denominator = float(len(sorted_items) - 1)
    for index, (task_id, _value) in enumerate(sorted_items):
        ranks[task_id] = index / denominator
    return ranks


def build_learned_router_plan(
    tasks: Iterable[Any],
    *,
    name: str,
    training_examples: list[RouterTrainingExample] | None = None,
    strongest_fraction: float = 1.0 / 3.0,
) -> dict[str, Any]:
    task_list = list(tasks)
    if not task_list:
        raise ValueError("learned router plan requires at least one task")
    if not (0.0 < strongest_fraction <= 1.0):
        raise ValueError("strongest_fraction must be in (0, 1]")
    scores, training_mode = score_tasks(task_list, training_examples=training_examples)
    strongest_slots = max(1, math.ceil(len(task_list) * strongest_fraction))
    ranked_ids = sorted(scores, key=lambda task_id: (scores[task_id], task_id), reverse=True)
    strongest_ids = set(ranked_ids[:strongest_slots])
    plan = {
        task_id: {
            "preferred_model": "tier3" if task_id in strongest_ids else "tier2",
            "priority": int(round(scores[task_id] * 1000.0)),
        }
        for task_id in scores
    }
    return {
        "meta": {
            "name": name,
            "source_class": "routellm_inspired_value_blind_learned_router",
            "training_mode": training_mode,
            "uses_task_value": False,
            "uses_budget_state": False,
            "label": "T3 resolved and T2 did not resolve on frozen historical outcomes",
            "features": list(FEATURE_NAMES),
            "strongest_fraction": strongest_fraction,
            "task_order": [str(getattr(task, "instance_id")) for task in task_list],
            "description": (
                "RouteLLM-inspired value-blind task router. It emits only "
                "preferred_model and priority; the compare runner supplies the "
                "shared hard cap."
            ),
        },
        "plan": plan,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a value-blind learned-router frozen plan")
    parser.add_argument("--task-ids", required=True, help="comma-separated selected task IDs")
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--training-jsonl",
        action="append",
        default=[],
        help="historical JSONL with T2/T3 outcomes; repeatable",
    )
    parser.add_argument("--strongest-fraction", type=float, default=1.0 / 3.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    task_ids = tuple(part.strip() for part in args.task_ids.split(",") if part.strip())
    if not task_ids:
        raise SystemExit("--task-ids did not contain any IDs")
    tasks = load_swebench_lite_tasks(instance_ids=task_ids)
    labels = load_historical_labels(args.training_jsonl)
    training_tasks = load_training_tasks_for_labels(labels, excluded_task_ids=set(task_ids))
    examples = build_training_examples(training_tasks, labels)
    plan = build_learned_router_plan(
        tasks,
        name=args.name,
        training_examples=examples,
        strongest_fraction=args.strongest_fraction,
    )
    if args.training_jsonl:
        plan["meta"]["training_jsonl"] = [str(path) for path in args.training_jsonl]
        plan["meta"]["training_examples"] = len(examples)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {output}: entries={len(plan['plan'])} mode={plan['meta']['training_mode']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

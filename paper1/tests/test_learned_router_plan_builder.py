from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from budgetflow.frozen_router import load_frozen_plan
from budgetflow.learned_router_plan_builder import (
    build_learned_router_plan,
    build_training_examples,
    load_historical_labels,
    load_training_tasks_for_labels,
    task_features,
    validate_value_blind_feature_record,
)


def _task(
    instance_id: str,
    *,
    patch_lines: int = 1,
    f2p: int = 1,
    p2p: int = 0,
    problem_words: int = 10,
    gold_files: int = 1,
):
    return SimpleNamespace(
        instance_id=instance_id,
        patch="\n".join("line" for _ in range(patch_lines)),
        fail_to_pass=tuple(f"test_fail_{i}" for i in range(f2p)),
        pass_to_pass=tuple(f"test_pass_{i}" for i in range(p2p)),
        problem_statement=" ".join("word" for _ in range(problem_words)),
        gold_files=tuple(f"file_{i}.py" for i in range(gold_files)),
    )


def test_task_features_are_value_blind() -> None:
    features = task_features(_task("task-a", patch_lines=3, f2p=2, p2p=1))

    assert set(features) == {
        "patch_lines",
        "f2p_count",
        "p2p_count",
        "problem_length",
        "gold_file_count",
        "estimated_task_token_demand",
    }
    validate_value_blind_feature_record(features)


def test_feature_record_rejects_value_and_budget_leakage() -> None:
    with pytest.raises(ValueError, match="criticality_level"):
        validate_value_blind_feature_record({"criticality_level": "critical"})
    with pytest.raises(ValueError, match="batch_budget_cap"):
        validate_value_blind_feature_record({"batch_budget_cap": 6.0})


def test_load_historical_labels_marks_t3_only_success(tmp_path) -> None:
    jsonl = tmp_path / "hist.jsonl"
    rows = [
        {"instance_id": "task-a", "strategy": "bare_t2_baseline", "score_status": "true_fail"},
        {"instance_id": "task-a", "strategy": "bare_t3_baseline", "score_status": "pass"},
        {"instance_id": "task-b", "strategy": "bare_t2_baseline", "score_status": "pass"},
        {"instance_id": "task-b", "strategy": "bare_t3_baseline", "score_status": "pass"},
        {"instance_id": "task-c", "strategy": "bare_t3_baseline", "score_status": "pass"},
    ]
    jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    assert load_historical_labels([jsonl]) == {"task-a": 1, "task-b": 0}


def test_build_training_examples_uses_only_labeled_tasks() -> None:
    examples = build_training_examples(
        [_task("task-a"), _task("task-b")],
        {"task-a": 1},
    )

    assert len(examples) == 1
    assert examples[0].instance_id == "task-a"
    assert examples[0].label == 1
    validate_value_blind_feature_record(examples[0].features)


def test_load_training_tasks_for_labels_excludes_eval_tasks(monkeypatch) -> None:
    loaded_ids = ()

    def fake_load(*, instance_ids):
        nonlocal loaded_ids
        loaded_ids = instance_ids
        return [_task(task_id) for task_id in instance_ids]

    monkeypatch.setattr(
        "budgetflow.learned_router_plan_builder.load_swebench_lite_tasks",
        fake_load,
    )

    tasks = load_training_tasks_for_labels(
        {"eval-task": 1, "train-a": 0, "train-b": 1},
        excluded_task_ids={"eval-task"},
    )

    assert loaded_ids == ("train-a", "train-b")
    assert [task.instance_id for task in tasks] == ["train-a", "train-b"]


def test_fallback_plan_assigns_highest_demand_to_tier3_and_carries_no_caps_or_values(tmp_path) -> None:
    tasks = [
        _task("short", patch_lines=1, problem_words=5, gold_files=1),
        _task("long", patch_lines=20, problem_words=120, gold_files=4),
        _task("medium", patch_lines=5, problem_words=30, gold_files=2),
    ]

    plan = build_learned_router_plan(
        tasks,
        name="unit_learned_router",
        strongest_fraction=1.0 / 3.0,
    )

    assert plan["meta"]["source_class"] == "routellm_inspired_value_blind_learned_router"
    assert plan["meta"]["uses_task_value"] is False
    assert plan["meta"]["uses_budget_state"] is False
    assert "hard_cap_usd" not in plan["meta"]
    for entry in plan["plan"].values():
        assert set(entry) == {"preferred_model", "priority"}
    assert plan["plan"]["long"]["preferred_model"] == "tier3"
    assert plan["plan"]["short"]["preferred_model"] == "tier2"
    assert plan["plan"]["medium"]["preferred_model"] == "tier2"

    plan_path = tmp_path / "learned_router.json"
    plan_path.write_text(json.dumps(plan) + "\n")
    loaded = load_frozen_plan(plan_path)
    assert loaded.name == "unit_learned_router"

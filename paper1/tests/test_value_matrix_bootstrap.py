from __future__ import annotations

from types import SimpleNamespace

from budgetflow.value_matrix import build_bootstrap_value_matrix


def test_bootstrap_value_matrix_uses_only_pre_registered_task_features() -> None:
    task = SimpleNamespace(
        instance_id="repo__task",
        repo="repo/project",
        patch="diff --git a/x.py b/x.py\n+line\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=("tests/test_a.py", "tests/test_b.py"),
        problem_statement="short bug report",
        gold_files=("x.py",),
    )

    matrix = build_bootstrap_value_matrix([task], task_source="unit")
    entry = matrix["tasks"]["repo__task"]

    assert matrix["meta"]["task_value_profiles"] == ["equal"]
    assert matrix["meta"]["source_class"] == "bootstrap_pre_registered_metadata"
    assert matrix["meta"]["outcome_free"] is True
    assert entry["features"]["patch_lines"] == 2
    assert entry["task_value"]["equal"] == 1.0
    assert entry["task_effort"]["bootstrap_heuristic"] > 1.0
    assert "resolved_rows" not in entry
    assert "avg_cost" not in entry


def test_bootstrap_value_matrix_can_emit_manual_value_profile() -> None:
    task = SimpleNamespace(
        instance_id="repo__task",
        repo="repo/project",
        patch="diff --git a/x.py b/x.py\n+line\n",
        fail_to_pass=tuple(f"tests/test_x.py::test_{i}" for i in range(15)),
        pass_to_pass=tuple(f"tests/test_a.py::test_{i}" for i in range(120)),
        problem_statement="short bug report",
        gold_files=("x.py",),
    )

    matrix = build_bootstrap_value_matrix(
        [task],
        task_source="unit",
        include_manual_value=True,
    )
    entry = matrix["tasks"]["repo__task"]

    assert matrix["meta"]["value_source_kind"] == "pre_registered_manual"
    assert matrix["meta"]["manual_value_formula"].startswith("verification_breadth_v1")
    assert matrix["meta"]["task_value_profiles"] == ["equal", "manual_value"]
    assert 0.6 <= entry["task_value"]["manual_value"] <= 1.0
    assert entry["value_formula"] == "verification_breadth_v1"
    assert "manual_value" in matrix["rankings"]

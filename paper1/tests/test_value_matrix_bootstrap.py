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

    assert matrix["meta"]["profiles"] == ["equal", "bootstrap_difficulty"]
    assert matrix["meta"]["source_class"] == "bootstrap_pre_registered_metadata"
    assert matrix["meta"]["outcome_free"] is True
    assert entry["features"]["patch_lines"] == 2
    assert entry["values"]["equal"] == 1.0
    assert entry["values"]["bootstrap_difficulty"] > 1.0
    assert "resolved_rows" not in entry
    assert "avg_cost" not in entry

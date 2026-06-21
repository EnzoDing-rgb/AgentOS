from __future__ import annotations

import json
from pathlib import Path

from budgetflow.official_harness_crosscheck import official_eval_command, select_crosscheck_rows


def _write_row(path: Path, row: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")


def test_select_crosscheck_rows_prefers_workspace_patch_failures_plus_passes(tmp_path: Path) -> None:
    workspace_patch = tmp_path / "workspace.patch"
    workspace_patch.write_text("diff --git a/app.py b/app.py\n+fixed\n")
    input_path = tmp_path / "run.jsonl"
    output_path = tmp_path / "subset.jsonl"

    _write_row(input_path, {"instance_id": "fail-a", "score_status": "true_fail", "failure_class": "repair_fail", "workspace_patch": str(workspace_patch)})
    _write_row(input_path, {"instance_id": "skip-no-patch", "score_status": "true_fail", "failure_class": "repair_fail"})
    _write_row(input_path, {"instance_id": "pass-a", "score_status": "pass", "failure_class": "pass", "workspace_patch": str(workspace_patch)})

    count = select_crosscheck_rows(input_path, output_path, limit=2, include_passes=1)

    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert count == 2
    assert [row["instance_id"] for row in rows] == ["fail-a", "pass-a"]


def test_official_eval_command_points_at_official_swebench_runner(tmp_path: Path) -> None:
    cmd = official_eval_command(
        tmp_path / "predictions.jsonl",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        run_id="run-a",
        swebench_venv=Path("/opt/swebench"),
        max_workers=2,
    )

    assert "/opt/swebench/bin/python -m swebench.harness.run_evaluation" in cmd
    assert "--predictions_path" in cmd
    assert "--run_id run-a" in cmd

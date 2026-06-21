from __future__ import annotations

import json
from pathlib import Path

from budgetflow.official_harness_crosscheck import (
    build_crosscheck_artifacts,
    official_eval_command,
    official_eval_preflight,
    select_crosscheck_rows,
)


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


def test_select_crosscheck_rows_deduplicates_instances_for_official_predictions(tmp_path: Path) -> None:
    workspace_patch = tmp_path / "workspace.patch"
    workspace_patch.write_text("diff --git a/app.py b/app.py\n+fixed\n")
    input_path = tmp_path / "run.jsonl"
    output_path = tmp_path / "subset.jsonl"

    _write_row(input_path, {"instance_id": "same-task", "strategy": "bare_t3_baseline", "score_status": "true_fail", "failure_class": "repair_fail", "workspace_patch": str(workspace_patch)})
    _write_row(input_path, {"instance_id": "same-task", "strategy": "budgetflow_task_level", "score_status": "true_fail", "failure_class": "repair_fail", "workspace_patch": str(workspace_patch)})
    _write_row(input_path, {"instance_id": "other-task", "strategy": "budgetflow_task_level", "score_status": "pass", "failure_class": "pass", "workspace_patch": str(workspace_patch)})

    count = select_crosscheck_rows(input_path, output_path, limit=3, include_passes=1)

    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert count == 2
    assert [row["instance_id"] for row in rows] == ["same-task", "other-task"]


def test_select_crosscheck_rows_skips_missing_workspace_patch_paths(tmp_path: Path) -> None:
    existing_patch = tmp_path / "workspace.patch"
    existing_patch.write_text("diff --git a/app.py b/app.py\n+fixed\n")
    missing_patch = tmp_path / "missing.patch"
    input_path = tmp_path / "run.jsonl"
    output_path = tmp_path / "subset.jsonl"

    _write_row(
        input_path,
        {
            "instance_id": "missing-patch",
            "score_status": "true_fail",
            "failure_class": "repair_fail",
            "workspace_patch": str(missing_patch),
        },
    )
    _write_row(
        input_path,
        {
            "instance_id": "existing-patch",
            "score_status": "true_fail",
            "failure_class": "repair_fail",
            "workspace_patch": str(existing_patch),
        },
    )

    count = select_crosscheck_rows(input_path, output_path, limit=4, include_passes=0)

    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert count == 1
    assert [row["instance_id"] for row in rows] == ["existing-patch"]


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


def test_official_eval_preflight_warns_when_swebench_python_missing(tmp_path: Path) -> None:
    warnings = official_eval_preflight(swebench_venv=tmp_path / "missing")

    assert any(warning.startswith("missing_swebench_python:") for warning in warnings)


def test_build_crosscheck_artifacts_writes_manifest_predictions_and_command(tmp_path: Path) -> None:
    workspace_patch = tmp_path / "workspace.patch"
    workspace_patch.write_text("diff --git a/app.py b/app.py\n+fixed\n")
    input_path = tmp_path / "run.jsonl"
    out_dir = tmp_path / "crosscheck"
    _write_row(
        input_path,
        {
            "instance_id": "task-a",
            "strategy": "budgetflow_task_level",
            "score_status": "true_fail",
            "failure_class": "repair_fail",
            "workspace_patch": str(workspace_patch),
        },
    )

    manifest = build_crosscheck_artifacts(
        input_path,
        out_dir=out_dir,
        limit=4,
        include_passes=1,
        model_name="budgetflow-crosscheck",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        run_id="run-a-crosscheck",
        swebench_venv=tmp_path / "missing-venv",
        max_workers=1,
    )

    manifest_path = out_dir / "run.official_crosscheck.manifest.json"
    command_path = out_dir / "run.official_crosscheck.command.txt"

    assert manifest["selected_rows"] == 1
    assert manifest["exported_predictions"] == 1
    assert Path(manifest["rows_path"]).is_file()
    assert Path(manifest["predictions_path"]).is_file()
    assert manifest_path.is_file()
    assert command_path.is_file()
    assert "swebench.harness.run_evaluation" in command_path.read_text()
    saved = json.loads(manifest_path.read_text())
    assert saved["mode"] == "dry_run_artifact_only"
    assert saved["selected_rows"] == 1

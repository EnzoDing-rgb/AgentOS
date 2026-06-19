from __future__ import annotations

import json
from pathlib import Path

from budgetflow.export_official_predictions import export_predictions


def test_export_predictions_prefers_workspace_patch(tmp_path: Path) -> None:
    workspace_patch = tmp_path / "workspace.patch"
    submitted_patch = tmp_path / "submitted.patch"
    workspace_patch.write_text("diff --git a/app.py b/app.py\n+workspace\n")
    submitted_patch.write_text("diff --git a/app.py b/app.py\n+submitted\n")
    input_path = tmp_path / "run.jsonl"
    output_path = tmp_path / "predictions.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "instance_id": "repo__task",
                "strategy": "budgetflow_task_level",
                "workspace_patch": str(workspace_patch),
                "submitted_patch": str(submitted_patch),
            }
        )
        + "\n"
    )

    count = export_predictions(input_path, output_path, model_name="budgetflow")

    assert count == 1
    record = json.loads(output_path.read_text().strip())
    assert record["model_patch"] == workspace_patch.read_text()

from __future__ import annotations

import json
from pathlib import Path

from budgetflow.recost import run_sensitivity


def test_run_sensitivity_dedup_keeps_last_row(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                json.dumps({
                    "strategy": "bare_t3_baseline",
                    "instance_id": "task-a",
                    "score_status": "true_fail",
                    "task_value": 1.0,
                    "total_cost": 0.10,
                    "row_finished_at": 1,
                    "backend_picks": [],
                }),
                json.dumps({
                    "strategy": "bare_t3_baseline",
                    "instance_id": "task-a",
                    "score_status": "pass",
                    "task_value": 1.0,
                    "total_cost": 0.40,
                    "row_finished_at": 2,
                    "backend_picks": [],
                }),
            ]
        )
        + "\n"
    )

    report = run_sensitivity(jsonl, ratios=(3.0,))
    stats = report["results"]["3.0x"]["bare_t3_baseline"]

    assert stats["total"] == 1
    assert stats["pass"] == 1

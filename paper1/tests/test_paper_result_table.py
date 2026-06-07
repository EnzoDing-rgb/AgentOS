from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_paper_result_table import build_markdown_table  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def test_build_markdown_table_summarizes_runs(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "raw_t3.jsonl",
        [
            {
                "strategy": "all_t3",
                "instance_id": "task-1",
                "harness_resolved": True,
                "task_cost": 10.0,
                "llm_turns": 2,
                "failure_class": "pass",
            },
            {
                "strategy": "all_t3",
                "instance_id": "task-2",
                "harness_resolved": False,
                "task_cost": 20.0,
                "llm_turns": 3,
                "failure_class": "repair_fail",
            },
        ],
    )
    _write_jsonl(
        tmp_path / "budgetflow.jsonl",
        [
            {
                "strategy": "budgetflow_equal_weight_tight",
                "instance_id": "task-1",
                "harness_resolved": True,
                "task_cost": 7.0,
                "llm_turns": 4,
                "failure_class": "pass",
            }
        ],
    )

    text = build_markdown_table(
        run_dir=tmp_path,
        stems=["raw_t3", "budgetflow"],
        labels={"raw_t3": "raw ceiling", "budgetflow": "BudgetFlow"},
    )

    assert "| forensic_axes |" in text
    assert "| raw ceiling | `all_t3` | 2 | 1/2 | 30.0 | 15.0 | 5 | pass=1, repair_fail=1 | pass=1, unknown=1 | inspect repair failures with forensic trace |" in text
    assert "| BudgetFlow | `budgetflow_equal_weight_tight` | 1 | 1/1 | 7.0 | 7.0 | 4 | pass=1 | pass=1 | keep / scale cautiously |" in text

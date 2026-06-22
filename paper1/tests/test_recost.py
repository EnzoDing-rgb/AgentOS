from __future__ import annotations

import json
from pathlib import Path

from budgetflow.recost import run_sensitivity
from budgetflow.recost import recost_record


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


def test_recost_uses_catalog_t2_cache_policy() -> None:
    recosted = recost_record(
        {
            "strategy": "budgetflow_task_level",
            "instance_id": "task-a",
            "backend_picks": ["tier2", "tier2"],
            "prompt_tokens_total": 2000,
            "completion_tokens_total": 0,
            "llm_turns": 2,
        },
        t3_multiplier=3.0,
    )

    # Turn 1 input: 1000 * 0.90 / 1M.
    # Turn 2 input: same tokens with mainline input_kv_cache_discount=0.0.
    assert recosted["total_cost"] == 0.0018
    assert recosted["recost_input_kv_cache_discount"] == 0.0

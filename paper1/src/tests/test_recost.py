from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from budgetflow.recost import rank_strategies
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
    assert stats["resolved_count"] == 1
    assert stats["resolved_rate"] == 1.0
    assert stats["total_spend"] == 0.4
    assert stats["cost_per_resolved_task"] == 0.4
    assert stats["total_resolved_value"] == 1.0
    assert stats["total_resolved_value_per_dollar"] == 2.5


def test_recost_ranks_by_total_resolved_value_per_dollar_by_default() -> None:
    report = {
        "results": {
            "3.0x": {
                "high_value": {
                    "yield_per_dollar": 1.0,
                    "total_resolved_value_per_dollar": 3.0,
                },
                "legacy_only": {
                    "yield_per_dollar": 2.0,
                    "total_resolved_value_per_dollar": 1.0,
                },
            }
        }
    }

    assert rank_strategies(report)["3.0x"] == [
        ("high_value", 3.0),
        ("legacy_only", 1.0),
    ]


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
        t3_target_ratio=3.0,
    )

    # Turn 1 input: 1000 * 0.90 / 1M.
    # Turn 2 input: same tokens with mainline input_kv_cache_discount=0.0.
    assert recosted["total_cost"] == 0.0018
    assert recosted["recost_input_kv_cache_discount"] == 0.0


def test_recost_can_apply_sensitivity_kv_discount_to_t2_and_t3_turns() -> None:
    recosted = recost_record(
        {
            "strategy": "budgetflow_task_level",
            "instance_id": "task-a",
            "backend_picks": ["tier2", "tier2", "tier3", "tier3"],
            "turn_traces": [
                {"final_backend": "tier2", "prompt_tokens": 1000, "completion_tokens": 100},
                {"final_backend": "tier2", "prompt_tokens": 1000, "completion_tokens": 100},
                {"final_backend": "tier3", "prompt_tokens": 1000, "completion_tokens": 100},
                {"final_backend": "tier3", "prompt_tokens": 1000, "completion_tokens": 100},
            ],
            "prompt_tokens_total": 4000,
            "completion_tokens_total": 400,
            "llm_turns": 4,
        },
        t3_target_ratio=5.0,
        input_kv_cache_discount=0.5,
        input_discount_after_turn=1,
        min_input_cost_fraction=0.5,
    )

    # T2 input: 0.0009 + 0.00045. T2 output: 2 * 100 * 4.5 / 1M.
    # T3 input: 0.0045 + 0.00225. T3 output: 2 * 100 * 22.5 / 1M.
    assert recosted["total_cost"] == 0.0135
    assert recosted["recost_input_kv_cache_discount"] == 0.5
    assert recosted["recost_kv_discount_applies_to"] == ["tier2", "tier3"]


def test_recost_t3_target_ratio_is_not_extra_multiplier() -> None:
    recosted = recost_record(
        {
            "strategy": "bare_t3_baseline",
            "instance_id": "task-a",
            "backend_picks": ["tier3"],
            "turn_traces": [
                {"final_backend": "tier3", "prompt_tokens": 1000, "completion_tokens": 100},
            ],
            "prompt_tokens_total": 1000,
            "completion_tokens_total": 100,
            "llm_turns": 1,
        },
        t3_target_ratio=5.0,
    )

    # T3 ratio 5.0 means T2 rates multiplied by 5, not catalog T3 rates
    # multiplied by another 5.
    assert recosted["total_cost"] == 0.00675


def test_recost_kv90_requires_lower_min_input_fraction() -> None:
    recosted = recost_record(
        {
            "strategy": "bare_t2_baseline",
            "instance_id": "task-a",
            "backend_picks": ["tier2", "tier2"],
            "turn_traces": [
                {"final_backend": "tier2", "prompt_tokens": 1000, "completion_tokens": 0},
                {"final_backend": "tier2", "prompt_tokens": 1000, "completion_tokens": 0},
            ],
            "prompt_tokens_total": 2000,
            "completion_tokens_total": 0,
            "llm_turns": 2,
        },
        t3_target_ratio=5.0,
        input_kv_cache_discount=0.9,
        min_input_cost_fraction=0.1,
    )

    assert recosted["total_cost"] == 0.00099


def test_recost_cli_accepts_kv_discount(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    output = tmp_path / "report.json"
    jsonl.write_text(
        json.dumps({
            "strategy": "budgetflow_task_level",
            "instance_id": "task-a",
            "score_status": "pass",
            "task_value": 1.0,
            "backend_picks": ["tier2", "tier2"],
            "turn_traces": [
                {"final_backend": "tier2", "prompt_tokens": 1000, "completion_tokens": 0},
                {"final_backend": "tier2", "prompt_tokens": 1000, "completion_tokens": 0},
            ],
            "prompt_tokens_total": 2000,
            "completion_tokens_total": 0,
            "llm_turns": 2,
            "row_finished_at": 1,
        })
        + "\n"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budgetflow.recost",
            str(jsonl),
            str(output),
            "--ratios",
            "1.0",
            "--kv-discount",
            "0.5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    stats = report["results"]["1.0x"]["budgetflow_task_level"]
    assert stats["total_cost"] == 0.0014
    assert report["input_kv_cache_discount"] == 0.5

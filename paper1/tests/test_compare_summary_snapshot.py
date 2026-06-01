from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.run_mini_swe_compare import _format_live_snapshot  # noqa: E402


def test_live_snapshot_lists_strategy_pass_fail() -> None:
    lines = _format_live_snapshot(
        strategy_names=["all_spark_tight", "budgetflow_full_tight"],
        resolved_by_strategy={
            "all_spark_tight": [False, False],
            "budgetflow_full_tight": [True, False, True],
        },
        task_cost_by_strategy={
            "all_spark_tight": [10.0, 20.0],
            "budgetflow_full_tight": [30.0, 40.0, 50.0],
        },
        turns_by_strategy={
            "all_spark_tight": [2, 4],
            "budgetflow_full_tight": [6, 8, 10],
        },
        spark_by_strategy={"all_spark_tight": [1.0, 1.0], "budgetflow_full_tight": [0.0, 0.0, 0.0]},
        flash_by_strategy={"all_spark_tight": [0.0, 0.0], "budgetflow_full_tight": [0.0, 0.0, 0.0]},
        pro_by_strategy={"all_spark_tight": [0.0, 0.0], "budgetflow_full_tight": [0.0, 0.0, 0.0]},
        t4_by_strategy={"all_spark_tight": [0.0, 0.0], "budgetflow_full_tight": [1.0, 1.0, 1.0]},
        batch_spent_by_strategy={"all_spark_tight": 30.0, "budgetflow_full_tight": 120.0},
        batch_caps={"all_spark_tight": 100.0, "budgetflow_full_tight": 3000.0},
        runs_done=5,
        total_runs=30,
        tasks_per_strategy=15,
        started=0.0,
        out_path=Path("/tmp/out.jsonl"),
        global_line="global total=30 done=5 running=25",
    )
    text = "\n".join(lines)
    assert "RUN STATUS done=5/30" in text
    assert "pass=2 fail=3" in text
    assert " T4 " in text
    assert "all_spark_tight" in text
    assert "    2   15     0     2" in text
    assert "budgetflow_full_tight" in text
    assert "    3   15     2     1" in text
    assert "      3000" in text

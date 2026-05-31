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
        runs_done=5,
        total_runs=30,
        tasks_per_strategy=15,
        started=0.0,
        out_path=Path("/tmp/out.jsonl"),
        global_line="global total=30 done=5 running=25",
    )
    text = "\n".join(lines)
    assert "LIVE SNAPSHOT" in text
    assert "GLOBAL done=5/30" in text
    assert "PASS=2 FAIL=3" in text
    assert "all_spark_tight" in text
    assert "    2   15     0     2" in text
    assert "budgetflow_full_tight" in text
    assert "    3   15     2     1" in text

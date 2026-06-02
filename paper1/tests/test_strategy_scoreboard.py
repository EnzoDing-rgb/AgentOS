from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.compare_checkpoint import StrategyScoreboard, strategy_abbrev  # noqa: E402


def test_strategy_scoreboard_live_line() -> None:
    names = ["all_spark_tight", "budget_only_tight", "all_pro"]
    board = StrategyScoreboard(names)
    board.record("all_spark_tight", resolved=True)
    board.record("all_spark_tight", resolved=False)
    board.record("budget_only_tight", resolved=True)
    line = board.format_line()
    assert "as-T 1/2" in line
    assert "bo-T 1/1" in line
    assert "apro 0/0" in line
    assert strategy_abbrev("all_spark_tight") == "as-T"
    assert strategy_abbrev("all_flash_tight") == "as-T"


def test_ceiling_strategy_abbrevs() -> None:
    assert strategy_abbrev("all_pro") == "apro"
    assert strategy_abbrev("all_t3") == "t3"
    assert strategy_abbrev("all_gpt53") == "t3"

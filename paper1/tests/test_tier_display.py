from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.console_log import backend_tier_label, format_tier_pool_line
from budgetflow.defaults import (
    TIER1_BACKEND,
    TIER1_DISPLAY,
    TIER2_BACKEND,
    TIER2_DISPLAY,
    TIER3_BACKEND,
    TIER3_DISPLAY,
    TIER4_BACKEND,
    TIER4_DISPLAY,
    TIER4_GPT53_BACKEND,
    TIER4_GPT53_DISPLAY,
    TIER4_QWEN_MAX_BACKEND,
    TIER4_QWEN_MAX_DISPLAY,
    tier_display_name,
)


def test_tier_display_name_mapping() -> None:
    assert tier_display_name(TIER1_BACKEND) == TIER1_DISPLAY
    assert tier_display_name(TIER2_BACKEND) == TIER2_DISPLAY
    assert tier_display_name(TIER3_BACKEND) == TIER3_DISPLAY
    assert tier_display_name(TIER4_BACKEND) == TIER4_DISPLAY
    assert tier_display_name(TIER4_QWEN_MAX_BACKEND) == TIER4_QWEN_MAX_DISPLAY
    assert tier_display_name(TIER4_GPT53_BACKEND) == TIER4_GPT53_DISPLAY


def test_backend_tier_label_full_names_not_abbrev() -> None:
    for backend, expected in (
        (TIER1_BACKEND, TIER1_DISPLAY),
        (TIER2_BACKEND, TIER2_DISPLAY),
        (TIER3_BACKEND, TIER3_DISPLAY),
        (TIER4_BACKEND, TIER4_DISPLAY),
        (TIER4_QWEN_MAX_BACKEND, TIER4_QWEN_MAX_DISPLAY),
        (TIER4_GPT53_BACKEND, TIER4_GPT53_DISPLAY),
    ):
        label = backend_tier_label(backend)
        assert expected in label
        assert "T1/" not in label and "T3/pro" not in label


def test_tier_pool_line_marks_t1_skipped_by_default() -> None:
    line = format_tier_pool_line()

    assert "skipped in main pool" in line
    assert TIER2_DISPLAY in line


def test_tier_pool_line_can_show_t1_for_ablation() -> None:
    line = format_tier_pool_line(include_t1=True)

    assert TIER1_DISPLAY in line
    assert "skipped in main pool" not in line

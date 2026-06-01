from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.console_log import backend_tier_label
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
    tier_display_name,
)


def test_tier_display_name_mapping() -> None:
    assert tier_display_name(TIER1_BACKEND) == TIER1_DISPLAY
    assert tier_display_name(TIER2_BACKEND) == TIER2_DISPLAY
    assert tier_display_name(TIER3_BACKEND) == TIER3_DISPLAY
    assert tier_display_name(TIER4_BACKEND) == TIER4_DISPLAY
    assert tier_display_name(TIER4_GPT53_BACKEND) == TIER4_GPT53_DISPLAY


def test_backend_tier_label_full_names_not_abbrev() -> None:
    for backend, expected in (
        (TIER1_BACKEND, TIER1_DISPLAY),
        (TIER2_BACKEND, TIER2_DISPLAY),
        (TIER3_BACKEND, TIER3_DISPLAY),
        (TIER4_BACKEND, TIER4_DISPLAY),
        (TIER4_GPT53_BACKEND, TIER4_GPT53_DISPLAY),
    ):
        label = backend_tier_label(backend)
        assert expected in label
        assert "T1/" not in label and "T3/pro" not in label

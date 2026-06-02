from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow import defaults


def test_current_tiers_are_coder_flash_coder_plus_gpt53_codex() -> None:
    assert defaults.TIER1_DISPLAY == "qwen3-coder-flash"
    assert defaults.TIER1_MODEL == "openai/qwen3-coder-flash"
    assert defaults.TIER2_DISPLAY == "qwen3-coder-plus"
    assert defaults.TIER2_MODEL == "openai/qwen3-coder-plus"
    assert defaults.TIER3_DISPLAY == "GPT-5.3 Codex"
    assert defaults.TIER3_MODEL == "openai/gpt-5.3-codex"


def test_gpt55_is_not_in_active_tier_maps() -> None:
    all_values = set(defaults.TIER_DISPLAY_BY_BACKEND.values()) | set(defaults.TIER_MODEL_BY_BACKEND.values())

    assert all("gpt-5.5" not in value.lower() for value in all_values)


def test_gpt53_codex_is_t3() -> None:
    assert defaults.TIER_MODEL_BY_BACKEND[defaults.TIER3_BACKEND] == "openai/gpt-5.3-codex"

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow import defaults


def test_current_tiers_are_stable_budgetflow_ids() -> None:
    assert defaults.TIER1_BACKEND == "tier1"
    assert defaults.TIER2_BACKEND == "tier2"
    assert defaults.TIER3_BACKEND == "tier3"


def test_current_tier_registry_maps_to_provider_models() -> None:
    assert defaults.TIER1_DISPLAY == "qwen3-coder-flash"
    assert defaults.TIER1_MODEL == "openai/qwen3-coder-flash"
    assert defaults.TIER2_DISPLAY == "qwen3-coder-plus"
    assert defaults.TIER2_MODEL == "openai/qwen3-coder-plus"
    assert defaults.TIER3_DISPLAY == "GPT-5.4"
    assert defaults.TIER3_MODEL == "openai/gpt-5.4"
    assert defaults.TIER_CONFIGS[defaults.TIER3_BACKEND].provider == "aicode007"
    assert defaults.TIER_CONFIGS[defaults.TIER3_BACKEND].text_mode is True


def test_gpt55_is_not_in_active_tier_maps() -> None:
    all_values = set(defaults.TIER_DISPLAY_BY_BACKEND.values()) | set(defaults.TIER_MODEL_BY_BACKEND.values())

    assert all("gpt-5.5" not in value.lower() for value in all_values)


def test_t3_model_lookup_uses_registry() -> None:
    assert defaults.TIER_MODEL_BY_BACKEND[defaults.TIER3_BACKEND] == defaults.TIER_CONFIGS[defaults.TIER3_BACKEND].model

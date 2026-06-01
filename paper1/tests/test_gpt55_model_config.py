from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow import defaults


def test_tier5_model_requests_actual_gpt55() -> None:
    assert defaults.TIER5_DISPLAY == "gpt-5.5"
    assert defaults.TIER5_MODEL == "openai/gpt-5.5"
    assert defaults.TIER_MODEL_BY_BACKEND[defaults.TIER5_BACKEND] == "openai/gpt-5.5"


def test_tier5_model_does_not_mask_mini_model_as_gpt55() -> None:
    assert "mini" not in defaults.TIER5_MODEL
    assert "gpt-5.4" not in defaults.TIER5_MODEL


def test_gpt53_codex_is_opt_in_regular_t4_candidate() -> None:
    assert defaults.TIER4_GPT53_DISPLAY == "gpt-5.3-codex"
    assert defaults.TIER4_GPT53_MODEL == "openai/gpt-5.3-codex"
    assert defaults.TIER_MODEL_BY_BACKEND[defaults.TIER4_GPT53_BACKEND] == "openai/gpt-5.3-codex"


def test_qwen_max_is_opt_in_regular_t4_candidate() -> None:
    assert defaults.TIER4_QWEN_MAX_DISPLAY == "qwen3.7-max"
    assert defaults.TIER4_QWEN_MAX_MODEL == "openai/qwen3.7-max"
    assert defaults.TIER_MODEL_BY_BACKEND[defaults.TIER4_QWEN_MAX_BACKEND] == "openai/qwen3.7-max"

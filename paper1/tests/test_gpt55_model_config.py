from __future__ import annotations

from budgetflow import defaults


def test_tier5_model_requests_actual_gpt55() -> None:
    assert defaults.TIER5_DISPLAY == "gpt-5.5"
    assert defaults.TIER5_MODEL == "openai/gpt-5.5"
    assert defaults.TIER_MODEL_BY_BACKEND[defaults.TIER5_BACKEND] == "openai/gpt-5.5"


def test_tier5_model_does_not_mask_mini_model_as_gpt55() -> None:
    assert "mini" not in defaults.TIER5_MODEL
    assert "gpt-5.4" not in defaults.TIER5_MODEL

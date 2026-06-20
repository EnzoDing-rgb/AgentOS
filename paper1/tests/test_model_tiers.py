from pathlib import Path

import pytest


def test_default_catalog_missing_fails_fast(monkeypatch) -> None:
    import budgetflow.model_tiers as mt

    original_path = mt.catalog_path()
    missing = Path("/tmp/budgetflow-missing-model-tiers.json")
    monkeypatch.setattr(mt, "DEFAULT_CATALOG_PATH", missing)

    with pytest.raises(FileNotFoundError, match="model tier catalog not found"):
        mt.init_catalog()

    if original_path is not None:
        mt.init_catalog(original_path)


def test_catalog_source_info_requires_initialized_catalog(monkeypatch) -> None:
    import budgetflow.model_tiers as mt

    monkeypatch.setattr(mt, "_catalog_path", None)

    with pytest.raises(RuntimeError, match="model tier catalog is not initialized"):
        mt.catalog_source_info()


def test_t2_input_kv_cache_discount_halves_input_after_first_turn() -> None:
    import budgetflow.model_tiers as mt

    first = mt.estimate_token_cost(
        "tier2",
        input_tokens=1000,
        output_tokens=0,
        turn_index=1,
    )
    second = mt.estimate_token_cost(
        "tier2",
        input_tokens=1000,
        output_tokens=0,
        turn_index=2,
    )
    output_first = mt.estimate_token_cost(
        "tier2",
        input_tokens=0,
        output_tokens=1000,
        turn_index=1,
    )
    output_second = mt.estimate_token_cost(
        "tier2",
        input_tokens=0,
        output_tokens=1000,
        turn_index=2,
    )

    assert second == pytest.approx(first * 0.5)
    assert output_second == pytest.approx(output_first)


def test_default_t2_uses_deepseek_v4_pro_provider() -> None:
    import budgetflow.model_tiers as mt

    tier2 = mt.MODEL_CATALOG.require_config("tier2")
    info = mt.catalog_source_info()

    assert tier2.model == "openai/deepseek-v4-pro"
    assert tier2.api_base == "https://api.deepseek.com/v1"
    assert tier2.api_key_env == "DEEPSEEK_API_KEY"
    assert tier2.display == "DeepSeek-V4-Pro"
    assert tier2.protocol == "tool_call"
    assert tier2.max_turns == 35
    assert info["catalog_semantic_revision"] == "t2-normalized-v1-t3x5"


def test_default_catalog_accepts_provider_only_t2_swap_history() -> None:
    import budgetflow.model_tiers as mt

    ok, reason = mt.catalog_record_compatible({
        "catalog_revision": "2026-06-17-glm51-t2-t3x5",
        "catalog_content_hash": "70beda1fbecb",
    })

    assert ok is True
    assert reason == "clean"


def test_default_catalog_rejects_unknown_semantic_history() -> None:
    import budgetflow.model_tiers as mt

    ok, reason = mt.catalog_record_compatible({
        "catalog_revision": "different-revision",
        "catalog_content_hash": "not-current",
    })

    assert ok is False
    assert reason == "catalog_mismatch"

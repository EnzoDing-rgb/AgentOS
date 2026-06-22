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


def test_default_t2_has_no_mainline_kv_cache_discount() -> None:
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

    assert second == pytest.approx(first)
    assert output_second == pytest.approx(output_first)


def test_kv50_catalog_applies_same_t2_t3_input_discount_after_first_turn() -> None:
    import budgetflow.model_tiers as mt

    original_path = mt.catalog_path()
    kv50_path = Path(__file__).resolve().parents[1] / "docs/config/model_tiers.kv50.json"
    mt.init_catalog(kv50_path)
    try:
        info = mt.catalog_source_info()
        assert info["catalog_revision"] == "2026-06-22-deepseek-v4-pro-t2-t3x5-kv50"
        assert info["catalog_semantic_revision"] == "t2-normalized-v1-t3x5-kv50"
        for backend in ("tier2", "tier3"):
            cfg = mt.MODEL_CATALOG.require_config(backend)
            assert cfg.turn_cache_policy.input_kv_cache_discount == pytest.approx(0.5)
            assert cfg.turn_cache_policy.min_input_cost_fraction == pytest.approx(0.5)
            first = mt.estimate_token_cost(
                backend,
                input_tokens=1000,
                output_tokens=0,
                turn_index=1,
            )
            second = mt.estimate_token_cost(
                backend,
                input_tokens=1000,
                output_tokens=0,
                turn_index=2,
            )
            output_first = mt.estimate_token_cost(
                backend,
                input_tokens=0,
                output_tokens=1000,
                turn_index=1,
            )
            output_second = mt.estimate_token_cost(
                backend,
                input_tokens=0,
                output_tokens=1000,
                turn_index=2,
            )
            assert second == pytest.approx(first * 0.5)
            assert output_second == pytest.approx(output_first)
    finally:
        if original_path is not None:
            mt.init_catalog(original_path)


def test_task_level_decision_cost_uses_backend_cache_policy() -> None:
    from budgetflow.decision_costs import TASK_LEVEL_DECISION_INPUT_TOKENS
    from budgetflow.decision_costs import task_level_decision_per_turn_cost
    from budgetflow.types import Backend

    no_cache = Backend(
        "tier2",
        2,
        1.0,
        10.0,
        100,
        20,
        100,
        0.5,
        1000,
    )
    kv50 = Backend(
        "tier2",
        2,
        1.0,
        10.0,
        100,
        20,
        100,
        0.5,
        1000,
        turn_cache_input_kv_discount=0.5,
        turn_cache_min_input_cost_fraction=0.5,
    )

    assert task_level_decision_per_turn_cost(kv50) == pytest.approx(
        task_level_decision_per_turn_cost(no_cache)
        - TASK_LEVEL_DECISION_INPUT_TOKENS * 0.5
    )


def test_default_t2_uses_deepseek_v4_pro_provider() -> None:
    import budgetflow.model_tiers as mt

    tier2 = mt.MODEL_CATALOG.require_config("tier2")
    info = mt.catalog_source_info()

    assert tier2.model == "openai/deepseek-v4-pro"
    assert tier2.api_base == "https://api.deepseek.com/v1"
    assert tier2.api_key_env == "DEEPSEEK_API_KEY"
    assert tier2.display == "DeepSeek-V4-Pro"
    assert tier2.protocol == "tool_call"
    assert tier2.max_turns == 60
    assert info["catalog_semantic_revision"] == "t2-normalized-v1-t3x5"


def test_default_catalog_uses_unified_mainline_turn_cap() -> None:
    import budgetflow.model_tiers as mt

    assert {cfg.max_turns for cfg in mt.MODEL_CATALOG.configs} == {60}

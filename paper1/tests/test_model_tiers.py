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

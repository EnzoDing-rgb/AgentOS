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

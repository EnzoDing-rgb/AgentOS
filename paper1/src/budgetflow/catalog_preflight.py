from __future__ import annotations

from .console_log import tag
from .model_tiers import MODEL_CATALOG, validate_tier_catalog


def print_tier_catalog_preflight() -> list[str]:
    """Print cost/progress confidence and return blocking catalog issues."""
    issues = validate_tier_catalog()
    for cfg in MODEL_CATALOG.configs:
        print(
            f"{tag('catalog', bold=False)} backend={cfg.backend} model={cfg.model} "
            f"cost_updated={cfg.cost_updated} progress_updated={cfg.progress_updated} "
            f"cost_source={cfg.cost_source}",
            flush=True,
        )
    for issue in issues:
        print(f"{tag('catalog', bold=False)} FAIL {issue}", flush=True)
    return issues

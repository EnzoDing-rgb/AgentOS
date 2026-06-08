"""Cost adapter: normalizes model-cost signals for BudgetFlow Mechanism.

Cost follows the same adapter rule as value. Default experiments anchor
cost to a versioned public price catalog. Enterprise deployments can
replace or calibrate that with provider estimates, invoices, internal
rate cards, or manual overrides.

BudgetFlow Mechanism consumes a normalized CostEstimate plus confidence.
It does not read provider price files or know the tier catalog schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class CostEstimate:
    """Normalized per-turn cost estimate consumed by BudgetFlow Mechanism."""

    usd: float
    source: str
    confidence: dict[str, float | str | bool] = field(default_factory=dict)


class CostAdapter(Protocol):
    """Contract: normalize cost signals into CostEstimate.

    Concrete adapters may use public price catalogs, provider estimates,
    invoices, or rate cards. BudgetFlow Mechanism only consumes CostEstimate.
    """

    def estimate(
        self,
        backend: str,
        input_tokens: int,
        expected_output_tokens: int,
        **context: Any,
    ) -> CostEstimate: ...

    def settle(self, estimate: CostEstimate, actual: dict[str, Any] | None) -> dict[str, Any]: ...


class SwebenchCostAdapter:
    """SWE-bench cost adapter wrapping the existing ModelCatalog.

    Uses the versioned public price catalog (ModelCatalog / TierConfig)
    to compute per-turn cost estimates. Token-cost banding, provider
    confidence, and catalog revision are SWE-bench adapter details.
    BudgetFlow Mechanism only sees CostEstimate.
    """

    def __init__(self, model_catalog: Any | None = None) -> None:
        from ..model_tiers import MODEL_CATALOG as _default_catalog

        self._catalog = model_catalog or _default_catalog

    def estimate(
        self,
        backend: str,
        input_tokens: int,
        expected_output_tokens: int,
        **context: Any,
    ) -> CostEstimate:
        config = self._catalog.config_for(backend)
        if config is None:
            raise ValueError(
                f"CostAdapter: unknown backend '{backend}'. "
                f"All backends must be registered in the model tier catalog "
                f"before cost estimates can be produced."
            )

        # Token-cost banding for input-length tiered pricing
        input_rate = config.cost_per_input_token
        output_rate = config.cost_per_output_token
        for band in getattr(config, 'token_cost_bands', ()) or ():
            if band.max_input_tokens is None or input_tokens <= band.max_input_tokens:
                input_rate = band.input_per_1m / 1_000_000
                output_rate = band.output_per_1m / 1_000_000
                break

        usd = input_tokens * input_rate + expected_output_tokens * output_rate
        return CostEstimate(
            usd=round(usd, 8),
            source=f"tier_catalog:{config.cost_source}",
            confidence={
                "cost_updated": config.cost_updated,
                "backend": backend,
            },
        )

    def settle(
        self,
        estimate: CostEstimate,
        actual: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if actual is None:
            return {"estimated_usd": estimate.usd, "actual_usd": None, "settled": False}
        actual_usd = float(actual.get("actual_cost", 0))
        return {
            "estimated_usd": estimate.usd,
            "actual_usd": actual_usd,
            "delta_usd": actual_usd - estimate.usd,
            "settled": True,
        }

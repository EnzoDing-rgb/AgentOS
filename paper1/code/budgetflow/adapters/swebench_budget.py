"""Budget adapter: normalizes budget-window inputs for BudgetFlow."""

from __future__ import annotations

from typing import Any, Protocol

from ..model_tiers import MODEL_CATALOG


class BudgetAdapter(Protocol):
    def normalize(self, **inputs: Any) -> dict[str, Any]: ...


class SwebenchBudgetAdapter:
    """Build the experiment budget input from pre-registered run arguments."""

    def normalize(
        self,
        *,
        hard_cap_usd: float,
        soft_cap_usd: float | None = None,
        account_id: str = "swebench-compare",
        window: str = "run",
        shared: bool = True,
        allowed_backends: tuple[str, ...] | None = None,
        source: str = "pre_registered_experiment_budget",
        **confidence: float | str | bool,
    ) -> dict[str, Any]:
        return {
            "account_id": account_id,
            "window": window,
            "hard_cap_usd": float(hard_cap_usd),
            "soft_cap_usd": None if soft_cap_usd is None else float(soft_cap_usd),
            "allowed_backends": list(allowed_backends or tuple(backend.name for backend in MODEL_CATALOG.backends())),
            "shared": shared,
            "source": source,
            "confidence": dict(confidence),
        }

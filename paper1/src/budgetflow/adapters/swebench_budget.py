"""Budget adapter: normalizes budget-window inputs for BudgetFlow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..model_tiers import MODEL_CATALOG


@dataclass(frozen=True)
class BudgetContext:
    account_id: str
    window: str
    hard_cap_usd: float
    soft_cap_usd: float | None = None
    allowed_backends: tuple[str, ...] = ()
    shared: bool = True
    source: str = "manual"
    confidence: dict[str, float | str | bool] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "window": self.window,
            "hard_cap_usd": self.hard_cap_usd,
            "soft_cap_usd": self.soft_cap_usd,
            "allowed_backends": list(self.allowed_backends),
            "shared": self.shared,
            "source": self.source,
            "confidence": dict(self.confidence),
        }


class BudgetAdapter(Protocol):
    def context(self, **inputs: Any) -> BudgetContext: ...


class SwebenchBudgetAdapter:
    """Build the experiment budget context from pre-registered run inputs."""

    def context(
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
    ) -> BudgetContext:
        return BudgetContext(
            account_id=account_id,
            window=window,
            hard_cap_usd=float(hard_cap_usd),
            soft_cap_usd=None if soft_cap_usd is None else float(soft_cap_usd),
            allowed_backends=allowed_backends or tuple(backend.name for backend in MODEL_CATALOG.backends()),
            shared=shared,
            source=source,
            confidence=dict(confidence),
        )

"""AllocationContext — standard decision input for BudgetFlow policies.

Carries the three North Star inputs (Task Value, Task Effort, Model Fit)
plus budget state, cost source, and confidence into policy decisions.

This dataclass is mechanism-level.  Domain adapters (SWE-bench, enterprise)
populate it; policy backends consume it.  No benchmark detail lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AllocationContext:
    """Standardised decision input for one task in a BudgetFlow policy.

    Task Value, Task Effort, and Model Fit are separate concepts (North Star).
    They must not be conflated in a single number or namespace.
    """

    task_value: float = 1.0
    """Estimated utility of a verified resolved outcome (Claim 1 input)."""

    task_effort: float | None = None
    """Estimated work, runway, or expected cost (diagnostic, not Claim 1 value)."""

    model_fit: dict[str, float] | None = None
    """Per-tier effectiveness prior (tier_name -> expected progress rate).

    The canonical keyed form is ``{"tier2": rate, "tier3": rate}``.
    ``{"strongest_vs_reference": delta}`` is accepted as a derived form at
    policy boundaries, but runtime adapters should prefer per-tier rates.
    """

    # Provenance
    value_source: str = "equal_sanity"
    effort_source: str = "none"
    model_fit_source: str = "catalog_progress_prior"

    # Confidence per input
    confidence: dict[str, str] = field(default_factory=dict)

    @property
    def has_effort(self) -> bool:
        return self.task_effort is not None and self.effort_source != "none"

    @property
    def has_model_fit(self) -> bool:
        return self.model_fit is not None and len(self.model_fit) > 0

    def strongest_delta(self, *, reference_tier: int, strongest_tier: int) -> float | None:
        """Return ModelFit delta for strongest minus reference tier if available."""
        if not self.model_fit:
            return None
        if "strongest_vs_reference" in self.model_fit:
            return float(self.model_fit["strongest_vs_reference"])
        reference_key = f"tier{reference_tier}"
        strongest_key = f"tier{strongest_tier}"
        if reference_key not in self.model_fit or strongest_key not in self.model_fit:
            return None
        return float(self.model_fit[strongest_key]) - float(self.model_fit[reference_key])

    def to_metadata(self) -> dict:
        """Return a JSON-serialisable summary for trace/record observability."""
        return {
            "task_value": self.task_value,
            "task_effort": self.task_effort,
            "model_fit_source": self.model_fit_source,
            "value_source": self.value_source,
            "effort_source": self.effort_source,
            "has_model_fit": self.has_model_fit,
        }

"""Tier frontier calibration — determines whether early T3 access is warranted.

Reads the currently loaded MODEL_CATALOG and computes cost ratios and
progress deltas between the strongest tier and the reference tier (the
enterprise default — second-cheapest when ≥3 tiers, cheapest when only 2).

No ML, no hardcoded model names.  Purely based on tier positions, token
prices, and progress priors from the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TierFrontier:
    """Pre-run calibration: should BudgetFlow allow early strongest-tier access?

    The reference tier is the second-cheapest when the catalog has ≥3 tiers
    (the enterprise default tier, typically T2).  When only 2 tiers exist,
    the reference falls back to the cheapest.
    """

    reference_tier: int
    strongest_tier: int
    reference_display: str
    strongest_display: str
    strongest_input_ratio: float    # strongest / reference
    strongest_output_ratio: float   # strongest / reference
    strongest_progress_delta: dict[str, float]  # strongest - reference
    early_allow_strongest: bool
    reason: str

    @classmethod
    def from_catalog(cls) -> TierFrontier | None:
        """Build from the currently loaded MODEL_CATALOG.

        Returns None when the catalog has fewer than 2 tiers (no frontier to
        calibrate).
        """
        from .model_tiers import MODEL_CATALOG

        configs = MODEL_CATALOG.configs
        if len(configs) < 2:
            return None

        ordered = sorted(configs, key=lambda c: c.tier)
        strongest = ordered[-1]

        # Reference tier: second-cheapest when ≥3 tiers (enterprise default T2),
        # cheapest when only 2 tiers exist.
        if len(ordered) >= 3:
            reference = ordered[1]  # second-cheapest = enterprise default
        else:
            reference = ordered[0]  # cheapest (fallback for 2-tier catalogs)

        input_ratio = _safe_ratio(strongest.cost_per_input_token, reference.cost_per_input_token)
        output_ratio = _safe_ratio(strongest.cost_per_output_token, reference.cost_per_output_token)
        cost_ratio = max(input_ratio, output_ratio)

        progress_delta: dict[str, float] = {}
        strongest_not_weaker = True
        for stage_key in ("localization", "repair", "validation"):
            sp = strongest.progress_prior.get(stage_key, 0.0)
            rp = reference.progress_prior.get(stage_key, 0.0)
            delta = sp - rp
            progress_delta[stage_key] = delta
            if delta < 0:
                strongest_not_weaker = False

        early_allow = False
        reason_parts: list[str] = []

        # Rule 1: cost proximity — strongest must not be dramatically more
        # expensive than the reference tier.  Threshold: max(input_ratio,
        # output_ratio) < 1.8.
        if cost_ratio < 1.8:
            reason_parts.append(
                f"cost_ratio={cost_ratio:.2f}<1.8 "
                f"strongest_vs_reference_input={input_ratio:.2f}x_output={output_ratio:.2f}x"
            )
        else:
            reason_parts.append(
                f"cost_ratio={cost_ratio:.2f}>=1.8 strongest_too_expensive_vs_reference"
            )

        # Rule 2: capability — strongest progress priors must be >= reference
        # in every stage.
        if strongest_not_weaker:
            reason_parts.append("strongest_progress>=reference_all_stages")
        else:
            reason_parts.append("strongest_weaker_in_some_stage_vs_reference")

        if cost_ratio < 1.8 and strongest_not_weaker:
            early_allow = True

        reason = (
            f"early_allow={'yes' if early_allow else 'no'}; "
            + "; ".join(reason_parts)
        )

        return cls(
            reference_tier=reference.tier,
            strongest_tier=strongest.tier,
            reference_display=reference.display,
            strongest_display=strongest.display,
            strongest_input_ratio=input_ratio,
            strongest_output_ratio=output_ratio,
            strongest_progress_delta=progress_delta,
            early_allow_strongest=early_allow,
            reason=reason,
        )

    def max_tier_pressure_threshold(self) -> float:
        """Budget pressure at which the strongest tier is unconditionally allowed.

        When early_allow_strongest is True the cap starts at the strongest tier
        anyway, so this is only meaningful for the conservative path.
        """
        if self.early_allow_strongest:
            return 0.02  # nearly always allowed
        return 0.15  # conservative default

    def to_dict(self) -> dict:
        return {
            "reference_tier": self.reference_tier,
            "strongest_tier": self.strongest_tier,
            "reference_display": self.reference_display,
            "strongest_display": self.strongest_display,
            "strongest_input_ratio": round(self.strongest_input_ratio, 4),
            "strongest_output_ratio": round(self.strongest_output_ratio, 4),
            "strongest_progress_delta": {k: round(v, 4) for k, v in self.strongest_progress_delta.items()},
            "early_allow_strongest": self.early_allow_strongest,
            "reason": self.reason,
        }


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return float("inf")
    return numerator / denominator

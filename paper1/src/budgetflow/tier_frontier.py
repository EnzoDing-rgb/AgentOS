"""Tier frontier calibration — ModelFit-based advisory frontier scoring.

Uses catalog progress_priors as ModelFit signals to compute whether
strongest-tier access is warranted for a given (stage, value, effort, budget).
Replaces the old binary ``cost_ratio < 1.8`` hard gate with a continuous
frontier score that policies can use as a decision input.

No ML, no hardcoded model names.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

from .defaults import FRONTIER_DEFAULT_RUNWAY_TURNS

if TYPE_CHECKING:
    from .allocation import AllocationContext


@dataclass(frozen=True)
class TierFrontier:
    """Pre-run calibration: should BudgetFlow allow strongest-tier access?

    Progress priors from the model catalog are used as ModelFit signals.
    The frontier score combines cost ratio and progress delta into a single
    advisory metric — lower score means stronger T3 case.
    """

    reference_tier: int
    strongest_tier: int
    reference_display: str
    strongest_display: str
    strongest_input_ratio: float
    strongest_output_ratio: float
    strongest_progress_delta: dict[str, float]
    reference_runway_turns: int
    reason: str

    @classmethod
    def from_catalog(cls) -> TierFrontier | None:
        from .model_tiers import MODEL_CATALOG

        configs = MODEL_CATALOG.configs
        if len(configs) < 2:
            return None

        ordered = sorted(configs, key=lambda c: c.tier)
        strongest = ordered[-1]

        if len(ordered) >= 3:
            reference = ordered[1]
        else:
            reference = ordered[0]

        input_ratio = _safe_ratio(strongest.cost_per_input_token, reference.cost_per_input_token)
        output_ratio = _safe_ratio(strongest.cost_per_output_token, reference.cost_per_output_token)
        cost_ratio = max(input_ratio, output_ratio)

        progress_delta: dict[str, float] = {}
        for stage_key in ("localization", "repair", "validation"):
            sp = strongest.progress_prior.get(stage_key, 0.0)
            rp = reference.progress_prior.get(stage_key, 0.0)
            progress_delta[stage_key] = sp - rp
        reference_runway = getattr(reference, "max_turns", None) or FRONTIER_DEFAULT_RUNWAY_TURNS

        reason_parts = [
            f"cost_ratio={cost_ratio:.2f} "
            f"input={input_ratio:.2f}x_output={output_ratio:.2f}x",
            "progress_deltas={" + ", ".join(f"{k}: {v:+.3f}" for k, v in progress_delta.items()) + "}",
            f"reference_runway_turns={reference_runway}",
        ]
        reason = "; ".join(reason_parts)

        return cls(
            reference_tier=reference.tier,
            strongest_tier=strongest.tier,
            reference_display=reference.display,
            strongest_display=strongest.display,
            strongest_input_ratio=input_ratio,
            strongest_output_ratio=output_ratio,
            strongest_progress_delta=progress_delta,
            reference_runway_turns=reference_runway,
            reason=reason,
        )

    def frontier_score(
        self,
        stage: str,
        allocation: AllocationContext | None = None,
        budget_pressure: float = 0.0,
    ) -> float:
        """Advisory frontier score: lower = stronger T3 case.

        Combines cost ratio and ModelFit (progress delta) into a single
        continuous score.  Policies use this as a decision input, not a
        binary gate.

        *stage* is one of "localization", "repair", "validation".

        *allocation* provides TaskValue and ModelFit priors.  Higher task
        value amplifies the progress-delta benefit, making T3 more attractive
        for high-value tasks.

        *budget_pressure* (0..1) dampens T3 attractiveness when budget is
        tight.  At pressure=0 no dampening; at pressure=1 the cost ratio
        penalty is doubled.

        Score < 1.0: T3 effective cost is justified by expected value gain.
        Score 1.0–2.0: marginal, depends on budget headroom.
        Score > 2.0: T3 cost likely not justified by progress delta alone.
        """
        delta = self.strongest_progress_delta.get(stage, 0.0)
        cost_ratio = max(self.strongest_input_ratio, self.strongest_output_ratio)

        task_value = 1.0
        if allocation is not None:
            task_value = allocation.task_value
            if allocation.has_model_fit and allocation.model_fit:
                fit_delta = allocation.strongest_delta(
                    reference_tier=self.reference_tier,
                    strongest_tier=self.strongest_tier,
                )
                if fit_delta is not None and fit_delta > delta:
                    delta = fit_delta

        incremental_cost_ratio = max(
            max(self.strongest_input_ratio, self.strongest_output_ratio) - 1.0,
            0.0,
        )
        value_gain = max(delta, 0.0) * task_value * max(1, self.reference_runway_turns)
        if value_gain <= 0:
            return _finite_score(cost_ratio * (1.0 + budget_pressure), cost_ratio, budget_pressure)

        effective_incremental_cost = incremental_cost_ratio * (1.0 + budget_pressure * 0.5)
        return _finite_score(effective_incremental_cost / value_gain, cost_ratio, budget_pressure)

    def to_dict(self) -> dict:
        return {
            "reference_tier": self.reference_tier,
            "strongest_tier": self.strongest_tier,
            "reference_display": self.reference_display,
            "strongest_display": self.strongest_display,
            "strongest_input_ratio": round(self.strongest_input_ratio, 4),
            "strongest_output_ratio": round(self.strongest_output_ratio, 4),
            "strongest_progress_delta": {k: round(v, 4) for k, v in self.strongest_progress_delta.items()},
            "reference_runway_turns": self.reference_runway_turns,
            "reason": self.reason,
        }


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return float("inf")
    return numerator / denominator


def _finite_score(score: float, cost_ratio: float, budget_pressure: float) -> float:
    """Keep bad catalog edits from leaking NaN/inf into traces."""
    if math.isfinite(score):
        return score
    fallback = cost_ratio * (1.0 + budget_pressure)
    if math.isfinite(fallback):
        return fallback
    return 1_000_000.0

"""Task-level T2/T3 routing decision — single shared entry point.

BudgetFlow Runtime (adapter/strategies.py) and the Budget Regime Compiler
(budget_binding.py projection) call the same function so readiness projection
and actual runtime decisions cannot fork.

The compiler must not assign model tiers. This module provides a deterministic
projection formula that mirrors runtime behavior for no-paid readiness.
"""

from __future__ import annotations

from .defaults import (
    MARGINAL_YIELD_PER_DOLLAR_THRESHOLD,
    TASK_START_COLD_FRONTIER_EFFORT_THRESHOLD,
    TASK_START_COLD_FRONTIER_EFFORT_TOLERANCE,
    TASK_START_DECISIVE_FIT_GAIN,
    TASK_START_HIGH_EFFORT_THRESHOLD,
    TASK_START_MIN_VALUE_FOR_DECISIVE_FIT,
    TASK_START_PAID_UPGRADE_MIN_FIT_GAIN,
    TASK_START_PRESSURE_THRESHOLD_MULTIPLIER,
    TASK_START_STRONGEST_MIN_BUDGET_COVERAGE,
    TASK_START_T3_ACCEPTANCE_MARGIN,
    TASK_START_VALUE_RATIO_GATE,
    task_start_effort_multiplier,
    task_start_t3_acceptance_threshold,
)


def task_start_tier_decision(
    *,
    task_value: float,
    task_effort: float,
    tier2_fit: float,
    tier3_fit: float,
    tier2_per_turn_cost: float,
    tier3_per_turn_cost: float,
    budget_pressure: float,
    task_budget: float | None,
    median_task_value: float = 1.0,
    has_trusted_model_fit: bool = False,
    is_cold_start: bool = False,
    reference_runway_turns: float | None = None,
) -> tuple[int, str, dict[str, float]]:
    """Return ``(selected_tier, reason, scores)`` for one task-start decision.

    All inputs are raw values. Callers extract them from their respective data
    sources (RoutingContext, value_features, catalog, calibration evidence).
    """

    # ── normalise inputs ────────────────────────────────────────────────
    effort = max(1.0, float(task_effort))
    value = float(task_value)
    median = max(0.001, float(median_task_value))
    pressure = max(0.0, min(1.5, float(budget_pressure)))
    t2_fit = max(0.001, float(tier2_fit))
    t3_fit = max(0.001, float(tier3_fit))
    fit_gain = max(0.0, t3_fit - t2_fit)

    # ── expected total cost per tier ─────────────────────────────────────
    t2_expected_cost = effort / t2_fit * tier2_per_turn_cost
    t3_expected_cost = effort / t3_fit * tier3_per_turn_cost
    reference_cost = max(t2_expected_cost, 0.000001)
    strongest_cost = max(t3_expected_cost, 0.000001)

    t2_unit_cost = reference_cost / effort
    t3_unit_cost = strongest_cost / effort
    extra_unit_cost = max(0.0, t3_unit_cost - t2_unit_cost)

    # ── budget gating ────────────────────────────────────────────────────
    budget_value = (
        float(task_budget)
        if task_budget is not None and task_budget > 0
        else None
    )
    budget_allows = (
        strongest_cost <= budget_value
        if budget_value is not None
        else True
    )
    budget_coverage = _budget_coverage(budget_value, strongest_cost)
    budget_soft_allows = (
        budget_allows
        or budget_value is None
        or budget_coverage >= TASK_START_STRONGEST_MIN_BUDGET_COVERAGE
    )

    # ── marginal yield ───────────────────────────────────────────────────
    effort_mult = task_start_effort_multiplier(effort, reference_runway_turns=reference_runway_turns)
    if strongest_cost <= reference_cost:
        marginal_yield = float("inf") if fit_gain > 0 else 0.0
    else:
        marginal_yield = value * fit_gain * effort_mult / max(extra_unit_cost, 0.000001)

    # ── threshold ────────────────────────────────────────────────────────
    threshold = (
        MARGINAL_YIELD_PER_DOLLAR_THRESHOLD
        * median
        * (1.0 + TASK_START_PRESSURE_THRESHOLD_MULTIPLIER * pressure)
    )
    acceptance = task_start_t3_acceptance_threshold(threshold)
    value_ratio = value / median

    # ── gates ────────────────────────────────────────────────────────────
    metadata_gate = (
        value_ratio >= TASK_START_VALUE_RATIO_GATE
        or (effort >= TASK_START_HIGH_EFFORT_THRESHOLD and value >= median)
    )
    decisive_fit_gate = (
        fit_gain >= TASK_START_DECISIVE_FIT_GAIN
        and value >= TASK_START_MIN_VALUE_FOR_DECISIVE_FIT
    )
    paid_upgrade_candidate = (
        strongest_cost <= reference_cost
        or decisive_fit_gate
        or (fit_gain >= TASK_START_PAID_UPGRADE_MIN_FIT_GAIN and metadata_gate)
    )

    # ── marginal yield path ──────────────────────────────────────────────
    if (
        budget_soft_allows
        and has_trusted_model_fit
        and fit_gain > 0
        and paid_upgrade_candidate
        and marginal_yield >= acceptance
    ):
        return 3, "marginal_yield_per_dollar", _scores(
            value=value,
            effort=effort,
            value_ratio=value_ratio,
            budget_pressure=pressure,
            budget_allows=budget_allows,
            has_trusted_model_fit=has_trusted_model_fit,
            t2_fit=t2_fit,
            t3_fit=t3_fit,
            fit_gain=fit_gain,
            reference_cost=reference_cost,
            strongest_cost=strongest_cost,
            t2_unit_cost=t2_unit_cost,
            t3_unit_cost=t3_unit_cost,
            extra_unit_cost=extra_unit_cost,
            effort_multiplier=effort_mult,
            marginal_yield=marginal_yield,
            threshold=threshold,
            acceptance_threshold=acceptance,
            paid_upgrade_candidate=paid_upgrade_candidate,
            decisive_fit_gate=decisive_fit_gate,
            metadata_gate=metadata_gate,
            task_budget=budget_value,
            headroom=_headroom(budget_value, strongest_cost),
            headroom_fraction=_headroom_fraction(budget_value, strongest_cost),
            budget_coverage=budget_coverage,
            budget_soft_allows=budget_soft_allows,
            rule="marginal_expected_value_per_dollar",
        )

    # ── uncertain frontier probe (cold start) ────────────────────────────
    if _uncertain_probe(
        is_cold_start=is_cold_start,
        budget_allows=budget_allows,
        budget_soft_allows=budget_soft_allows,
        budget_coverage=budget_coverage,
        headroom_fraction=_headroom_fraction(budget_value, strongest_cost),
        pressure=pressure,
        value_ratio=value_ratio,
        fit_gain=fit_gain,
        paid_upgrade_candidate=paid_upgrade_candidate,
        marginal_yield=marginal_yield,
        acceptance=acceptance,
        effort=effort,
        value=value,
        median=median,
    ):
        return 3, "uncertain_frontier_probe", _scores(
            value=value,
            effort=effort,
            value_ratio=value_ratio,
            budget_pressure=pressure,
            budget_allows=budget_allows,
            has_trusted_model_fit=has_trusted_model_fit,
            t2_fit=t2_fit,
            t3_fit=t3_fit,
            fit_gain=fit_gain,
            reference_cost=reference_cost,
            strongest_cost=strongest_cost,
            t2_unit_cost=t2_unit_cost,
            t3_unit_cost=t3_unit_cost,
            extra_unit_cost=extra_unit_cost,
            effort_multiplier=effort_mult,
            marginal_yield=marginal_yield,
            threshold=threshold,
            acceptance_threshold=acceptance,
            paid_upgrade_candidate=paid_upgrade_candidate,
            decisive_fit_gate=decisive_fit_gate,
            metadata_gate=metadata_gate,
            task_budget=budget_value,
            headroom=_headroom(budget_value, strongest_cost),
            headroom_fraction=_headroom_fraction(budget_value, strongest_cost),
            budget_coverage=budget_coverage,
            budget_soft_allows=budget_soft_allows,
            rule="uncertain_frontier_probe",
        )

    # ── default: reference tier ──────────────────────────────────────────
    return 2, "reference_frontier", _scores(
        value=value,
        effort=effort,
        value_ratio=value_ratio,
        budget_pressure=pressure,
        budget_allows=budget_allows,
        has_trusted_model_fit=has_trusted_model_fit,
        t2_fit=t2_fit,
        t3_fit=t3_fit,
        fit_gain=fit_gain,
        reference_cost=reference_cost,
        strongest_cost=strongest_cost,
        t2_unit_cost=t2_unit_cost,
        t3_unit_cost=t3_unit_cost,
        extra_unit_cost=extra_unit_cost,
        effort_multiplier=effort_mult,
        marginal_yield=marginal_yield,
        threshold=threshold,
        acceptance_threshold=acceptance,
        paid_upgrade_candidate=paid_upgrade_candidate,
        decisive_fit_gate=decisive_fit_gate,
        metadata_gate=metadata_gate,
        task_budget=budget_value,
        headroom=_headroom(budget_value, strongest_cost),
        headroom_fraction=_headroom_fraction(budget_value, strongest_cost),
        budget_coverage=budget_coverage,
        budget_soft_allows=budget_soft_allows,
        rule="reference_frontier",
    )


# ── helpers ────────────────────────────────────────────────────────────────


def _headroom(task_budget: float | None, strongest_cost: float) -> float:
    if task_budget is None or task_budget <= 0:
        return 0.0
    return max(0.0, task_budget - strongest_cost)


def _headroom_fraction(task_budget: float | None, strongest_cost: float) -> float:
    if task_budget is None or task_budget <= 0:
        return 0.0
    return _headroom(task_budget, strongest_cost) / max(task_budget, 0.000001)


def _budget_coverage(task_budget: float | None, strongest_cost: float) -> float:
    if task_budget is None:
        return 1.0
    if task_budget <= 0:
        return 0.0
    return min(1.0, float(task_budget) / max(strongest_cost, 0.000001))


def _uncertain_probe(
    *,
    is_cold_start: bool,
    budget_allows: bool,
    budget_soft_allows: bool,
    budget_coverage: float,
    headroom_fraction: float,
    pressure: float,
    value_ratio: float,
    fit_gain: float,
    paid_upgrade_candidate: bool,
    marginal_yield: float,
    acceptance: float,
    effort: float,
    value: float,
    median: float,
) -> bool:
    if not is_cold_start:
        return False
    if not budget_soft_allows:
        return False
    if not budget_allows and not (
        paid_upgrade_candidate
        and fit_gain > 0
        and marginal_yield >= acceptance
        and budget_coverage >= TASK_START_STRONGEST_MIN_BUDGET_COVERAGE
    ):
        return False
    if budget_allows and headroom_fraction < 0.10:
        return False
    if pressure > 0.80:
        return False
    cold_effort_floor = (
        TASK_START_COLD_FRONTIER_EFFORT_THRESHOLD
        * TASK_START_COLD_FRONTIER_EFFORT_TOLERANCE
    )
    return (
        value_ratio >= TASK_START_VALUE_RATIO_GATE
        or (effort >= cold_effort_floor and value >= median)
        or (effort >= TASK_START_HIGH_EFFORT_THRESHOLD and value >= median)
    )


def _scores(
    *,
    value: float,
    effort: float,
    value_ratio: float,
    budget_pressure: float,
    budget_allows: bool,
    has_trusted_model_fit: bool,
    t2_fit: float,
    t3_fit: float,
    fit_gain: float,
    reference_cost: float,
    strongest_cost: float,
    t2_unit_cost: float,
    t3_unit_cost: float,
    extra_unit_cost: float,
    effort_multiplier: float,
    marginal_yield: float,
    threshold: float,
    acceptance_threshold: float,
    paid_upgrade_candidate: bool,
    decisive_fit_gate: bool,
    metadata_gate: bool,
    task_budget: float | None,
    headroom: float,
    headroom_fraction: float,
    budget_coverage: float,
    budget_soft_allows: bool,
    rule: str,
) -> dict[str, float]:
    return {
        "task_value": value,
        "task_effort": effort,
        "value_ratio": round(value_ratio, 6),
        "budget_pressure": budget_pressure,
        "budget_allows_strongest": 1.0 if budget_allows else 0.0,
        "budget_soft_allows_strongest": 1.0 if budget_soft_allows else 0.0,
        "strongest_budget_coverage": budget_coverage,
        "strongest_min_budget_coverage": TASK_START_STRONGEST_MIN_BUDGET_COVERAGE,
        "has_trusted_model_fit": 1.0 if has_trusted_model_fit else 0.0,
        "reference_fit": t2_fit,
        "strongest_fit": t3_fit,
        "fit_gain": fit_gain,
        "min_fit_gain_for_paid_upgrade": TASK_START_PAID_UPGRADE_MIN_FIT_GAIN,
        "decisive_fit_gain": TASK_START_DECISIVE_FIT_GAIN,
        "value_ratio_gate": TASK_START_VALUE_RATIO_GATE,
        "paid_upgrade_candidate": 1.0 if paid_upgrade_candidate else 0.0,
        "decisive_fit_gate": 1.0 if decisive_fit_gate else 0.0,
        "criticality_or_effort_gate": 1.0 if metadata_gate else 0.0,
        "reference_expected_total_cost": reference_cost,
        "strongest_expected_total_cost": strongest_cost,
        "extra_expected_cost": max(0.0, strongest_cost - reference_cost),
        "reference_unit_cost": t2_unit_cost,
        "strongest_unit_cost": t3_unit_cost,
        "extra_unit_cost": extra_unit_cost,
        "effort_multiplier": effort_multiplier,
        "marginal_yield_per_dollar": marginal_yield if marginal_yield != float("inf") else 999999.0,
        "budget_pressure_threshold": threshold,
        "t3_acceptance_threshold": acceptance_threshold,
        "t3_acceptance_margin": TASK_START_T3_ACCEPTANCE_MARGIN,
        "task_budget": float(task_budget) if task_budget is not None else 0.0,
        "task_budget_headroom": headroom,
        "task_budget_headroom_fraction": headroom_fraction,
        "rule": rule,
    }

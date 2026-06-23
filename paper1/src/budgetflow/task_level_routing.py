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
    TASK_START_CRITICAL_VALUE_RATIO_GATE,
    TASK_START_DECISIVE_FIT_GAIN,
    TASK_START_HIGH_EFFORT_THRESHOLD,
    TASK_START_HIGH_PRESSURE_PROBE_MARGIN,
    TASK_START_MIN_VALUE_FOR_DECISIVE_FIT,
    TASK_START_PAID_UPGRADE_MIN_FIT_GAIN,
    TASK_START_PRESSURE_THRESHOLD_MULTIPLIER,
    TASK_START_STRONGEST_MIN_BUDGET_COVERAGE,
    TASK_START_STRONGEST_MIN_PROBE_TURNS,
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
    planned_task_budget: float | None = None,
    effective_task_budget: float | None = None,
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
    planned_budget_value = _non_negative_or_none(planned_task_budget)
    effective_budget_value = _non_negative_or_none(
        effective_task_budget if effective_task_budget is not None else planned_budget_value
    )
    affordability_budget = planned_budget_value
    budget_allows = (
        strongest_cost <= affordability_budget
        if affordability_budget is not None
        else True
    )
    strongest_probe_cost = max(0.000001, float(tier3_per_turn_cost)) * max(
        1.0,
        float(TASK_START_STRONGEST_MIN_PROBE_TURNS),
    )
    budget_allows_probe = (
        strongest_probe_cost <= affordability_budget
        if affordability_budget is not None
        else True
    )
    budget_coverage = _budget_coverage(affordability_budget, strongest_cost)
    effective_budget_coverage = _budget_coverage(effective_budget_value, strongest_cost)
    coverage_soft_allows = (
        budget_allows
        or affordability_budget is None
        or budget_coverage >= TASK_START_STRONGEST_MIN_BUDGET_COVERAGE
    )
    has_positive_runway = effective_budget_value is None or effective_budget_value > 0.0

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
    marginal_candidate = (
        has_trusted_model_fit
        and fit_gain > 0
        and paid_upgrade_candidate
        and marginal_yield >= acceptance
    )
    decisive_marginal_override = (
        not coverage_soft_allows
        and has_positive_runway
        and budget_allows_probe
        and marginal_candidate
        and decisive_fit_gate
        and metadata_gate
        and pressure <= 0.50
        and (
            marginal_yield >= acceptance * 3.0
            or strongest_cost <= reference_cost
        )
    )
    critical_value_probe = (
        not coverage_soft_allows
        and has_positive_runway
        and budget_allows_probe
        and value_ratio >= TASK_START_CRITICAL_VALUE_RATIO_GATE
        and paid_upgrade_candidate
        and fit_gain >= TASK_START_PAID_UPGRADE_MIN_FIT_GAIN
        and marginal_yield >= acceptance
    )
    high_pressure_efficiency_probe = (
        is_cold_start
        and pressure > 0.80
        and has_positive_runway
        and budget_allows_probe
        and budget_coverage >= TASK_START_STRONGEST_MIN_BUDGET_COVERAGE
        and paid_upgrade_candidate
        and metadata_gate
        and fit_gain >= TASK_START_PAID_UPGRADE_MIN_FIT_GAIN
        and marginal_yield >= acceptance * TASK_START_HIGH_PRESSURE_PROBE_MARGIN
    )
    budget_soft_allows = (
        has_positive_runway
        and (
            coverage_soft_allows
            or decisive_marginal_override
            or critical_value_probe
            or high_pressure_efficiency_probe
        )
    )
    headroom = _headroom(affordability_budget, strongest_cost)
    headroom_fraction = _headroom_fraction(affordability_budget, strongest_cost)

    def scores(rule: str) -> dict[str, float]:
        return _scores(
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
            planned_task_budget=planned_budget_value,
            effective_task_budget=effective_budget_value,
            headroom=headroom,
            headroom_fraction=headroom_fraction,
            budget_coverage=budget_coverage,
            effective_budget_coverage=effective_budget_coverage,
            budget_soft_allows=budget_soft_allows,
            decisive_marginal_budget_override=decisive_marginal_override,
            critical_value_probe=critical_value_probe,
            high_pressure_efficiency_probe=high_pressure_efficiency_probe,
            strongest_probe_cost=strongest_probe_cost,
            budget_allows_probe=budget_allows_probe,
            rule=rule,
        )

    # ── marginal yield path ──────────────────────────────────────────────
    if (
        budget_soft_allows
        and marginal_candidate
    ):
        return 3, (
            "decisive_marginal_yield_budget_override"
            if decisive_marginal_override
            else "marginal_yield_per_dollar"
        ), scores("marginal_expected_value_per_dollar")

    # ── critical value probe ─────────────────────────────────────────────
    if critical_value_probe:
        return 3, "critical_value_probe", scores("critical_value_probe")

    # ── uncertain frontier probe (cold start) ────────────────────────────
    if high_pressure_efficiency_probe or _uncertain_probe(
        is_cold_start=is_cold_start,
        budget_allows=budget_allows,
        budget_soft_allows=budget_soft_allows,
        budget_coverage=budget_coverage,
        headroom_fraction=_headroom_fraction(affordability_budget, strongest_cost),
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
        return 3, (
            "high_pressure_efficiency_probe"
            if high_pressure_efficiency_probe
            else "uncertain_frontier_probe"
        ), scores("uncertain_frontier_probe")

    # ── default: reference tier ──────────────────────────────────────────
    return 2, "reference_frontier", scores("reference_frontier")


# ── helpers ────────────────────────────────────────────────────────────────


def _non_negative_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    if float(value) < 0:
        return None
    return float(value)


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
    headroom: float,
    headroom_fraction: float,
    budget_coverage: float,
    effective_budget_coverage: float,
    budget_soft_allows: bool,
    rule: str,
    planned_task_budget: float | None,
    effective_task_budget: float | None,
    decisive_marginal_budget_override: bool = False,
    critical_value_probe: bool = False,
    high_pressure_efficiency_probe: bool = False,
    strongest_probe_cost: float = 0.0,
    budget_allows_probe: bool = False,
) -> dict[str, float]:
    return {
        "task_value": value,
        "task_effort": effort,
        "value_ratio": round(value_ratio, 6),
        "budget_pressure": budget_pressure,
        "budget_allows_strongest": 1.0 if budget_allows else 0.0,
        "budget_soft_allows_strongest": 1.0 if budget_soft_allows else 0.0,
        "decisive_marginal_budget_override": (
            1.0 if decisive_marginal_budget_override else 0.0
        ),
        "critical_value_probe": 1.0 if critical_value_probe else 0.0,
        "high_pressure_efficiency_probe": 1.0 if high_pressure_efficiency_probe else 0.0,
        "high_pressure_probe_margin": TASK_START_HIGH_PRESSURE_PROBE_MARGIN,
        "critical_value_ratio_gate": TASK_START_CRITICAL_VALUE_RATIO_GATE,
        "budget_allows_strongest_probe": 1.0 if budget_allows_probe else 0.0,
        "strongest_probe_cost": strongest_probe_cost,
        "strongest_min_probe_turns": TASK_START_STRONGEST_MIN_PROBE_TURNS,
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
        "planned_task_budget": float(planned_task_budget) if planned_task_budget is not None else 0.0,
        "effective_task_budget": float(effective_task_budget) if effective_task_budget is not None else 0.0,
        "task_budget_headroom": headroom,
        "task_budget_headroom_fraction": headroom_fraction,
        "effective_budget_coverage": effective_budget_coverage,
        "rule": rule,
    }

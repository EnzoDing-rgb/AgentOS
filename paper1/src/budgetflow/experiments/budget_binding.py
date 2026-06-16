"""Budget binding calibrator — generates auditable budget_plan.json from code.

Reads historical diagnostic JSONL, re-normalizes costs with the active model
catalog, and projects spend for the target task set.  Produces a budget plan
with a GO/NO-GO decision that paid-readiness gates on.

No ML, no outcome leakage.  Historical data is used only for token/tier
proportions; costs are always re-priced with the current catalog.
"""

from __future__ import annotations

import json
import math
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from budgetflow.experiments.compare_config import load_strategy_set, paper_mainline_strategy_names

from ..model_tiers import MODEL_CATALOG, catalog_path, catalog_revision, catalog_source_info, init_catalog


# Cold-start pressure posture for paper-mainline strategies.  Frozen caps are
# pre-registered pressure anchors, not empirical expected costs.  These
# multipliers describe the intended initial pressure shape before clean Cost
# Memory exists; clean current-schema rows supersede them strategy by strategy.
_COLD_START_PRESSURE_PRIOR_MULTIPLIERS: dict[str, float] = {
    "bare_t2_baseline": 0.55,
    "bare_t3_baseline": 1.05,
    "enterprise_router_baseline": 0.76,
    "budgetflow_same_enterprise_router": 0.76,
    "budgetflow_task_level": 0.85,
    "budgetflow_segment": 0.90,
}


@dataclass
class BudgetBindingPlan:
    """Code-generated budget plan for a compare run."""

    hard_cap_usd: float
    source: str = "budget_binding_calibrator"
    generation_mode: str = "frozen_plan_cap_sum"
    target_projected_utilization: float | None = None
    catalog_revision: str = ""
    catalog_path: str = ""
    catalog_content_hash: str = ""
    historical_source: str = ""
    task_ids: list[str] = field(default_factory=list)
    strategy_names: list[str] = field(default_factory=list)
    projected_spend_by_strategy: dict[str, float] = field(default_factory=dict)
    projected_utilization_by_strategy: dict[str, float] = field(default_factory=dict)
    min_viable_budget: float = 0.0
    loose_budget_threshold: float = 0.0
    tight_budget_threshold: float = 0.0
    decision: str = "PASS"
    reasons: list[str] = field(default_factory=list)
    override_reason: str = ""
    pressure_contract: dict[str, Any] = field(default_factory=dict)
    projection_confidence: str = "unvalidated"
    calibration_error: dict[str, float] = field(default_factory=dict)
    calibration_excluded: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict = {
            "hard_cap_usd": round(self.hard_cap_usd, 4),
            "source": self.source,
            "generation_mode": self.generation_mode,
            "catalog_revision": self.catalog_revision,
            "catalog_path": self.catalog_path,
            "catalog_content_hash": self.catalog_content_hash,
            "historical_source": self.historical_source,
            "task_ids": self.task_ids,
            "strategy_names": self.strategy_names,
            "projected_spend_by_strategy": {
                k: round(v, 4) for k, v in self.projected_spend_by_strategy.items()
            },
            "projected_utilization_by_strategy": {
                k: round(v, 4) for k, v in self.projected_utilization_by_strategy.items()
            },
            "min_viable_budget": round(self.min_viable_budget, 4),
            "loose_budget_threshold": round(self.loose_budget_threshold, 4),
            "tight_budget_threshold": round(self.tight_budget_threshold, 4),
            "decision": self.decision,
            "reasons": self.reasons,
            "pressure_contract": self.pressure_contract,
            "projection_confidence": self.projection_confidence,
        }
        if self.target_projected_utilization is not None:
            d["target_projected_utilization"] = round(self.target_projected_utilization, 4)
        if self.override_reason:
            d["override_reason"] = self.override_reason
        if self.calibration_error:
            d["calibration_error"] = {k: round(v, 4) for k, v in self.calibration_error.items()}
        if self.calibration_excluded:
            d["calibration_excluded"] = dict(self.calibration_excluded)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> BudgetBindingPlan:
        return cls(
            hard_cap_usd=d["hard_cap_usd"],
            source=d.get("source", "budget_binding_calibrator"),
            generation_mode=d["generation_mode"],
            target_projected_utilization=d.get("target_projected_utilization"),
            catalog_revision=d.get("catalog_revision", ""),
            catalog_path=d.get("catalog_path", ""),
            catalog_content_hash=d.get("catalog_content_hash", ""),
            historical_source=d.get("historical_source", ""),
            task_ids=d.get("task_ids", []),
            strategy_names=d.get("strategy_names", []),
            projected_spend_by_strategy=d.get("projected_spend_by_strategy", {}),
            projected_utilization_by_strategy=d.get("projected_utilization_by_strategy", {}),
            min_viable_budget=d.get("min_viable_budget", 0.0),
            loose_budget_threshold=d.get("loose_budget_threshold", 0.0),
            tight_budget_threshold=d.get("tight_budget_threshold", 0.0),
            decision=d.get("decision", "PASS"),
            reasons=d.get("reasons", []),
            override_reason=d.get("override_reason", ""),
            pressure_contract=d.get("pressure_contract", {}),
            projection_confidence=d.get("projection_confidence", "unvalidated"),
            calibration_error=d.get("calibration_error", {}),
            calibration_excluded=d.get("calibration_excluded", {}),
        )


@dataclass
class CalibrationAudit:
    """Post-run comparison of projected vs actual spend."""

    strategy_errors: dict[str, dict] = field(default_factory=dict)
    overall_mape: float = 0.0
    max_error_strategy: str = ""
    max_error_pct: float = 0.0
    projection_confidence: str = "unvalidated"
    recommendations: list[str] = field(default_factory=list)
    generation_mode: str = ""
    target_utilization: float | None = None
    actual_utilization_by_strategy: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_errors": self.strategy_errors,
            "overall_mape": round(self.overall_mape, 4),
            "max_error_strategy": self.max_error_strategy,
            "max_error_pct": round(self.max_error_pct, 4),
            "projection_confidence": self.projection_confidence,
            "recommendations": self.recommendations,
            "generation_mode": self.generation_mode,
            "target_utilization": self.target_utilization,
            "actual_utilization_by_strategy": {
                k: round(v, 4) for k, v in self.actual_utilization_by_strategy.items()
            },
        }


# ── Public API ────────────────────────────────────────────────────────────


def calibrate_budget(
    task_ids: list[str],
    *,
    historical_jsonl: Path | None = None,
    frozen_plan_path: Path | None = None,
    value_matrix_path: Path | None = None,
    strategies: tuple[str, ...] | None = None,
    output_path: Path | None = None,
    override_reason: str = "",
    target_utilization: float | None = None,
    prior_calibration: CalibrationAudit | None = None,
) -> BudgetBindingPlan:
    """Generate a budget binding plan from historical data and current catalog.

    Two modes:

    * **frozen_plan_cap_sum** (default when *target_utilization* is None):
      ``hard_cap`` = sum of frozen plan per-task ``base_cap`` values.
      Suitable for mechanism-diagnostic runs whose budget is bound to a
      pre-registered static router plan.

    * **target_utilization** (when set, e.g. 0.80):
      ``hard_cap`` = p75(projected spend) / *target_utilization*.
      The reference is the 75th percentile of the configured paper-mainline
      strategy set — not any single BudgetFlow policy's spend.  Cheaper
      strategies have more headroom; bare T3 may be at or above cap.  The
      pressure shape is an audit output, never a generation rule.

    *prior_calibration* feeds projection confidence into the readiness gate.
    When a prior calibration audit shows high projection error, the plan
    decision may be downgraded to WARNING or BLOCK.
    """
    if target_utilization is not None and not (0.0 < target_utilization <= 1.0):
        raise ValueError(f"target_utilization must be in (0, 1], got {target_utilization}")
    if strategies is None:
        strategies = paper_mainline_strategy_names()

    generation_mode = "target_utilization" if target_utilization is not None else "frozen_plan_cap_sum"

    catalog_info = catalog_source_info()
    plan = BudgetBindingPlan(
        hard_cap_usd=0.0,
        generation_mode=generation_mode,
        target_projected_utilization=target_utilization,
        catalog_revision=str(catalog_info.get("catalog_revision") or catalog_revision()),
        catalog_path=str(
            catalog_info.get("catalog_path")
            or (str(catalog_path()) if catalog_path() else "python_fallback")
        ),
        catalog_content_hash=str(catalog_info.get("catalog_content_hash") or ""),
        historical_source=str(historical_jsonl) if historical_jsonl else "bootstrap_estimate",
        task_ids=list(task_ids),
        strategy_names=list(strategies),
    )

    # ── Load historical per-strategy per-task costs ──────────────────────
    historical: dict[str, dict[str, float]] = {}  # strategy -> {task_id -> cost}
    calibration_excluded: dict[str, int] = {}
    if historical_jsonl and historical_jsonl.exists():
        historical, calibration_excluded = _load_historical_costs(historical_jsonl)
        if calibration_excluded:
            plan.calibration_excluded = calibration_excluded
            total_excluded = sum(calibration_excluded.values())
            plan.reasons.append(
                f"calibration:excluded {total_excluded} contaminated rows: "
                + ", ".join(f"{k}={v}" for k, v in sorted(calibration_excluded.items()))
            )

    # ── Compute T3 price multiplier for re-normalization ────────────────
    t3_multiplier = _t3_price_multiplier()

    # ── Load frozen plan caps for reference ─────────────────────────────
    frozen_caps: dict[str, float] = {}
    preferred_models: dict[str, str] = {}
    if frozen_plan_path and frozen_plan_path.exists():
        frozen_caps = _load_frozen_caps(frozen_plan_path)
        preferred_models = _load_frozen_preferred_models(frozen_plan_path)
        if not historical_jsonl:
            plan.historical_source = f"cold_start_pressure_prior:frozen_plan={frozen_plan_path}"
            plan.reasons.append(
                "projection_basis: cold_start_pressure_prior from frozen caps; "
                "frozen caps are pressure anchors, not empirical expected-cost observations"
            )

    # ── Estimate zero-history tasks from value matrix ────────────────────
    value_features: dict[str, dict] = {}
    if value_matrix_path and value_matrix_path.exists():
        value_features = _load_value_features(value_matrix_path)

    # ── Effective-cost calibration per strategy ─────────────────────────
    # Compute cost-per-effort-unit from clean historical rows to account for
    # turn-efficiency differences (T3 may be cheaper than T2 despite higher
    # token prices, because it completes tasks in fewer turns).
    strategy_cost_per_effort: dict[str, float] = {}
    strategy_cal_n: dict[str, int] = {}
    for strategy in strategies:
        costs: list[float] = []
        for tid in task_ids:
            hist_cost = historical.get(strategy, {}).get(tid)
            if hist_cost is not None and hist_cost > 0:
                feat = value_features.get(tid, {})
                effort = feat.get("bootstrap_difficulty", 30.0) if feat else 30.0
                if effort > 0:
                    costs.append(hist_cost / effort)
        if costs:
            strategy_cost_per_effort[strategy] = sorted(costs)[len(costs) // 2]
            strategy_cal_n[strategy] = len(costs)

    # ── Project spend per strategy ──────────────────────────────────────
    projected: dict[str, float] = {}
    for strategy in strategies:
        total = 0.0
        cpe = strategy_cost_per_effort.get(strategy)
        for tid in task_ids:
            hist_cost = historical.get(strategy, {}).get(tid)
            if hist_cost is not None:
                # Historical cost with catalog-based re-normalization
                t3_share = _estimate_t3_cost_share(strategy, tid, historical, preferred_models=preferred_models)
                normalized = hist_cost * (1.0 + t3_share * (t3_multiplier - 1.0))
                total += normalized
            elif cpe is not None:
                # Cost-per-effort calibration: use observed efficiency
                feat = value_features.get(tid, {})
                effort = feat.get("bootstrap_difficulty", 30.0) if feat else 30.0
                total += effort * cpe
            else:
                total += _bootstrap_cost_estimate(
                    tid, strategy, value_features, historical, t3_multiplier, frozen_caps=frozen_caps
                )
        projected[strategy] = total

    plan.projected_spend_by_strategy = projected

    # Report per-strategy calibration confidence
    for strategy in strategies:
        cal_n = strategy_cal_n.get(strategy, 0)
        if cal_n >= 5:
            plan.reasons.append(
                f"calibration:{strategy} n={cal_n} cost_per_effort={strategy_cost_per_effort.get(strategy, 0):.6f}"
            )
        elif cal_n > 0:
            plan.reasons.append(
                f"calibration:{strategy} n={cal_n} (low sample, treat projection as advisory)"
            )
        else:
            cold_start_source = "cold_start_pressure_prior" if frozen_caps else "bootstrap_estimate"
            plan.reasons.append(
                f"calibration:{strategy} n=0 (no historical data, projection uses {cold_start_source})"
            )

    plan.min_viable_budget = max(projected.values()) if projected else 0.0
    frozen_cap_sum = sum(frozen_caps.get(tid, 0.0) for tid in task_ids)

    plan.loose_budget_threshold = plan.min_viable_budget * 2.0
    plan.tight_budget_threshold = plan.min_viable_budget

    # ── Decision logic ──────────────────────────────────────────────────

    if target_utilization is not None:
        # ── target_utilization mode ──────────────────────────────────
        ref_spend = _distribution_p75(list(projected.values()))
        plan.reasons.append(
            f"reference_rule: strategy_set_p75_projected_spend = ${ref_spend:.4f}"
        )

        if ref_spend <= 0:
            plan.hard_cap_usd = frozen_cap_sum if frozen_cap_sum > 0 else 1.0
            plan.decision = "BLOCK"
            plan.reasons.append("no projected spend data; cannot compute p75 reference")
        else:
            plan.hard_cap_usd = ref_spend / target_utilization
            plan.reasons.append(
                f"hard_cap = p75_ref(${ref_spend:.4f}) / "
                f"target_utilization({target_utilization}) = ${plan.hard_cap_usd:.4f}"
            )

        for strategy in strategies:
            spend = projected.get(strategy, 0.0)
            plan.projected_utilization_by_strategy[strategy] = (
                min(spend / plan.hard_cap_usd, 1.0) if plan.hard_cap_usd > 0 else 0.0
            )

        # ── Pressure contract (formalized audit output) ──────────────
        _build_pressure_contract(plan, strategies)

        # Tight-budget warnings for strategies that exceed hard cap
        for strategy in strategies:
            spend = projected.get(strategy, 0.0)
            if spend > plan.hard_cap_usd * 1.05:
                plan.reasons.append(
                    f"tight_budget_warning: {strategy} projected spend "
                    f"${spend:.2f} > hard_cap ${plan.hard_cap_usd:.2f} "
                    f"({spend / plan.hard_cap_usd:.1%} utilization) — "
                    f"strategy may not complete within shared budget"
                )

        if plan.decision != "BLOCK":
            max_util = max(plan.projected_utilization_by_strategy.values()) if plan.projected_utilization_by_strategy else 0.0
            plan.reasons.append(
                f"decision=PASS: hard_cap=${plan.hard_cap_usd:.2f} from "
                f"p75_ref / {target_utilization}, max projected utilization "
                f"{max_util:.1%}"
            )

    else:
        # ── frozen_plan_cap_sum mode (legacy) ─────────────────────────
        plan.hard_cap_usd = frozen_cap_sum if frozen_cap_sum > 0 else plan.min_viable_budget

        for strategy in strategies:
            spend = projected.get(strategy, 0.0)
            plan.projected_utilization_by_strategy[strategy] = (
                min(spend / plan.hard_cap_usd, 1.0) if plan.hard_cap_usd > 0 else 0.0
            )

        _build_pressure_contract(plan, strategies)

        max_util = max(plan.projected_utilization_by_strategy.values()) if plan.projected_utilization_by_strategy else 0.0
        budget_loose = max_util < 0.15
        if budget_loose and override_reason and frozen_cap_sum > 0:
            plan.decision = "PASS_WITH_DIAGNOSTIC_OVERRIDE"
            plan.override_reason = override_reason
            plan.reasons.append(
                f"max projected utilization {max_util:.1%} < 15% — "
                f"hard_cap=${plan.hard_cap_usd:.2f} is loose, but budget intentionally "
                f"bound to pre-registered frozen plan cap sum for "
                f"enterprise_router/budgetflow_same_enterprise_router symmetry"
            )
            plan.reasons.append(f"override: {override_reason}")
        elif max_util < 0.15:
            plan.decision = "BLOCK"
            plan.reasons.append(
                f"max projected utilization {max_util:.1%} < 15% — "
                f"hard_cap=${plan.hard_cap_usd:.2f} is too loose, budget not binding"
            )
        elif max_util < 0.30:
            plan.reasons.append(
                f"max projected utilization {max_util:.1%} is low (< 30%) — "
                f"consider tightening hard_cap"
            )

        for strategy in strategies:
            spend = projected.get(strategy, 0.0)
            if spend > plan.hard_cap_usd * 1.1:
                plan.decision = "BLOCK"
                plan.reasons.append(
                    f"{strategy} projected spend ${spend:.2f} > "
                    f"hard_cap ${plan.hard_cap_usd:.2f} — budget too tight"
                )

        if frozen_cap_sum > 0 and plan.hard_cap_usd != frozen_cap_sum:
            plan.decision = "BLOCK"
            plan.reasons.append(
                f"hard_cap ${plan.hard_cap_usd:.2f} != frozen cap sum ${frozen_cap_sum:.2f}"
            )

        if not plan.reasons:
            plan.reasons.append(
                f"all strategies projected within hard_cap=${plan.hard_cap_usd:.2f}, "
                f"max utilization {max_util:.1%}"
            )

    # ── Projection confidence from prior calibration ────────────────────
    if prior_calibration is not None:
        plan.projection_confidence = prior_calibration.projection_confidence
        plan.calibration_error = {
            s: e["error_pct"] for s, e in prior_calibration.strategy_errors.items()
        }
        _apply_calibration_gate(plan, prior_calibration)
    else:
        plan.projection_confidence = "unvalidated"
        plan.reasons.append(
            "projection_confidence=unvalidated: no prior calibration audit provided. "
            "Run a no-paid calibration audit before relying on projected utilization."
        )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n")

    return plan


def audit_calibration(
    jsonl_path: Path,
    budget_plan: BudgetBindingPlan | Path,
    *,
    output_path: Path | None = None,
    per_strategy_cap: dict[str, float] | None = None,
) -> CalibrationAudit:
    """Compare projected spend from a budget plan against actual spend in a JSONL.

    Pure no-paid analysis.  Reads completed JSONL records, aggregates actual
    spend per strategy, and compares against the budget plan's projections.
    Computes projection error, confidence grade, and recommendations.

    *budget_plan* can be a BudgetBindingPlan instance or a path to a
    budget_plan.json file.

    *per_strategy_cap* maps strategy name → batch cap for per-policy
    utilization.  When provided, utilization is computed against each
    strategy's own cap rather than the single ``hard_cap_usd``.
    """
    if isinstance(budget_plan, Path):
        plan = BudgetBindingPlan.from_dict(json.loads(budget_plan.read_text()))
    else:
        plan = budget_plan

    # ── Aggregate actual spend from JSONL ──────────────────────────────
    actual_spend: dict[str, float] = {}
    actual_utilization: dict[str, float] = {}
    strategy_task_counts: dict[str, int] = {}

    latest_records: dict[tuple[str, str], tuple[float, int, dict]] = {}
    with jsonl_path.open() as f:
        for order, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            strategy = rec.get("strategy", "")
            instance_id = rec.get("instance_id", "")
            if not strategy or not instance_id:
                continue
            # Dedup: keep last occurrence of each (strategy, instance_id)
            key = (strategy, instance_id)
            finished_at = float(rec.get("row_finished_at", 0) or 0)
            if key not in latest_records or (finished_at, order) >= (
                latest_records[key][0],
                latest_records[key][1],
            ):
                latest_records[key] = (finished_at, order, rec)

    for (strategy, _instance_id), (_finished_at, _order, rec) in latest_records.items():
        cost = float(rec.get("total_cost") or 0)
        actual_spend[strategy] = actual_spend.get(strategy, 0.0) + cost
        strategy_task_counts[strategy] = strategy_task_counts.get(strategy, 0) + 1

    if per_strategy_cap:
        for strategy in actual_spend:
            cap = per_strategy_cap.get(strategy, per_strategy_cap.get("default"))
            if cap and cap > 0:
                actual_utilization[strategy] = round(min(actual_spend[strategy] / cap, 1.0), 4)
    else:
        hard_cap = plan.hard_cap_usd
        if hard_cap > 0:
            for strategy in actual_spend:
                actual_utilization[strategy] = round(min(actual_spend[strategy] / hard_cap, 1.0), 4)

    # ── Compare projected vs actual ────────────────────────────────────
    strategy_errors: dict[str, dict] = {}
    total_abs_error = 0.0
    n_strategies = 0

    for strategy in plan.projected_spend_by_strategy:
        projected = plan.projected_spend_by_strategy.get(strategy, 0.0)
        actual = actual_spend.get(strategy, 0.0)
        if projected <= 0 and actual <= 0:
            continue
        n_strategies += 1
        error_pct = abs(projected - actual) / max(projected, 0.001)
        total_abs_error += error_pct
        cap = per_strategy_cap.get(strategy) if per_strategy_cap else plan.hard_cap_usd
        strategy_errors[strategy] = {
            "projected": round(projected, 4),
            "actual": round(actual, 4),
            "error_pct": round(error_pct, 4),
            "strategy_cap": round(cap, 4) if cap else None,
            "projected_utilization": plan.projected_utilization_by_strategy.get(strategy, 0.0),
            "actual_utilization": actual_utilization.get(strategy, 0.0),
            "task_count": strategy_task_counts.get(strategy, 0),
        }

    overall_mape = total_abs_error / max(n_strategies, 1)

    # ── Confidence grade ───────────────────────────────────────────────
    if overall_mape < 0.30:
        confidence = "high"
    elif overall_mape < 0.60:
        confidence = "low"
    else:
        confidence = "unvalidated"

    # ── Max error ──────────────────────────────────────────────────────
    max_err_strat = ""
    max_err_pct = 0.0
    for strat, err in strategy_errors.items():
        if err["error_pct"] > max_err_pct:
            max_err_pct = err["error_pct"]
            max_err_strat = strat

    # ── Recommendations ────────────────────────────────────────────────
    recommendations: list[str] = []
    if confidence == "unvalidated":
        recommendations.append(
            "BLOCK next paid run until projection model is recalibrated. "
            f"Overall MAPE {overall_mape:.1%} exceeds 60% threshold."
        )
    elif confidence == "low":
        recommendations.append(
            f"WARNING: projection error MAPE={overall_mape:.1%}. "
            "Consider using frozen_plan_cap_sum mode or a larger safety margin."
        )
    if max_err_pct > 1.0:
        recommendations.append(
            f"CRITICAL: {max_err_strat} projection error {max_err_pct:.1%} — "
            "this strategy's spend estimate is off by more than 2x."
        )

    audit = CalibrationAudit(
        strategy_errors=strategy_errors,
        overall_mape=overall_mape,
        max_error_strategy=max_err_strat,
        max_error_pct=max_err_pct,
        projection_confidence=confidence,
        recommendations=recommendations,
        generation_mode=plan.generation_mode,
        target_utilization=plan.target_projected_utilization,
        actual_utilization_by_strategy=actual_utilization,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(audit.to_dict(), indent=2) + "\n")

    return audit


def _distribution_p75(values: list[float]) -> float:
    """75th percentile of *values* via nearest-rank method.

    Returns 0.0 when *values* is empty.  Used as the reference point for
    target-utilization budget generation: the budget is set so that p75
    of the comparison strategy set fits within the target utilization,
    while the most expensive strategy faces genuine pressure.
    """
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    idx = min(int(math.ceil(0.75 * n)) - 1, n - 1)
    return sorted_v[max(idx, 0)]


def _build_pressure_contract(
    plan: BudgetBindingPlan,
    strategies: tuple[str, ...],
) -> None:
    """Build a formalized pressure contract from projected utilization.

    The pressure contract documents expected shape assertions and grades
    the budget plan's pressure quality.  It is an audit output — it never
    drives generation rules.
    """
    utils = plan.projected_utilization_by_strategy
    t2_util = utils.get("bare_t2_baseline", 0.0)
    t3_util = utils.get("bare_t3_baseline", 0.0)
    er_util = utils.get("enterprise_router_baseline", 0.0)
    bf_task_util = utils.get("budgetflow_task_level", 0.0)
    bf_segment_util = utils.get("budgetflow_segment", 0.0)
    bf_primary_util = bf_task_util or bf_segment_util
    target = plan.target_projected_utilization or 0.80

    assertions: list[str] = []
    violations: list[str] = []

    # Shape assertions
    if t2_util > 0 and t3_util > 0:
        if t2_util < target:
            assertions.append(f"t2_loose: bare_t2_baseline at {t2_util:.1%} < target {target:.0%}")
        else:
            violations.append(f"t2_tight: bare_t2_baseline at {t2_util:.1%} >= target {target:.0%} — budget may be too tight for T2")

        if t3_util >= target * 0.85:
            assertions.append(f"t3_tight: bare_t3_baseline at {t3_util:.1%} >= {target * 0.85:.0%} — budget-constrained as expected")
        else:
            violations.append(f"t3_loose: bare_t3_baseline at {t3_util:.1%} < {target * 0.85:.0%} — strongest tier not budget-constrained")

        if t3_util < t2_util:
            violations.append(
                f"pressure_inverted: T3 ({t3_util:.1%}) < T2 ({t2_util:.1%}) — "
                "strongest tier has more headroom than middle tier; pressure direction is wrong"
            )

    if bf_primary_util > 0:
        primary_name = "budgetflow_task_level" if bf_task_util > 0 else "budgetflow_segment"
        if abs(bf_primary_util - target) < 0.15:
            assertions.append(f"budgetflow_near_target: {primary_name} at {bf_primary_util:.1%} near target {target:.0%}")
        else:
            violations.append(f"budgetflow_off_target: {primary_name} at {bf_primary_util:.1%} far from target {target:.0%}")

    # Grade
    if not assertions and not violations:
        grade = "fail"
        violations.append("no pressure data available — cannot assess contract")
    elif any("inverted" in v for v in violations):
        grade = "fail"
    elif violations:
        grade = "warn"
    else:
        grade = "pass"

    contract = {
        "target_utilization": target,
        "shape": {
            "bare_t2_baseline": round(t2_util, 4),
            "bare_t3_baseline": round(t3_util, 4),
            "enterprise_router_baseline": round(er_util, 4) if er_util > 0 else None,
            "budgetflow_same_enterprise_router": round(
                utils.get("budgetflow_same_enterprise_router", 0.0), 4
            ) if utils.get("budgetflow_same_enterprise_router", 0.0) > 0 else None,
            "budgetflow_task_level": round(bf_task_util, 4) if bf_task_util > 0 else None,
            "budgetflow_segment": round(bf_segment_util, 4) if bf_segment_util > 0 else None,
        },
        "assertions": assertions,
        "violations": violations,
        "grade": grade,
    }
    plan.pressure_contract = contract

    # Also add summary lines to reasons for readability
    plan.reasons.append(f"pressure_contract: grade={grade}")
    for a in assertions:
        plan.reasons.append(f"pressure_contract: {a}")
    for v in violations:
        plan.reasons.append(f"pressure_contract VIOLATION: {v}")


def _apply_calibration_gate(
    plan: BudgetBindingPlan,
    audit: CalibrationAudit,
) -> None:
    """Apply prior calibration results to the readiness gate.

    Downgrades the plan decision when projection confidence is insufficient.
    This prevents pretending target_utilization is satisfied when the
    projection model has known large errors.
    """
    confidence = audit.projection_confidence

    if confidence == "unvalidated":
        if plan.decision == "PASS":
            plan.decision = "BLOCK"
            plan.reasons.append(
                f"CALIBRATION_GATE BLOCK: prior projection MAPE={audit.overall_mape:.1%} "
                f"exceeds 60% threshold. Projection model is unvalidated — cannot "
                f"rely on target_utilization budget. Recalibrate projection model or "
                f"use frozen_plan_cap_sum budget mode."
            )
        for rec in audit.recommendations:
            plan.reasons.append(f"CALIBRATION_GATE: {rec}")

    elif confidence == "low":
        plan.reasons.append(
            f"CALIBRATION_GATE WARNING: prior projection MAPE={audit.overall_mape:.1%} "
            f"is in 30-60% range. Projection confidence is low. "
            f"Max error: {audit.max_error_strategy} at {audit.max_error_pct:.1%}. "
            f"Consider adding a 20-30% safety margin to hard_cap."
        )
        for rec in audit.recommendations:
            plan.reasons.append(f"CALIBRATION_GATE: {rec}")

    else:
        plan.reasons.append(
            f"CALIBRATION_GATE: prior projection MAPE={audit.overall_mape:.1%} "
            f"confidence={confidence}. Max error: {audit.max_error_strategy} "
            f"at {audit.max_error_pct:.1%}."
        )


def _row_is_calibration_eligible(row: dict) -> tuple[bool, str]:
    """Check whether a historical JSONL row is clean enough for cost calibration.

    Contaminated rows are forensic-only — they may inform postmortems but
    must not enter cost-per-effort or ModelFit estimation.
    """
    budget_mode = row.get("budget_mode", "")

    # Budget asymmetry is a runtime cap-mode problem.  A budget plan whose
    # source is "frozen_plan_cap_sum" can still produce a clean shared batch
    # cap after the cap semantics fix, so do not key on budget_input.source.
    if budget_mode == "frozen_router_caps":
        return False, "budget_asymmetry:frozen_router_caps"

    # Diagnostic catalog with inflated prices (e.g. t3x3 = 3x T3 prices).
    catalog = row.get("catalog") or {}
    catalog_rev = catalog.get("catalog_revision", "")
    if "t3x3" in catalog_rev.lower() or "diagnostic" in catalog_rev.lower():
        return False, f"diagnostic_catalog:{catalog_rev}"

    # Router bugs or pre-selected backend that contaminated tier choices.
    routing = row.get("routing", "")
    va_active = row.get("va_active")
    if routing == "enterprise_router" and va_active is True:
        return False, "contaminated:enterprise_router_with_va_active"

    # Protocol/harness errors that truncated the run — cost is not
    # representative of normal execution.
    exit_status = row.get("exit_status", "")
    if exit_status in ("BudgetFlowBudgetError",):
        return False, f"budget_error:{exit_status}"

    # Successful protocol retries are valid scoreable evidence, but their
    # cost includes a failed formatting/provider turn.  Keep them out of cost
    # calibration so retry instability does not inflate future budget plans.
    if row.get("protocol_retry_used"):
        return False, "protocol_retry_overhead"

    return True, "clean"


def _load_historical_costs(
    jsonl_path: Path,
    *,
    calibration_eligible_only: bool = True,
) -> tuple[dict[str, dict[str, float]], dict[str, int]]:
    """Extract per-strategy per-task total_cost from historical JSONL.

    Returns (costs, exclusion_counts) where exclusion_counts maps
    exclusion_reason -> count of rows filtered out.
    """
    costs: dict[str, dict[str, float]] = {}
    excluded: dict[str, int] = {}
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            strategy = d.get("strategy", "")
            instance_id = d.get("instance_id", "")
            if not strategy or not instance_id:
                continue

            if calibration_eligible_only:
                eligible, reason = _row_is_calibration_eligible(d)
                if not eligible:
                    excluded[reason] = excluded.get(reason, 0) + 1
                    continue

            total_cost = d.get("total_cost") or d.get("scoreable_cost") or 0.0
            costs.setdefault(strategy, {})[instance_id] = float(total_cost)
    return costs, excluded


def _estimate_t3_cost_share(
    strategy: str,
    task_id: str,
    historical: dict[str, dict[str, float]],
    *,
    preferred_models: dict[str, str] | None = None,
) -> float:
    """Estimate T3 cost share from historical data, not hardcoded labels.

    Uses per-strategy effective-cost observation when historical rows exist.
    Falls back to catalog-based heuristics for zero-history tasks.
    """
    # Strategies that use a single tier based on fixed routing
    if strategy == "bare_t3_baseline":
        return 1.0
    if strategy == "bare_t2_baseline":
        return 0.0
    # Frozen-plan strategies: T3 share depends on preferred_model, not
    # a hardcoded default.  When no plan entry exists, assume T2-only
    # (conservative for budget estimation).
    if strategy in ("enterprise_router_baseline", "budgetflow_same_enterprise_router"):
        if preferred_models:
            model = preferred_models.get(task_id, "")
            if model == "tier3":
                return 1.0
        return 0.0
    # BudgetFlow value-aware and segment-aware policies: mixed T2/T3.
    # Use 0.30 as a weakly-informative prior — the actual share depends
    # on task value, effort, model fit, and budget pressure at runtime.
    if strategy in {"budgetflow_task_level", "budgetflow_segment",
                    "budgetflow_conservative", "segment_value_aware",
                    "budgetflow_same_enterprise_router"}:
        return 0.30
    # Conservative default for unrecognised strategies: assume T2-only.
    # Override this when adding a new strategy that uses mixed routing.
    return 0.0


def _t3_price_multiplier() -> float:
    """Compute how much more expensive T3 is in current catalog vs reference.

    Reference: the calibrated T3 price from the default catalog
    ($0.294/$1.793 per 1M).  Returns the multiplier to apply to historical
    T3 costs.
    """
    t3_cfg = MODEL_CATALOG.config_for("tier3")
    if t3_cfg is None:
        return 1.0
    # Reference: default catalog T3 prices (calibrated transaction price)
    ref_input = 0.294  # $/1M
    ref_output = 1.793  # $/1M
    cur_input = t3_cfg.cost_per_input_token * 1_000_000
    cur_output = t3_cfg.cost_per_output_token * 1_000_000
    # Average multiplier weighted toward output (output tokens dominate cost)
    input_mult = cur_input / ref_input if ref_input > 0 else 1.0
    output_mult = cur_output / ref_output if ref_output > 0 else 1.0
    return (input_mult + output_mult) / 2.0


def _load_frozen_caps(frozen_plan_path: Path) -> dict[str, float]:
    """Extract per-task base_cap from frozen router plan."""
    with frozen_plan_path.open() as f:
        plan = json.load(f)
    caps: dict[str, float] = {}
    for tid, entry in plan.get("plan", {}).items():
        caps[tid] = float(entry.get("base_cap", 0.0))
    return caps


def _load_frozen_preferred_models(frozen_plan_path: Path) -> dict[str, str]:
    """Extract per-task preferred_model from frozen router plan."""
    with frozen_plan_path.open() as f:
        plan = json.load(f)
    models: dict[str, str] = {}
    for tid, entry in plan.get("plan", {}).items():
        model = str(entry.get("preferred_model", ""))
        if model:
            models[tid] = model
    return models


def _load_value_features(value_matrix_path: Path) -> dict[str, dict]:
    """Extract per-task features from value matrix.

    Reads ``task_effort.bootstrap_heuristic`` (North Star schema) and
    normalises into a ``bootstrap_difficulty`` key on each entry.
    """
    with value_matrix_path.open() as f:
        matrix = json.load(f)
    tasks = matrix.get("tasks", {})
    for tid, entry in tasks.items():
        if not isinstance(entry, dict):
            continue
        if "bootstrap_difficulty" in entry:
            continue
        te = entry.get("task_effort")
        if isinstance(te, dict):
            heuristic = te.get("bootstrap_heuristic")
            if heuristic is not None:
                entry["bootstrap_difficulty"] = float(heuristic)
    return tasks


def _bootstrap_cost_estimate(
    task_id: str,
    strategy: str,
    value_features: dict[str, dict],
    historical: dict[str, dict[str, float]],
    t3_multiplier: float,
    *,
    frozen_caps: dict[str, float] | None = None,
) -> float:
    """Project cold-start spend pressure for a task with no historical data.

    When frozen caps exist, they are used as pressure anchors rather than as
    empirical expected-cost observations.  Otherwise the compiler falls back
    to bootstrap_difficulty ratios vs known tasks of the same strategy.
    """
    frozen_cap = (frozen_caps or {}).get(task_id)
    if frozen_cap is not None and frozen_cap > 0:
        multiplier = _COLD_START_PRESSURE_PRIOR_MULTIPLIERS.get(strategy)
        if multiplier is not None:
            return frozen_cap * multiplier

    features = value_features.get(task_id, {})
    difficulty = (
        features.get("bootstrap_difficulty", 30.0)
        if features else 30.0
    )

    # Find median cost per difficulty unit from historical data
    ratios: list[float] = []
    for hist_tid, hist_feat in value_features.items():
        hist_cost = historical.get(strategy, {}).get(hist_tid)
        if hist_cost is None or hist_cost <= 0:
            continue
        hist_diff = hist_feat.get("bootstrap_difficulty")
        if hist_diff is None or hist_diff <= 0:
            continue
        ratios.append(hist_cost / hist_diff)

    if not ratios:
        return _fallback_cost_estimate(strategy, difficulty, t3_multiplier)

    median_ratio = sorted(ratios)[len(ratios) // 2]
    estimated = difficulty * median_ratio

    # Apply T3 multiplier for strategies that may use T3
    if strategy == "bare_t3_baseline":
        estimated *= t3_multiplier
    elif strategy in {"budgetflow_task_level", "budgetflow_segment",
                      "budgetflow_conservative", "segment_value_aware",
                      "budgetflow_same_enterprise_router"}:
        estimated *= (1.0 + 0.30 * (t3_multiplier - 1.0))

    return estimated


def _fallback_cost_estimate(
    strategy: str,
    difficulty: float,
    t3_multiplier: float,
) -> float:
    """Conservative cost estimate when no historical data is available."""
    # Base: ~$0.001 per difficulty unit (calibrated from SymPy data)
    base_rate = 0.001
    estimated = difficulty * base_rate
    if strategy == "bare_t3_baseline":
        estimated *= t3_multiplier
    elif strategy in {"budgetflow_task_level", "budgetflow_segment",
                      "budgetflow_conservative", "segment_value_aware",
                      "budgetflow_same_enterprise_router"}:
        estimated *= (1.0 + 0.30 * (t3_multiplier - 1.0))
    return estimated


def _parse_task_ids(raw: str) -> list[str]:
    task_ids = [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]
    if not task_ids:
        raise SystemExit("--task-ids did not contain any task ids")
    return task_ids


def _strategy_names_from_set(path: str | None) -> tuple[str, ...]:
    if not path:
        return paper_mainline_strategy_names()
    return tuple(strategy.name for strategy in load_strategy_set(path))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Budget Regime Compiler: generate or audit budget_plan.json artifacts"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    calibrate = sub.add_parser("calibrate", help="generate a budget_plan.json")
    calibrate.add_argument("--task-ids", required=True, help="comma-separated selected task ids")
    calibrate.add_argument("--strategy-set", default=None, help="strategy-set JSON; default is paper mainline")
    calibrate.add_argument("--frozen-plan", default=None, help="frozen router plan JSON")
    calibrate.add_argument("--value-matrix", default=None, help="value matrix JSON")
    calibrate.add_argument("--model-catalog", default=None, help="model tier catalog JSON")
    calibrate.add_argument("--historical-jsonl", default=None, help="optional clean historical JSONL")
    calibrate.add_argument(
        "--target-utilization",
        type=float,
        default=None,
        help="generate hard_cap from p75(projected spend) / target utilization",
    )
    calibrate.add_argument("--override-reason", default="", help="documented diagnostic override reason")
    calibrate.add_argument("--output", required=True, help="output budget_plan.json path")

    audit = sub.add_parser("audit", help="compare projected vs actual spend from a completed JSONL")
    audit.add_argument("--jsonl", required=True, help="run JSONL to audit")
    audit.add_argument("--budget-plan", required=True, help="budget_plan.json used for the run")
    audit.add_argument("--output", required=False, help="optional calibration audit JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "calibrate":
        if args.model_catalog:
            init_catalog(Path(args.model_catalog))
        plan = calibrate_budget(
            _parse_task_ids(args.task_ids),
            historical_jsonl=Path(args.historical_jsonl) if args.historical_jsonl else None,
            frozen_plan_path=Path(args.frozen_plan) if args.frozen_plan else None,
            value_matrix_path=Path(args.value_matrix) if args.value_matrix else None,
            strategies=_strategy_names_from_set(args.strategy_set),
            output_path=Path(args.output),
            override_reason=args.override_reason,
            target_utilization=args.target_utilization,
        )
        print(
            f"wrote {args.output}: decision={plan.decision} "
            f"generation_mode={plan.generation_mode} hard_cap=${plan.hard_cap_usd:.4f} "
            f"catalog={plan.catalog_revision}",
            flush=True,
        )
        return 0 if plan.decision != "BLOCK" else 2

    if args.command == "audit":
        audit = audit_calibration(
            Path(args.jsonl),
            Path(args.budget_plan),
            output_path=Path(args.output) if args.output else None,
        )
        if args.output:
            print(
                f"wrote {args.output}: confidence={audit.projection_confidence} "
                f"mape={audit.overall_mape:.1%}",
                flush=True,
            )
        else:
            print(json.dumps(audit.to_dict(), indent=2), flush=True)
        return 0

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

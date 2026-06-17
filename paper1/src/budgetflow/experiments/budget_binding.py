"""Budget binding calibrator — generates auditable budget_plan.json from code.

Reads historical diagnostic JSONL and projects spend for the target task set.
Produces a budget plan with a GO/NO-GO decision that paid-readiness gates on.

No ML, no outcome leakage.  Current-schema JSONL costs are already settled in
the run's model-tier catalog units. Budget-exhausted rows are censored spend
floors, not complete cost observations.
"""

from __future__ import annotations

import json
import math
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from budgetflow.experiments.compare_config import load_strategy_set, paper_mainline_strategy_names

from ..model_fit_estimator import ModelFitEvidence, estimate_model_fit_from_jsonl
from ..model_tiers import (
    MODEL_CATALOG,
    catalog_path,
    catalog_revision,
    catalog_source_info,
    estimate_token_cost,
    init_catalog,
)


COLD_START_INPUT_TOKENS_PER_EFFORT = 4_500
COLD_START_OUTPUT_TOKENS_PER_EFFORT = 150
BUDGETFLOW_PLANNED_TASK_BUDGET_MODE = "budgetflow_loose_task_budget"
BUDGETFLOW_PLANNED_TASK_BUDGET_MULTIPLIER = 2.0
BUDGETFLOW_PLANNED_TASK_BUDGET_MIN_USD = 0.05
BUDGETFLOW_PLANNED_TASK_BUDGET_BATCH_FLOOR_RULE = "hard_cap_usd/sqrt(task_count)+projected_cost_multiplier"
BUDGETFLOW_PLANNED_TASK_BUDGET_STRATEGIES = frozenset({
    "budgetflow_task_level",
    "budgetflow_segment",
})


@dataclass
class BudgetBindingPlan:
    """Code-generated budget plan for a compare run."""

    hard_cap_usd: float
    source: str = "budget_binding_calibrator"
    generation_mode: str = "target_utilization"
    target_projected_utilization: float | None = None
    catalog_revision: str = ""
    catalog_path: str = ""
    catalog_content_hash: str = ""
    historical_source: str = ""
    task_ids: list[str] = field(default_factory=list)
    strategy_names: list[str] = field(default_factory=list)
    projected_spend_by_strategy: dict[str, float] = field(default_factory=dict)
    projected_task_cost_by_strategy: dict[str, dict[str, float]] = field(default_factory=dict)
    projected_utilization_by_strategy: dict[str, float] = field(default_factory=dict)
    raw_projected_utilization_by_strategy: dict[str, float] = field(default_factory=dict)
    reference_spend_usd: float = 0.0
    strongest_boundary_usd: float = 0.0
    max_projected_spend_usd: float = 0.0
    decision: str = "PASS"
    reasons: list[str] = field(default_factory=list)
    pressure_contract: dict[str, Any] = field(default_factory=dict)
    projection_confidence: str = "unvalidated"
    calibration_error: dict[str, float] = field(default_factory=dict)
    calibration_excluded: dict[str, int] = field(default_factory=dict)
    censored_spend_floor_by_strategy: dict[str, float] = field(default_factory=dict)
    model_fit_evidence: dict | None = None
    planned_task_budget_by_strategy: dict[str, dict[str, float]] = field(default_factory=dict)
    planned_task_budget_policy: dict[str, Any] = field(default_factory=dict)

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
            "projected_task_cost_by_strategy": {
                strategy: {task_id: round(cost, 4) for task_id, cost in costs.items()}
                for strategy, costs in self.projected_task_cost_by_strategy.items()
            },
            "projected_utilization_by_strategy": {
                k: round(v, 4) for k, v in self.projected_utilization_by_strategy.items()
            },
            "raw_projected_utilization_by_strategy": {
                k: round(v, 4) for k, v in self.raw_projected_utilization_by_strategy.items()
            },
            "reference_spend_usd": round(self.reference_spend_usd, 4),
            "strongest_boundary_usd": round(self.strongest_boundary_usd, 4),
            "max_projected_spend_usd": round(self.max_projected_spend_usd, 4),
            "decision": self.decision,
            "reasons": self.reasons,
            "pressure_contract": self.pressure_contract,
            "projection_confidence": self.projection_confidence,
        }
        if self.target_projected_utilization is not None:
            d["target_projected_utilization"] = round(self.target_projected_utilization, 4)
        if self.calibration_error:
            d["calibration_error"] = {k: round(v, 4) for k, v in self.calibration_error.items()}
        if self.calibration_excluded:
            d["calibration_excluded"] = dict(self.calibration_excluded)
        if self.censored_spend_floor_by_strategy:
            d["censored_spend_floor_by_strategy"] = {
                k: round(v, 4) for k, v in self.censored_spend_floor_by_strategy.items()
            }
        if self.model_fit_evidence:
            d["model_fit_evidence"] = self.model_fit_evidence
        if self.planned_task_budget_by_strategy:
            d["planned_task_budget_by_strategy"] = {
                strategy: {task_id: round(cap, 4) for task_id, cap in caps.items()}
                for strategy, caps in self.planned_task_budget_by_strategy.items()
            }
            d["planned_task_budget_policy"] = dict(self.planned_task_budget_policy)
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
            projected_task_cost_by_strategy=d.get("projected_task_cost_by_strategy", {}),
            projected_utilization_by_strategy=d.get("projected_utilization_by_strategy", {}),
            raw_projected_utilization_by_strategy=d.get("raw_projected_utilization_by_strategy", {}),
            reference_spend_usd=d.get("reference_spend_usd", 0.0),
            strongest_boundary_usd=d.get("strongest_boundary_usd", 0.0),
            max_projected_spend_usd=d.get("max_projected_spend_usd", 0.0),
            decision=d.get("decision", "PASS"),
            reasons=d.get("reasons", []),
            pressure_contract=d.get("pressure_contract", {}),
            projection_confidence=d.get("projection_confidence", "unvalidated"),
            calibration_error=d.get("calibration_error", {}),
            calibration_excluded=d.get("calibration_excluded", {}),
            censored_spend_floor_by_strategy=d.get("censored_spend_floor_by_strategy", {}),
            model_fit_evidence=d.get("model_fit_evidence"),
            planned_task_budget_by_strategy=d.get("planned_task_budget_by_strategy", {}),
            planned_task_budget_policy=d.get("planned_task_budget_policy", {}),
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
    raw_actual_utilization_by_strategy: dict[str, float] = field(default_factory=dict)
    budget_exhausted_by_strategy: dict[str, int] = field(default_factory=dict)

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
            "raw_actual_utilization_by_strategy": {
                k: round(v, 4) for k, v in self.raw_actual_utilization_by_strategy.items()
            },
            "budget_exhausted_by_strategy": dict(self.budget_exhausted_by_strategy),
        }

    @classmethod
    def from_dict(cls, d: dict) -> CalibrationAudit:
        return cls(
            strategy_errors=d.get("strategy_errors", {}),
            overall_mape=float(d.get("overall_mape", 0.0) or 0.0),
            max_error_strategy=str(d.get("max_error_strategy", "") or ""),
            max_error_pct=float(d.get("max_error_pct", 0.0) or 0.0),
            projection_confidence=str(d.get("projection_confidence", "unvalidated") or "unvalidated"),
            recommendations=list(d.get("recommendations", []) or []),
            generation_mode=str(d.get("generation_mode", "") or ""),
            target_utilization=d.get("target_utilization"),
            actual_utilization_by_strategy=d.get("actual_utilization_by_strategy", {}),
            raw_actual_utilization_by_strategy=d.get("raw_actual_utilization_by_strategy", {}),
            budget_exhausted_by_strategy=d.get("budget_exhausted_by_strategy", {}),
        )


@dataclass
class HistoricalCostSignals:
    """Cost signals with complete observations separated from censored floors."""

    observed_costs: dict[str, dict[str, float]] = field(default_factory=dict)
    censored_task_costs_by_strategy: dict[str, dict[str, float]] = field(default_factory=dict)
    censored_spend_floor_by_strategy: dict[str, float] = field(default_factory=dict)
    censored_row_counts: dict[str, int] = field(default_factory=dict)
    excluded: dict[str, int] = field(default_factory=dict)


# ── Public API ────────────────────────────────────────────────────────────


def calibrate_budget(
    task_ids: list[str],
    *,
    historical_jsonl: Path | None = None,
    value_matrix_path: Path | None = None,
    strategies: tuple[str, ...] | None = None,
    output_path: Path | None = None,
    target_utilization: float | None = None,
    calibration_evidence: CalibrationAudit | None = None,
) -> BudgetBindingPlan:
    """Generate a budget binding plan from historical data and current catalog.

    ``hard_cap`` = p75(projected spend) / *target_utilization*, clipped by the
    Strongest Model projected spend. The reference is the 75th percentile of the
    configured paper-mainline strategy set — not any single BudgetFlow policy's
    spend. Cheaper strategies have more headroom; bare T3 may be at or above
    cap. The pressure shape is an audit output, never a generation rule.

    *calibration_evidence* is read-only readiness evidence from one prior
    diagnostic pass. It does not tune the cap. When the audit shows high
    projection error, the plan decision may be downgraded to WARNING or BLOCK.
    """
    if target_utilization is None:
        raise ValueError("target_utilization is required")
    if not (0.0 < target_utilization <= 1.0):
        raise ValueError(f"target_utilization must be in (0, 1], got {target_utilization}")
    if strategies is None:
        strategies = paper_mainline_strategy_names()

    catalog_info = catalog_source_info()
    plan = BudgetBindingPlan(
        hard_cap_usd=0.0,
        generation_mode="target_utilization",
        target_projected_utilization=target_utilization,
        catalog_revision=str(catalog_info.get("catalog_revision") or catalog_revision()),
        catalog_path=str(catalog_info.get("catalog_path") or catalog_path()),
        catalog_content_hash=str(catalog_info.get("catalog_content_hash") or ""),
        historical_source=str(historical_jsonl) if historical_jsonl else "bootstrap_estimate",
        task_ids=list(task_ids),
        strategy_names=list(strategies),
    )

    # ── Load historical per-strategy per-task cost signals ───────────────
    historical: dict[str, dict[str, float]] = {}  # strategy -> {task_id -> cost}
    calibration_excluded: dict[str, int] = {}
    censored_spend_floor_by_strategy: dict[str, float] = {}
    censored_task_costs_by_strategy: dict[str, dict[str, float]] = {}
    if historical_jsonl and historical_jsonl.exists():
        signals = _load_historical_cost_signals(historical_jsonl)
        historical = signals.observed_costs
        calibration_excluded = signals.excluded
        censored_task_costs_by_strategy = signals.censored_task_costs_by_strategy
        censored_spend_floor_by_strategy = {
            strategy: sum(
                cost for task_id, cost in task_costs.items()
                if task_id in set(task_ids)
            )
            for strategy, task_costs in censored_task_costs_by_strategy.items()
        }
        censored_spend_floor_by_strategy = {
            strategy: floor
            for strategy, floor in censored_spend_floor_by_strategy.items()
            if floor > 0
        }
        if calibration_excluded:
            plan.calibration_excluded = calibration_excluded
            total_excluded = sum(calibration_excluded.values())
            plan.reasons.append(
                f"calibration:excluded {total_excluded} contaminated rows: "
                + ", ".join(f"{k}={v}" for k, v in sorted(calibration_excluded.items()))
            )
        if censored_spend_floor_by_strategy:
            plan.censored_spend_floor_by_strategy = censored_spend_floor_by_strategy
            plan.reasons.append(
                "calibration:censored spend floors from budget-exhausted rows: "
                + ", ".join(
                    f"{k}=${v:.4f}" for k, v in sorted(censored_spend_floor_by_strategy.items())
                )
            )

    # ── Estimate zero-history tasks from value matrix ────────────────────
    value_features: dict[str, dict] = {}
    if value_matrix_path and value_matrix_path.exists():
        value_features = _load_value_features(value_matrix_path)

    # ── Derive ModelFit from clean historical evidence ──────────────────
    fit_overrides: dict[int, float] | None = None
    if historical_jsonl and historical_jsonl.exists() and value_features:
        try:
            evidence = estimate_model_fit_from_jsonl(
                historical_jsonl,
                task_ids,
                value_features,
            )
            fit_overrides = evidence.tier_fit
            plan.model_fit_evidence = {
                "tier_fit": evidence.to_allocation_model_fit(),
                "source": evidence.source,
                "confidence": evidence.confidence,
                "evidence_tasks": evidence.evidence_tasks,
                "censored_tiers": sorted(evidence.censored_tiers),
                "reasons": evidence.reasons,
            }
            plan.reasons.append(
                f"calibration:model_fit_evidence confidence={evidence.confidence} "
                f"from {evidence.evidence_tasks} tasks: "
                + ", ".join(
                    f"tier{t}={evidence.tier_fit[t]:.4f}" for t in sorted(evidence.tier_fit)
                )
            )
            if evidence.censored_tiers:
                plan.reasons.append(
                    f"calibration:model_fit_censored tiers={sorted(evidence.censored_tiers)} "
                    "have budget-exhausted upper-bound evidence"
                )
            if evidence.confidence in ("low", "medium"):
                plan.reasons.append(
                    f"calibration:model_fit_confidence={evidence.confidence}; "
                    "cold-start projections use derived fit but are not paper-ready. "
                    "Run more diagnostic calibration before treating as paper evidence."
                )
        except Exception:
            # ModelFit estimation is advisory; never block budget generation.
            pass

    strategy_cal_n: dict[str, int] = {}
    for strategy in strategies:
        observed = 0
        for tid in task_ids:
            hist_cost = historical.get(strategy, {}).get(tid)
            if hist_cost is not None and hist_cost > 0:
                observed += 1
        if observed:
            strategy_cal_n[strategy] = observed

    # ── Project spend per strategy ──────────────────────────────────────
    projected: dict[str, float] = {}
    projected_task_costs: dict[str, dict[str, float]] = {}
    for strategy in strategies:
        task_costs = _project_strategy_task_costs(
            strategy,
            task_ids,
            value_features,
            historical.get(strategy, {}),
            censored_task_costs_by_strategy.get(strategy, {}),
            fit_overrides=fit_overrides,
        )
        projected_task_costs[strategy] = task_costs
        projected[strategy] = sum(task_costs.values())

    plan.projected_spend_by_strategy = projected
    plan.projected_task_cost_by_strategy = projected_task_costs

    # Report per-strategy calibration confidence
    for strategy in strategies:
        cal_n = strategy_cal_n.get(strategy, 0)
        if cal_n >= 5:
            plan.reasons.append(
                f"calibration:{strategy} n={cal_n} exact observed costs"
            )
        elif cal_n > 0:
            plan.reasons.append(
                f"calibration:{strategy} n={cal_n} exact observed costs (low sample, no cross-task extrapolation)"
            )
        else:
            plan.reasons.append(
                f"calibration:{strategy} n=0 (no historical data, projection uses bootstrap_estimate)"
            )

    plan.max_projected_spend_usd = max(projected.values()) if projected else 0.0

    # ── Decision logic ──────────────────────────────────────────────────
    ref_spend = _distribution_p75(list(projected.values()))
    plan.reference_spend_usd = ref_spend
    plan.reasons.append(
        f"reference_rule: strategy_set_p75_projected_spend = ${ref_spend:.4f}"
    )

    t3_boundary = projected.get("bare_t3_baseline", 0.0)
    plan.strongest_boundary_usd = t3_boundary
    if ref_spend <= 0:
        plan.hard_cap_usd = 1.0
        plan.decision = "BLOCK"
        plan.reasons.append("no projected spend data; cannot compute p75 reference")
    else:
        target_cap = ref_spend / target_utilization
        strongest_runway_floor = _prefix_cost_before_final_task(
            projected_task_costs.get("bare_t3_baseline", {}),
            task_ids,
        )
        plan.hard_cap_usd = max(target_cap, strongest_runway_floor)
        plan.reasons.append(
            f"hard_cap = p75_ref(${ref_spend:.4f}) / "
            f"target_utilization({target_utilization}) = ${target_cap:.4f}"
        )
        if strongest_runway_floor > 0:
            plan.reasons.append(
                f"strongest_runway_floor: hard_cap must be at least "
                f"${strongest_runway_floor:.4f} so the Strongest Model baseline "
                "reaches the final task before budget pressure dominates"
            )
        if t3_boundary > 0:
            plan.reasons.append(
                f"strongest_boundary: bare_t3_baseline projected spend ${t3_boundary:.4f}; "
                "recorded for pressure audit, not a hard cap"
            )

    plan.planned_task_budget_by_strategy = _build_budgetflow_planned_task_budgets(
        strategies,
        task_ids,
        projected_task_costs,
        hard_cap_usd=plan.hard_cap_usd,
    )
    if plan.planned_task_budget_by_strategy:
        plan.planned_task_budget_policy = {
            "mode": BUDGETFLOW_PLANNED_TASK_BUDGET_MODE,
            "source": "projected_task_cost_by_strategy",
            "multiplier": BUDGETFLOW_PLANNED_TASK_BUDGET_MULTIPLIER,
            "min_usd": BUDGETFLOW_PLANNED_TASK_BUDGET_MIN_USD,
            "batch_floor_rule": BUDGETFLOW_PLANNED_TASK_BUDGET_BATCH_FLOOR_RULE,
            "sum_can_exceed_hard_cap": True,
            "applies_to": sorted(plan.planned_task_budget_by_strategy),
        }
        plan.reasons.append(
            "planned_task_budget: BudgetFlow active policies get loose task budgets "
            "derived from projected task costs; sums may exceed hard_cap and runtime "
            "still enforces the shared batch hard cap"
        )

    for strategy in strategies:
        spend = projected.get(strategy, 0.0)
        raw_util = spend / plan.hard_cap_usd if plan.hard_cap_usd > 0 else 0.0
        plan.raw_projected_utilization_by_strategy[strategy] = raw_util
        plan.projected_utilization_by_strategy[strategy] = min(raw_util, 1.0)

    _build_pressure_contract(plan, strategies)
    _apply_pressure_contract_gate(plan)

    for strategy in strategies:
        spend = projected.get(strategy, 0.0)
        if plan.hard_cap_usd > 0 and spend > plan.hard_cap_usd * 1.05:
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
            f"target pressure with strongest boundary, max projected utilization "
            f"{max_util:.1%}"
        )

    # ── Projection confidence from calibration evidence ─────────────────
    if calibration_evidence is not None:
        plan.projection_confidence = calibration_evidence.projection_confidence
        plan.calibration_error = {
            s: e["error_pct"] for s, e in calibration_evidence.strategy_errors.items()
        }
        _apply_calibration_gate(plan, calibration_evidence)
    else:
        plan.projection_confidence = "unvalidated"
        plan.reasons.append(
            "projection_confidence=unvalidated: no calibration evidence provided. "
            "Run one diagnostic calibration audit before relying on projected utilization."
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
    raw_actual_utilization: dict[str, float] = {}
    strategy_task_counts: dict[str, int] = {}
    budget_exhausted_by_strategy: dict[str, int] = {}

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
        if _row_is_budget_exhausted(rec):
            budget_exhausted_by_strategy[strategy] = budget_exhausted_by_strategy.get(strategy, 0) + 1

    if per_strategy_cap:
        for strategy in actual_spend:
            cap = per_strategy_cap.get(strategy, per_strategy_cap.get("default"))
            if cap and cap > 0:
                raw_util = actual_spend[strategy] / cap
                raw_actual_utilization[strategy] = round(raw_util, 4)
                actual_utilization[strategy] = round(min(raw_util, 1.0), 4)
    else:
        hard_cap = plan.hard_cap_usd
        if hard_cap > 0:
            for strategy in actual_spend:
                raw_util = actual_spend[strategy] / hard_cap
                raw_actual_utilization[strategy] = round(raw_util, 4)
                actual_utilization[strategy] = round(min(raw_util, 1.0), 4)

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
            "raw_projected_utilization": plan.raw_projected_utilization_by_strategy.get(
                strategy,
                plan.projected_utilization_by_strategy.get(strategy, 0.0),
            ),
            "actual_utilization": actual_utilization.get(strategy, 0.0),
            "raw_actual_utilization": raw_actual_utilization.get(strategy, 0.0),
            "budget_exhausted_rows": budget_exhausted_by_strategy.get(strategy, 0),
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
            "Treat the next run as diagnostic calibration evidence."
        )
    if max_err_pct > 1.0:
        recommendations.append(
            f"CRITICAL: {max_err_strat} projection error {max_err_pct:.1%} — "
            "this strategy's spend estimate is off by more than 2x."
        )

    primary_strategies = {
        "bare_t2_baseline",
        "bare_t3_baseline",
        "budgetflow_task_level",
        "budgetflow_segment",
    }
    saturated_primary = [
        strategy for strategy, util in actual_utilization.items()
        if strategy in primary_strategies and util >= 0.98
    ]
    if len(saturated_primary) >= 3:
        if confidence == "high":
            confidence = "low"
        recommendations.append(
            "WARNING: all primary strategies exhausted or nearly exhausted the shared cap "
            f"({', '.join(sorted(saturated_primary))}). Projection error alone is not enough "
            "to certify the target utilization regime; widen or recalibrate the budget plan "
            "before treating policy strength as interpretable."
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
        raw_actual_utilization_by_strategy=raw_actual_utilization,
        budget_exhausted_by_strategy=budget_exhausted_by_strategy,
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


def _build_budgetflow_planned_task_budgets(
    strategies: tuple[str, ...],
    task_ids: list[str],
    projected_task_costs: dict[str, dict[str, float]],
    *,
    hard_cap_usd: float,
) -> dict[str, dict[str, float]]:
    planned: dict[str, dict[str, float]] = {}
    task_count = max(1, len(task_ids))
    batch_floor = max(0.0, float(hard_cap_usd or 0.0)) / (task_count ** 0.5)
    for strategy in strategies:
        if strategy not in BUDGETFLOW_PLANNED_TASK_BUDGET_STRATEGIES:
            continue
        costs = projected_task_costs.get(strategy, {})
        if not costs:
            continue
        planned[strategy] = {
            task_id: max(
                BUDGETFLOW_PLANNED_TASK_BUDGET_MIN_USD,
                batch_floor
                + float(costs.get(task_id, 0.0)) * BUDGETFLOW_PLANNED_TASK_BUDGET_MULTIPLIER,
            )
            for task_id in task_ids
        }
    return planned


def _build_pressure_contract(
    plan: BudgetBindingPlan,
    strategies: tuple[str, ...],
) -> None:
    """Build a formalized pressure contract from projected utilization.

    The pressure contract documents expected shape assertions and grades the
    budget plan's pressure quality.  A failed contract can block readiness, but
    it does not change the cap formula itself.
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

    # Shape assertions.  T2 is a diagnostic mirror only: stronger models may
    # cost more per token but use fewer turns, so T2/T3 total utilization is not
    # an ordering axiom.
    if t2_util > 0 and t3_util > 0:
        assertions.append(
            f"t2_diagnostic: bare_t2_baseline at {t2_util:.1%}; "
            "not a pressure-ordering constraint"
        )

        if t3_util >= target * 0.85:
            assertions.append(f"t3_tight: bare_t3_baseline at {t3_util:.1%} >= {target * 0.85:.0%} — budget-constrained as expected")
        else:
            violations.append(f"t3_loose: bare_t3_baseline at {t3_util:.1%} < {target * 0.85:.0%} — strongest tier not budget-constrained")

    if bf_primary_util > 0:
        primary_name = "budgetflow_task_level" if bf_task_util > 0 else "budgetflow_segment"
        lower_bound = target * 0.85
        if bf_primary_util >= lower_bound:
            assertions.append(
                f"budgetflow_pressure_ready: {primary_name} at {bf_primary_util:.1%} "
                f">= {lower_bound:.0%}; enough pressure for allocation"
            )
        else:
            violations.append(
                f"budgetflow_under_target: {primary_name} at {bf_primary_util:.1%} "
                f"< {lower_bound:.0%}; budget may be too loose or policy may be too conservative"
            )

    # Grade
    if not assertions and not violations:
        grade = "fail"
        violations.append("no pressure data available — cannot assess contract")
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


def _apply_pressure_contract_gate(plan: BudgetBindingPlan) -> None:
    grade = str((plan.pressure_contract or {}).get("grade") or "")
    violations = list((plan.pressure_contract or {}).get("violations") or [])
    if grade == "fail" and plan.decision != "BLOCK":
        plan.decision = "BLOCK"
        plan.reasons.append(
            "PRESSURE_GATE BLOCK: budget pressure contract failed; regenerate "
            "the budget plan before a paid run"
        )
    elif any("budgetflow_under_target" in violation for violation in violations):
        plan.reasons.append(
            "PRESSURE_GATE WARNING: BudgetFlow projected utilization is below "
            "the target pressure regime; treat the next run as calibration, "
            "not paper evidence"
        )


def _apply_calibration_gate(
    plan: BudgetBindingPlan,
    audit: CalibrationAudit,
) -> None:
    """Apply calibration evidence to the readiness gate.

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
                f"rely on target_utilization budget."
            )
        for rec in audit.recommendations:
            plan.reasons.append(f"CALIBRATION_GATE: {rec}")

    elif confidence == "low":
        plan.reasons.append(
            f"CALIBRATION_GATE WARNING: prior projection MAPE={audit.overall_mape:.1%} "
            f"confidence=low. "
            f"Max error: {audit.max_error_strategy} at {audit.max_error_pct:.1%}. "
            f"Treat the next run as diagnostic calibration evidence, not paper evidence."
        )
        for rec in audit.recommendations:
            plan.reasons.append(f"CALIBRATION_GATE: {rec}")

    else:
        plan.reasons.append(
            f"CALIBRATION_GATE: prior projection MAPE={audit.overall_mape:.1%} "
            f"confidence={confidence}. Max error: {audit.max_error_strategy} "
            f"at {audit.max_error_pct:.1%}."
        )


def _row_is_calibration_eligible(
    row: dict,
    *,
    allow_budget_exhausted: bool = False,
) -> tuple[bool, str]:
    """Check whether a historical JSONL row is clean enough for cost calibration.

    Contaminated rows are forensic-only — they may inform postmortems but
    must not enter cost-per-effort or ModelFit estimation.
    """
    budget_mode = row.get("budget_mode", "")
    score_status = str(row.get("score_status") or "")
    if not score_status:
        return False, "missing_score_status"
    if score_status not in {"pass", "true_fail"}:
        return False, f"not_scoreable:{score_status}"
    harness_trust = str(row.get("harness_trust") or "")
    if harness_trust != "trusted":
        if not harness_trust:
            return False, "harness_trust:missing"
        return False, f"harness_trust:{harness_trust}"

    row_catalog = row.get("catalog") or {}
    catalog_ok, catalog_reason = _row_catalog_compatible(row_catalog)
    if not catalog_ok:
        return False, catalog_reason

    if budget_mode == "frozen_router_caps":
        return False, "budget_asymmetry:frozen_router_caps"

    # Diagnostic catalog with inflated prices (e.g. t3x3 = 3x T3 prices).
    catalog = row_catalog
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
    exit_reason = str(row.get("exit_reason") or "")
    if exit_status in ("BudgetFlowBudgetError",):
        if not (allow_budget_exhausted and _row_is_budget_exhausted(row)):
            return False, f"budget_error:{exit_status}"
    failure_class = str(row.get("failure_class") or "")
    abort_reason = str(row.get("abort_reason") or "")
    exit_owner = str(row.get("exit_owner") or "")
    provider_error_kind = str(row.get("provider_error_kind") or "")
    if (
        failure_class == "infra_fail"
        or "infra" in abort_reason
        or "provider" in abort_reason
        or exit_owner == "provider_error"
        or provider_error_kind
        or "provider" in exit_reason.lower()
    ):
        return False, "infra_or_provider_abort"
    if (
        failure_class == "extract_fail"
        and (
            str(row.get("exit_status") or "") == "FormatError"
            or "format_error" in exit_reason.lower()
            or exit_owner == "parser_protocol"
        )
    ):
        return False, "protocol_or_parser_abort"

    # Successful protocol retries are valid scoreable evidence, but their
    # cost includes a failed formatting/provider turn.  Keep them out of cost
    # calibration so retry instability does not inflate future budget plans.
    if row.get("protocol_retry_used"):
        return False, "protocol_retry_overhead"

    return True, "clean"


def _load_historical_costs(
    jsonl_path: Path,
) -> tuple[dict[str, dict[str, float]], dict[str, int]]:
    """Extract per-strategy per-task total_cost from historical JSONL.

    Returns (costs, exclusion_counts) where exclusion_counts maps
    exclusion_reason -> count of rows filtered out.
    """
    signals = _load_historical_cost_signals(jsonl_path)
    return signals.observed_costs, signals.excluded


def _load_historical_cost_signals(jsonl_path: Path) -> HistoricalCostSignals:
    """Load current cost signals without mixing complete and censored rows."""

    signals = HistoricalCostSignals()
    records = _latest_records_by_strategy_task(jsonl_path)
    for (strategy, instance_id), rec in records.items():
        total_cost = float(rec.get("total_cost") or rec.get("scoreable_cost") or 0.0)
        eligible, reason = _row_is_calibration_eligible(rec, allow_budget_exhausted=True)
        if not eligible:
            signals.excluded[reason] = signals.excluded.get(reason, 0) + 1
            continue
        if _row_is_budget_exhausted(rec):
            signals.censored_task_costs_by_strategy.setdefault(strategy, {})[instance_id] = total_cost
            signals.censored_spend_floor_by_strategy[strategy] = (
                signals.censored_spend_floor_by_strategy.get(strategy, 0.0) + total_cost
            )
            signals.censored_row_counts[strategy] = signals.censored_row_counts.get(strategy, 0) + 1
            continue

        signals.observed_costs.setdefault(strategy, {})[instance_id] = total_cost
    return signals


def _latest_records_by_strategy_task(jsonl_path: Path) -> dict[tuple[str, str], dict]:
    latest: dict[tuple[str, str], tuple[float, int, dict]] = {}
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
            finished_at = float(rec.get("row_finished_at", 0) or 0)
            key = (strategy, instance_id)
            if key not in latest or (finished_at, order) >= (latest[key][0], latest[key][1]):
                latest[key] = (finished_at, order, rec)
    return {key: rec for key, (_finished_at, _order, rec) in latest.items()}


def _row_is_budget_exhausted(row: dict) -> bool:
    fields = (
        row.get("exit_status"),
        row.get("exit_reason"),
        row.get("agent_exit_status"),
        row.get("agent_exit_reason"),
        row.get("failure_class"),
    )
    return any("budget" in str(value).lower() and "exhaust" in str(value).lower() for value in fields)


def _row_catalog_compatible(row_catalog: dict) -> tuple[bool, str]:
    """Current cost observations must use the active catalog units."""

    if not isinstance(row_catalog, dict) or not row_catalog:
        return False, "missing_catalog"
    active_catalog = catalog_source_info()
    row_hash = str(row_catalog.get("catalog_content_hash") or "")
    active_hash = str(active_catalog.get("catalog_content_hash") or "")
    row_revision = str(row_catalog.get("catalog_revision") or "")
    active_revision = str(active_catalog.get("catalog_revision") or "")
    if row_hash and active_hash:
        return (True, "clean") if row_hash == active_hash else (False, "catalog_mismatch")
    if row_revision and active_revision:
        return (True, "clean") if row_revision == active_revision else (False, "catalog_mismatch")
    return False, "missing_catalog"


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
    *,
    fit_overrides: dict[int, float] | None = None,
) -> float:
    """Project cold-start spend pressure for a task with no historical data.

    Cold-start estimates use pre-registered task-effort features. Router plans
    do not provide budget caps to the compiler.
    """
    features = value_features.get(task_id, {})
    difficulty = (
        features.get("bootstrap_difficulty", 30.0)
        if features else 30.0
    )

    return _cold_start_cost_estimate(
        difficulty,
        fit_overrides=fit_overrides,
        fixed_projection_tier=_fixed_projection_tier_for_strategy(strategy),
    )


def _project_strategy_task_costs(
    strategy: str,
    task_ids: list[str],
    value_features: dict[str, dict],
    observed_costs: dict[str, float],
    censored_costs: dict[str, float],
    *,
    fit_overrides: dict[int, float] | None = None,
) -> dict[str, float]:
    scale = _strategy_effort_scale(strategy, observed_costs, value_features, fit_overrides=fit_overrides)
    projected: dict[str, float] = {}
    for task_id in task_ids:
        baseline = _bootstrap_cost_estimate(task_id, strategy, value_features, fit_overrides=fit_overrides) * scale
        observed = observed_costs.get(task_id)
        if observed is not None and observed > 0:
            projected[task_id] = observed
            continue
        censored = censored_costs.get(task_id)
        if censored is not None and censored > 0:
            # A budget-exhausted row is a lower bound on spent cost, not a full
            # completion cost.  Add one task-sized runway estimate so the next
            # cap is not trained to starve the same task again.
            projected[task_id] = censored + baseline
            continue
        projected[task_id] = baseline
    return projected


def _strategy_effort_scale(
    strategy: str,
    observed_costs: dict[str, float],
    value_features: dict[str, dict],
    *,
    fit_overrides: dict[int, float] | None = None,
) -> float:
    ratios: list[float] = []
    for task_id, cost in observed_costs.items():
        baseline = _bootstrap_cost_estimate(task_id, strategy, value_features, fit_overrides=fit_overrides)
        if cost > 0 and baseline > 0:
            ratios.append(cost / baseline)
    if not ratios:
        return 1.0
    ratios.sort()
    return ratios[len(ratios) // 2]


def _prefix_cost_before_final_task(
    task_costs: dict[str, float],
    task_ids: list[str],
) -> float:
    if len(task_ids) <= 1:
        return 0.0
    return sum(float(task_costs.get(task_id, 0.0) or 0.0) for task_id in task_ids[:-1])


def _cold_start_cost_estimate(
    difficulty: float,
    *,
    fit_overrides: dict[int, float] | None = None,
    fixed_projection_tier: int | None = None,
) -> float:
    """Workload reference cold-start estimate when no cost data exists.

    This is a Budget Regime Compiler scale estimate, not a BudgetFlow runtime
    tier decision. It uses a catalog-level reference price near the
    middle/strong boundary and adjusts for workload-level Model Fit when
    available. Pure-tier diagnostic controls may pass ``fixed_projection_tier``
    because their model tier is declared by the control itself, not assigned by
    the compiler.
    """
    input_tokens = max(1, round(difficulty * COLD_START_INPUT_TOKENS_PER_EFFORT))
    output_tokens = max(1, round(difficulty * COLD_START_OUTPUT_TOKENS_PER_EFFORT))

    ordered = sorted(MODEL_CATALOG.configs, key=lambda cfg: cfg.tier)
    if not ordered:
        raise ValueError("model catalog is empty; cannot compile cold-start budget")
    strongest = ordered[-1]
    reference = ordered[1] if len(ordered) >= 3 else ordered[0]
    projection = reference
    if fixed_projection_tier is not None:
        projection = next((cfg for cfg in ordered if cfg.tier == fixed_projection_tier), reference)
    reference_cost = estimate_token_cost(
        projection.backend,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    def _tier_fit(tier: int, fallback: float) -> float:
        if fit_overrides and tier in fit_overrides:
            return max(0.001, fit_overrides[tier])
        return max(0.001, fallback)

    strongest_fit = _tier_fit(strongest.tier, getattr(strongest, "progress_score", 0.001))
    reference_fit = _tier_fit(projection.tier, getattr(projection, "progress_score", 0.001))
    fit_ratio = strongest_fit / max(reference_fit, 0.001)
    turns_multiplier = max(1.0, fit_ratio)
    return reference_cost * turns_multiplier


def _fixed_projection_tier_for_strategy(strategy: str) -> int | None:
    """Return a strategy-declared fixed tier for pure-tier controls only."""
    if strategy in {"all_flash", "bare_t1_baseline", "all_t1_baseline"}:
        return 1
    if strategy in {"bare_t2_baseline", "budget_only_t2", "budget_only_t2_baseline", "all_tier2"}:
        return 2
    if strategy in {"bare_t3_baseline", "all_t3", "all_pro", "all_strongest_model"}:
        return max((cfg.tier for cfg in MODEL_CATALOG.configs), default=3)
    return None


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
    calibrate.add_argument("--value-matrix", default=None, help="value matrix JSON")
    calibrate.add_argument("--model-catalog", default=None, help="model tier catalog JSON")
    calibrate.add_argument("--historical-jsonl", default=None, help="optional clean historical JSONL")
    calibrate.add_argument(
        "--calibration-evidence",
        default=None,
        help="optional read-only calibration audit JSON from one previous diagnostic run",
    )
    calibrate.add_argument(
        "--target-utilization",
        type=float,
        default=None,
        help="generate hard_cap from p75(projected spend) / target utilization",
    )
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
            value_matrix_path=Path(args.value_matrix) if args.value_matrix else None,
            strategies=_strategy_names_from_set(args.strategy_set),
            output_path=Path(args.output),
            target_utilization=args.target_utilization,
            calibration_evidence=(
                CalibrationAudit.from_dict(json.loads(Path(args.calibration_evidence).read_text()))
                if args.calibration_evidence else None
            ),
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

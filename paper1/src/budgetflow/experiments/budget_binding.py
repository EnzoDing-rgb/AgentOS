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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..model_tiers import MODEL_CATALOG, catalog_revision, catalog_path


@dataclass
class BudgetBindingPlan:
    """Code-generated budget plan for a compare run."""

    hard_cap_usd: float
    source: str = "budget_binding_calibrator"
    catalog_revision: str = ""
    catalog_path: str = ""
    historical_source: str = ""
    task_ids: list[str] = field(default_factory=list)
    projected_spend_by_strategy: dict[str, float] = field(default_factory=dict)
    projected_utilization_by_strategy: dict[str, float] = field(default_factory=dict)
    min_viable_budget: float = 0.0
    loose_budget_threshold: float = 0.0
    tight_budget_threshold: float = 0.0
    decision: str = "PASS"
    reasons: list[str] = field(default_factory=list)
    override_reason: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "hard_cap_usd": round(self.hard_cap_usd, 4),
            "source": self.source,
            "catalog_revision": self.catalog_revision,
            "catalog_path": self.catalog_path,
            "historical_source": self.historical_source,
            "task_ids": self.task_ids,
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
        }
        if self.override_reason:
            d["override_reason"] = self.override_reason
        return d

    @classmethod
    def from_dict(cls, d: dict) -> BudgetBindingPlan:
        return cls(
            hard_cap_usd=d["hard_cap_usd"],
            source=d.get("source", "budget_binding_calibrator"),
            catalog_revision=d.get("catalog_revision", ""),
            catalog_path=d.get("catalog_path", ""),
            historical_source=d.get("historical_source", ""),
            task_ids=d.get("task_ids", []),
            projected_spend_by_strategy=d.get("projected_spend_by_strategy", {}),
            projected_utilization_by_strategy=d.get("projected_utilization_by_strategy", {}),
            min_viable_budget=d.get("min_viable_budget", 0.0),
            loose_budget_threshold=d.get("loose_budget_threshold", 0.0),
            tight_budget_threshold=d.get("tight_budget_threshold", 0.0),
            decision=d.get("decision", "PASS"),
            reasons=d.get("reasons", []),
            override_reason=d.get("override_reason", ""),
        )


def calibrate_budget(
    task_ids: list[str],
    *,
    historical_jsonl: Path | None = None,
    frozen_plan_path: Path | None = None,
    value_matrix_path: Path | None = None,
    strategies: tuple[str, ...] = (
        "bare_t2_baseline",
        "bare_t3_baseline",
        "enterprise_router_baseline",
        "budgetflow_same_router",
        "budgetflow_full",
    ),
    output_path: Path | None = None,
    override_reason: str = "",
) -> BudgetBindingPlan:
    """Generate a budget binding plan from historical data and current catalog.

    If no historical JSONL is provided, falls back to bootstrap estimates from
    the value matrix and frozen plan.

    When *override_reason* is set and the frozen cap sum drives the hard cap,
    low projected utilization emits ``PASS_WITH_DIAGNOSTIC_OVERRIDE`` instead
    of ``BLOCK``.  This lets mechanism-diagnostic runs acknowledge the loose
    budget while still being gated by a pre-registered frozen plan.
    """
    plan = BudgetBindingPlan(
        hard_cap_usd=0.0,
        catalog_revision=catalog_revision(),
        catalog_path=str(catalog_path()) if catalog_path() else "python_fallback",
        historical_source=str(historical_jsonl) if historical_jsonl else "bootstrap_estimate",
        task_ids=list(task_ids),
    )

    # ── Load historical per-strategy per-task costs ──────────────────────
    historical: dict[str, dict[str, float]] = {}  # strategy -> {task_id -> cost}
    if historical_jsonl and historical_jsonl.exists():
        historical = _load_historical_costs(historical_jsonl)

    # ── Compute T3 price multiplier for re-normalization ────────────────
    t3_multiplier = _t3_price_multiplier()

    # ── Load frozen plan caps for reference ─────────────────────────────
    frozen_caps: dict[str, float] = {}
    preferred_models: dict[str, str] = {}
    if frozen_plan_path and frozen_plan_path.exists():
        frozen_caps = _load_frozen_caps(frozen_plan_path)
        preferred_models = _load_frozen_preferred_models(frozen_plan_path)

    # ── Estimate zero-history tasks from value matrix ────────────────────
    value_features: dict[str, dict] = {}
    if value_matrix_path and value_matrix_path.exists():
        value_features = _load_value_features(value_matrix_path)

    # ── Project spend per strategy ──────────────────────────────────────
    projected: dict[str, float] = {}
    for strategy in strategies:
        total = 0.0
        for tid in task_ids:
            hist_cost = historical.get(strategy, {}).get(tid)
            if hist_cost is not None:
                # Re-normalize: historical T3 costs × multiplier
                t3_share = _estimate_t3_cost_share(strategy, tid, historical, preferred_models=preferred_models)
                normalized = hist_cost * (1.0 + t3_share * (t3_multiplier - 1.0))
                total += normalized
            else:
                # Zero-history estimate from value matrix bootstrap_difficulty
                total += _bootstrap_cost_estimate(
                    tid, strategy, value_features, historical, t3_multiplier
                )
        projected[strategy] = total

    plan.projected_spend_by_strategy = projected

    # ── Compute thresholds ──────────────────────────────────────────────
    # The budget binds to the frozen-plan strategies (enterprise_router,
    # budgetflow_same_router).  The shared-batch strategies (bare_t2, bare_t3,
    # budgetflow_full) share a common pool.

    # Min viable: enough for the most expensive single strategy to complete
    plan.min_viable_budget = max(projected.values()) if projected else 0.0

    # Frozen cap sum from the plan (pre-registered caps)
    frozen_cap_sum = sum(frozen_caps.get(tid, 0.0) for tid in task_ids)

    # Loose threshold: 2× the max projected spend (budget not binding)
    plan.loose_budget_threshold = plan.min_viable_budget * 2.0

    # Tight threshold: the max projected spend (at edge of viability)
    plan.tight_budget_threshold = plan.min_viable_budget

    # ── Decision logic ──────────────────────────────────────────────────
    # Recommended hard cap: use the frozen cap sum as the binding budget.
    # This keeps symmetry with the enterprise_router / budgetflow_same_router
    # strategies which use per-task frozen caps.
    plan.hard_cap_usd = frozen_cap_sum if frozen_cap_sum > 0 else plan.min_viable_budget

    # Compute utilization at recommended cap
    for strategy in strategies:
        spend = projected.get(strategy, 0.0)
        plan.projected_utilization_by_strategy[strategy] = (
            min(spend / plan.hard_cap_usd, 1.0) if plan.hard_cap_usd > 0 else 0.0
        )

    # Check: budget too loose?
    max_util = max(plan.projected_utilization_by_strategy.values()) if plan.projected_utilization_by_strategy else 0.0
    budget_loose = max_util < 0.15
    if budget_loose and override_reason and frozen_cap_sum > 0:
        plan.decision = "PASS_WITH_DIAGNOSTIC_OVERRIDE"
        plan.override_reason = override_reason
        plan.reasons.append(
            f"max projected utilization {max_util:.1%} < 15% — "
            f"hard_cap=${plan.hard_cap_usd:.2f} is loose, but budget intentionally "
            f"bound to pre-registered frozen plan cap sum for "
            f"enterprise_router/budgetflow_same_router symmetry"
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

    # Check: budget too tight?
    for strategy in strategies:
        spend = projected.get(strategy, 0.0)
        if spend > plan.hard_cap_usd * 1.1:
            plan.decision = "BLOCK"
            plan.reasons.append(
                f"{strategy} projected spend ${spend:.2f} > "
                f"hard_cap ${plan.hard_cap_usd:.2f} — budget too tight"
            )

    # Check: frozen plan consistency
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

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n")

    return plan


# Mapping from historical strategy names to canonical names.
_HISTORICAL_NAME_MAP: dict[str, str] = {
    "bare_strong_model": "bare_t3_baseline",
}


def _load_historical_costs(jsonl_path: Path) -> dict[str, dict[str, float]]:
    """Extract per-strategy per-task total_cost from historical JSONL.

    Historical strategy names are mapped to canonical names via
    _HISTORICAL_NAME_MAP so pre-rename diagnostic data remains usable.
    """
    costs: dict[str, dict[str, float]] = {}
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
            strategy = _HISTORICAL_NAME_MAP.get(strategy, strategy)
            total_cost = d.get("total_cost") or d.get("scoreable_cost") or 0.0
            costs.setdefault(strategy, {})[instance_id] = float(total_cost)
    return costs


def _estimate_t3_cost_share(
    strategy: str,
    task_id: str,
    historical: dict[str, dict[str, float]],
    *,
    preferred_models: dict[str, str] | None = None,
) -> float:
    """Estimate the fraction of cost that came from T3 turns.

    Uses per-strategy heuristics based on routing type.  For frozen-plan
    strategies the T3 share is read from the plan's ``preferred_model``
    field — no task-id hardcoding.
    """
    # Strategies that are 100% T3
    if strategy in ("bare_t3_baseline",):
        return 1.0
    # Strategies that are 0% T3
    if strategy in ("bare_t2_baseline",):
        return 0.0
    # Frozen plan strategies: read preferred_model from the plan
    if strategy in ("enterprise_router_baseline", "budgetflow_same_router"):
        if preferred_models:
            model = preferred_models.get(task_id, "")
            if model == "tier3":
                return 1.0
        return 0.0
    # budgetflow_full: mixed T2/T3, estimate from historical tier proportions
    # Default: assume ~30% T3 cost share for value-aware routing
    return 0.30


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
) -> float:
    """Estimate cost for a task with no historical data.

    Uses bootstrap_difficulty ratio vs known tasks of the same strategy.
    """
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
        # Fallback: estimate from strategy type
        return _fallback_cost_estimate(strategy, difficulty, t3_multiplier)

    median_ratio = sorted(ratios)[len(ratios) // 2]
    estimated = difficulty * median_ratio

    # Apply T3 multiplier if this strategy uses T3
    if strategy == "bare_t3_baseline":
        estimated *= t3_multiplier
    elif strategy == "budgetflow_full":
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
    elif strategy == "budgetflow_full":
        estimated *= (1.0 + 0.30 * (t3_multiplier - 1.0))
    return estimated

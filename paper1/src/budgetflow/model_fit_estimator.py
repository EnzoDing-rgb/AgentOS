"""ModelFit estimation from clean historical JSONL evidence.

Derives per-tier fit/productivity rates from verified outcome and cost/turn
evidence. Budget-exhausted rows are censored runway signals: the observed spend
is not enough, so the derived fit is an upper bound rather than a complete cost
sample.

No ML, no task-id-specific rules, no benchmark-specific logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .model_tiers import MODEL_CATALOG


@dataclass
class ModelFitEvidence:
    """Per-tier ModelFit derived from clean historical runs."""

    tier_fit: dict[int, float]
    source: str = "historical_jsonl"
    confidence: str = "low"
    evidence_tasks: int = 0
    censored_tiers: set[int] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)

    def to_allocation_model_fit(self) -> dict[str, float]:
        """Convert to the keyed form AllocationContext expects."""
        return {f"tier{t}": f for t, f in self.tier_fit.items()}


def estimate_model_fit_from_jsonl(
    jsonl_path: Path,
    task_ids: list[str],
    value_features: dict[str, dict],
) -> ModelFitEvidence:
    """Derive per-tier ModelFit from clean historical JSONL evidence.

    Uses only harness-trusted rows with the current catalog. Completed
    (non-budget-exhausted) rows from single-tier strategies provide direct
    per-tier cost evidence. Budget-exhausted rows are censored upper bounds
    that inform the exhausted tier without becoming complete samples.

    Returns a ModelFitEvidence with per-tier fit rates. Tiers with no
    historical evidence fall back to catalog progress_score.
    """
    task_id_set = set(task_ids)

    # Collect per-tier efficiency observations: tier -> [fit_estimate, ...]
    observed: dict[int, list[float]] = {}
    censored_bounds: dict[int, list[float]] = {}
    evidence_task_ids: set[str] = set()

    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            instance_id = rec.get("instance_id", "")
            if instance_id not in task_id_set:
                continue

            strategy = rec.get("strategy", "")
            tier = _tier_for_strategy(strategy)
            if tier is None:
                continue

            total_cost = float(rec.get("total_cost") or 0)
            if total_cost <= 0:
                continue

            # Only current-catalog rows
            row_catalog = rec.get("catalog") or {}
            if not _catalog_compatible(row_catalog):
                continue

            # Only scoreable outcomes
            score_status = str(rec.get("score_status") or "")
            if score_status not in {"pass", "true_fail"}:
                continue

            # Exclude infra/provider/protocol aborts
            if not _is_clean_run(rec):
                continue

            task_effort = _task_effort_for(value_features, instance_id)
            per_turn = _catalog_per_turn_cost(tier)
            if per_turn <= 0:
                continue

            is_exhausted = _row_is_budget_exhausted(rec)

            # fit = task_effort * per_turn_cost / total_cost
            # Clamp to [0.001, 1.0] — a tier cannot have zero or >100% progress per turn.
            fit_estimate = (task_effort * per_turn) / total_cost
            fit_estimate = max(0.001, min(1.0, fit_estimate))

            if is_exhausted:
                # Censored: true total_cost would be higher, so true fit is lower.
                # This fit_estimate is an UPPER BOUND.
                censored_bounds.setdefault(tier, []).append(fit_estimate)
            else:
                observed.setdefault(tier, []).append(fit_estimate)
                evidence_task_ids.add(instance_id)

    return _build_evidence(observed, censored_bounds, evidence_task_ids)


def _build_evidence(
    observed: dict[int, list[float]],
    censored_bounds: dict[int, list[float]],
    evidence_task_ids: set[str],
) -> ModelFitEvidence:
    """Aggregate per-tier observations into ModelFitEvidence."""
    reasons: list[str] = []
    tier_fit: dict[int, float] = {}
    censored_tiers: set[int] = set()

    # Catalog fallback: progress_score per tier
    catalog_fit: dict[int, float] = {}
    for cfg in MODEL_CATALOG.configs:
        catalog_fit[cfg.tier] = max(0.001, cfg.progress_score)

    all_tiers = sorted(set(list(observed.keys()) + list(censored_bounds.keys()) + list(catalog_fit.keys())))

    for tier in all_tiers:
        obs = observed.get(tier, [])
        cens = censored_bounds.get(tier, [])

        if obs:
            # Use completed observations as the fit estimate. Censored rows are
            # incomplete upper-bound evidence: they lower confidence and are
            # auditable, but a single exhausted task must not overwrite a stable
            # completed cluster from other tasks.
            median_fit = _median(obs)
            if cens:
                min_bound = min(cens)
                censored_tiers.add(tier)
                if len(obs) < 3 and min_bound < median_fit:
                    reasons.append(
                        f"tier{tier}: limited completed evidence; censored upper bound "
                        f"lowers fit from {median_fit:.4f} to ≤{min_bound:.4f}"
                    )
                    median_fit = min_bound
                else:
                    reasons.append(
                        f"tier{tier}: {len(cens)} incomplete censored rows recorded "
                        f"(min upper bound={min_bound:.4f}) without overriding "
                        f"{len(obs)} completed rows"
                    )
            tier_fit[tier] = round(median_fit, 6)
            reasons.append(
                f"tier{tier}: fit={tier_fit[tier]:.4f} from {len(obs)} completed "
                f"+ {len(cens)} censored rows"
            )
        elif cens:
            # Only censored evidence: the true fit is below all observed bounds.
            # Use the minimum bound as the estimate and mark it censored; do not
            # add an extra magic multiplier without calibration evidence.
            min_bound = min(cens)
            tier_fit[tier] = round(max(0.001, min_bound), 6)
            censored_tiers.add(tier)
            reasons.append(
                f"tier{tier}: fit={tier_fit[tier]:.4f} from {len(cens)} censored-only rows "
                f"(min upper bound={min_bound:.4f}; incomplete evidence)"
            )
        else:
            # No evidence — fall back to catalog
            tier_fit[tier] = catalog_fit.get(tier, 0.001)
            reasons.append(
                f"tier{tier}: fit={tier_fit[tier]:.4f} (catalog fallback, no historical evidence)"
            )

    evidence_count = len(evidence_task_ids)
    confidence = "high" if evidence_count >= 3 else "medium" if evidence_count >= 1 else "low"

    return ModelFitEvidence(
        tier_fit=tier_fit,
        source="historical_jsonl",
        confidence=confidence,
        evidence_tasks=evidence_count,
        censored_tiers=censored_tiers,
        reasons=reasons,
    )


def _tier_for_strategy(strategy: str) -> int | None:
    """Infer which tier a single-tier strategy used. Returns None if ambiguous."""
    if strategy in ("bare_t2_baseline", "budget_only_t2", "all_tier2"):
        return 2
    if strategy in ("bare_t3_baseline", "all_t3", "all_pro"):
        return 3
    if strategy in ("all_flash", "bare_t1_baseline"):
        return 1
    return None


def _catalog_per_turn_cost(tier: int) -> float:
    """Estimate per-turn cost for a tier using catalog mean token counts."""
    config = MODEL_CATALOG.config_for(f"tier{tier}")
    if config is None:
        for cfg in MODEL_CATALOG.configs:
            if cfg.tier == tier:
                config = cfg
                break
    if config is None:
        return 0.0
    return (
        config.cost_per_input_token * 2000
        + config.cost_per_output_token * config.mean_output_tokens
    )


def _task_effort_for(value_features: dict[str, dict], task_id: str) -> float:
    """Extract task_effort from value features, defaulting to 30.0."""
    features = value_features.get(task_id, {})
    if not features:
        return 30.0
    return float(features.get("bootstrap_difficulty", 30.0))


def _catalog_compatible(row_catalog: dict) -> bool:
    """Check whether a row's catalog matches the currently loaded catalog."""
    from .model_tiers import catalog_source_info

    if not isinstance(row_catalog, dict) or not row_catalog:
        return False
    active = catalog_source_info()
    row_hash = str(row_catalog.get("catalog_content_hash") or "")
    active_hash = str(active.get("catalog_content_hash") or "")
    if row_hash and active_hash:
        return row_hash == active_hash
    row_rev = str(row_catalog.get("catalog_revision") or "")
    active_rev = str(active.get("catalog_revision") or "")
    if row_rev and active_rev:
        return row_rev == active_rev
    return False


def _is_clean_run(rec: dict) -> bool:
    """Exclude rows with infra/provider/protocol aborts."""
    failure_class = str(rec.get("failure_class") or "")
    abort_reason = str(rec.get("abort_reason") or "")
    exit_owner = str(rec.get("exit_owner") or "")
    provider_error_kind = str(rec.get("provider_error_kind") or "")
    exit_reason = str(rec.get("exit_reason") or "")
    exit_status = str(rec.get("exit_status") or "")
    harness_trust = str(rec.get("harness_trust") or "")

    if harness_trust != "trusted":
        return False
    if failure_class == "infra_fail" or "infra" in abort_reason:
        return False
    if "provider" in abort_reason or exit_owner == "provider_error" or provider_error_kind:
        return False
    if "provider" in exit_reason.lower():
        return False
    if exit_status in ("BudgetFlowBudgetError",):
        # Budget-exhausted is handled separately, not excluded
        pass
    if failure_class == "extract_fail" and (
        exit_status == "FormatError"
        or "format_error" in exit_reason.lower()
        or exit_owner == "parser_protocol"
    ):
        return False
    if rec.get("protocol_retry_used"):
        return False
    return True


def _row_is_budget_exhausted(row: dict) -> bool:
    fields = (
        row.get("exit_status"),
        row.get("exit_reason"),
        row.get("agent_exit_status"),
        row.get("agent_exit_reason"),
        row.get("failure_class"),
    )
    return any(
        "budget" in str(v).lower() and "exhaust" in str(v).lower() for v in fields
    )


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0

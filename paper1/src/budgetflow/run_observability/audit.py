"""Compact audit computation for BudgetFlow run JSONL records."""

from __future__ import annotations

from collections import Counter

from budgetflow.failure_classification import (
    build_verdict,
    classify_failure,
    compute_exit_owner,
    is_score_abort,
    is_score_pass,
    is_score_true_fail,
)
from budgetflow.model_tiers import MODEL_CATALOG, parse_tier_label
from budgetflow.observability import build_harness_trust

from .schema import _routing_memory_source, _routing_memory_used, _routing_prior_task_seen

def _count_tier(backend_picks, tier: int) -> int:
    if not backend_picks:
        return 0
    return sum(1 for p in backend_picks if parse_tier_label(p) == tier)


def _tier_counts(backend_picks) -> dict[int, int]:
    counts: dict[int, int] = {}
    for pick in backend_picks or []:
        tier = _pick_tier(pick)
        if tier > 0:
            counts[tier] = counts.get(tier, 0) + 1
    return counts


# ── Compact audit ────────────────────────────────────────────────────────────

def _pick_tier(pick) -> int:
    """Best-effort tier from a backend_pick string like 'tier2' or 'T2'."""
    return parse_tier_label(pick)


def _has_invoice_accurate_cost(record: dict) -> bool:
    """Check if the record has provider usage for every settled turn."""
    if (
        record.get("usage_source") == "none"
        and record.get("cost_mode") == "no_provider_call"
        and float(record.get("total_cost") or 0.0) == 0.0
    ):
        return True
    if record.get("usage_source") == "provider":
        return True
    traces = record.get("turn_traces")
    if not isinstance(traces, list) or not traces:
        return False
    settled = [trace for trace in traces if isinstance(trace, dict) and trace.get("reservation_settled")]
    if not settled:
        return False
    return all(trace.get("usage_source") == "provider" for trace in settled)


def _cost_mode_counts(records: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        mode = str(record.get("cost_mode") or record.get("usage_source") or "unknown")
        counts[mode] += 1
    return dict(counts)


def _t3_id(records: list[dict]) -> int:
    observed = [
        parse_tier_label(pick)
        for record in records
        for pick in (record.get("backend_picks") or [])
    ]
    configured = [cfg.tier for cfg in MODEL_CATALOG.configs]
    return max([tier for tier in observed + configured if tier > 0], default=0)


def _trace_productive(trace: dict) -> bool | None:
    if trace.get("error_type") or trace.get("parser_error_type"):
        return False
    signals: list[bool | None] = []
    if "action_progress_state" in trace:
        signals.append(_progress_state_productive(str(trace.get("action_progress_state"))))
    if "progress_state" in trace:
        signals.append(_progress_state_productive(str(trace.get("progress_state"))))
    if "action_has_progress" in trace:
        signals.append(_optional_bool(trace.get("action_has_progress")))
    if "has_progress" in trace:
        signals.append(_optional_bool(trace.get("has_progress")))
    if True in signals:
        return True
    if any(signal is None for signal in signals):
        return None
    return False if signals else None


def _progress_state_productive(state: str) -> bool | None:
    if state == "progress":
        return True
    if state == "no_progress":
        return False
    return None


def _optional_bool(value) -> bool | None:
    if value is True:
        return True
    if value is False:
        return False
    return None


def _trace_tier(trace: dict) -> int:
    """Actual tier used by this turn.

    ``backend_tier`` is the execution tier. ``final_backend`` is only a legacy
    fallback for old traces that did not persist backend_tier; taking max()
    across both can misattribute downgraded/fallback turns to the strongest
    model.
    """
    backend_tier = int(trace.get("backend_tier") or 0)
    if backend_tier > 0:
        return backend_tier
    return parse_tier_label(trace.get("final_backend") or "")


def _t3_productivity(records: list[dict], t3_tier: int) -> dict[str, dict]:
    by_strategy: dict[str, dict] = {}
    if t3_tier <= 0:
        return by_strategy
    for record in records:
        strat = str(record.get("strategy", "unknown"))
        stats = by_strategy.setdefault(
            strat,
            {
                "t3_turns": 0,
                "t3_productive_turns": 0,
                "t3_no_progress_turns": 0,
                "t3_unknown_progress_turns": 0,
                "t3_cost": 0.0,
                "t3_no_progress_cost": 0.0,
                "t3_unknown_progress_cost": 0.0,
            },
        )
        traces = record.get("turn_traces") or []
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            tier = _trace_tier(trace)
            if tier < t3_tier:
                continue
            cost = float(trace.get("billable_cost") or trace.get("actual_cost") or 0.0)
            useful = _trace_productive(trace)
            stats["t3_turns"] += 1
            stats["t3_cost"] += cost
            if useful is True:
                stats["t3_productive_turns"] += 1
            elif useful is False:
                stats["t3_no_progress_turns"] += 1
                stats["t3_no_progress_cost"] += cost
            else:
                stats["t3_unknown_progress_turns"] += 1
                stats["t3_unknown_progress_cost"] += cost
    for stats in by_strategy.values():
        total = max(int(stats["t3_turns"]), 1)
        stats["t3_productive_rate"] = stats["t3_productive_turns"] / total
    return by_strategy


def _t3_source(trace: dict) -> str:
    explicit = str(trace.get("routing_trigger_source") or "")
    if explicit:
        return explicit
    if trace.get("value_triggered_escalation_active") or trace.get("value_triggered_escalation_opened"):
        return "value_triggered"
    if trace.get("strongest_starter_applied"):
        return "starter_memory"
    if trace.get("rescue_window_opened") or int(trace.get("rescue_window_remaining") or 0) > 0:
        return "evidence_triggered"
    return "routing_or_progress"


def _t3_source_breakdown(records: list[dict], t3_tier: int) -> dict[str, dict[str, dict]]:
    by_strategy: dict[str, dict[str, dict]] = {}
    if t3_tier <= 0:
        return by_strategy
    for record in records:
        strat = str(record.get("strategy", "unknown"))
        by_source = by_strategy.setdefault(strat, {})
        traces = record.get("turn_traces") or []
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            tier = _trace_tier(trace)
            if tier < t3_tier:
                continue
            source = _t3_source(trace)
            stats = by_source.setdefault(
                source,
                {
                    "t3_turns": 0,
                    "t3_productive_turns": 0,
                    "t3_no_progress_turns": 0,
                    "t3_unknown_progress_turns": 0,
                    "t3_no_progress_cost": 0.0,
                    "t3_unknown_progress_cost": 0.0,
                },
            )
            productive = _trace_productive(trace)
            stats["t3_turns"] += 1
            if productive is True:
                stats["t3_productive_turns"] += 1
            elif productive is False:
                stats["t3_no_progress_turns"] += 1
                stats["t3_no_progress_cost"] += float(
                    trace.get("billable_cost") or trace.get("actual_cost") or 0.0
                )
            else:
                stats["t3_unknown_progress_turns"] += 1
                stats["t3_unknown_progress_cost"] += float(
                    trace.get("billable_cost") or trace.get("actual_cost") or 0.0
                )
    for by_source in by_strategy.values():
        for stats in by_source.values():
            stats["t3_productive_rate"] = stats["t3_productive_turns"] / max(int(stats["t3_turns"]), 1)
    return by_strategy


def _mechanism_isolation_delta(by_strategy: dict[str, dict]) -> dict:
    # Mechanism-first delta: BudgetFlow mechanism vs enterprise router baseline.
    # Both use the same frozen router plan; the only difference is the
    # execution mechanism (shared ledger, reservation/settlement, stop-loss).
    # Only computed when all three mainline strategies are present.
    mechanism = by_strategy.get("budgetflow_same_enterprise_router")
    baseline = by_strategy.get("enterprise_router_baseline")
    bare = by_strategy.get("bare_t3_baseline")
    if not mechanism or not baseline:
        return {}
    delta = {
        "mechanism_strategy": "BudgetFlow Same Router",
        "baseline_strategy": "Enterprise Router Baseline",
        "delta_pass": int(mechanism.get("pass", 0)) - int(baseline.get("pass", 0)),
        "delta_cost": float(mechanism.get("cost", 0.0)) - float(baseline.get("cost", 0.0)),
        "delta_yield": (
            float(mechanism.get("yield_score", 0.0))
            - float(baseline.get("yield_score", 0.0))
        ),
        "delta_yield_coverage": (
            float(mechanism.get("yield_coverage", 0.0))
            - float(baseline.get("yield_coverage", 0.0))
        ),
        "delta_yield_per_dollar": (
            float(mechanism.get("yield_per_dollar", 0.0))
            - float(baseline.get("yield_per_dollar", 0.0))
        ),
        "delta_yield_per_total_dollar": (
            float(mechanism.get("yield_per_total_dollar", 0.0))
            - float(baseline.get("yield_per_total_dollar", 0.0))
        ),
    }
    if bare:
        delta["bare_t3_pass"] = int(bare.get("pass", 0))
        delta["bare_t3_cost"] = float(bare.get("cost", 0.0))
        delta["bare_t3_yield"] = float(bare.get("yield_score", 0.0))
    return delta


def _decision_issues(record: dict) -> list[str]:
    issues: list[str] = []
    if record.get("task_value") is None:
        issues.append("missing_value")
    if not (record.get("value_source") or record.get("task_value_source_class")):
        issues.append("missing_value_source")
    if record.get("total_cost") is None:
        issues.append("missing_cost")
    has_row_cost_confidence = (
        record.get("usage_source") == "none"
        and record.get("cost_mode") == "no_provider_call"
        and float(record.get("total_cost") or 0.0) == 0.0
    )
    if not (
        has_row_cost_confidence
        or record.get("budget_prior_confidence")
        or record.get("cost_source")
        or _trace_has_field(record, "cost_estimate_confidence")
        or _trace_has_field(record, "cost_source")
    ):
        issues.append("missing_cost_confidence")

    traces = record.get("turn_traces")
    has_policy_decision = False
    has_provider_error = False
    if isinstance(traces, list):
        has_policy_decision = any(
            isinstance(trace, dict) and bool(trace.get("policy_decision"))
            for trace in traces
        )
        has_provider_error = any(
            isinstance(trace, dict)
            and bool(trace.get("error_type") or trace.get("provider_status_code"))
            for trace in traces
        )
    if int(record.get("turn_trace_count") or 0) > 0 and not has_policy_decision:
        issues.append("missing_policy_decision")
    if has_provider_error:
        issues.append("provider_error")

    if record.get("policy_memory_enabled") and not _routing_memory_source(record):
        issues.append("memory_enabled_missing_source")

    trust = build_harness_trust(record)
    if trust.get("severity") == "blocking":
        issues.append("harness_blocking")
    return issues


def _decision_issue_counts(records: list[dict]) -> dict[str, int]:
    counts: Counter = Counter()
    for record in records:
        counts.update(_decision_issues(record))
    return dict(counts.most_common())


def _trace_has_field(record: dict, field: str) -> bool:
    traces = record.get("turn_traces")
    if not isinstance(traces, list):
        return False
    return any(isinstance(trace, dict) and bool(trace.get(field)) for trace in traces)


_DECISION_ISSUE_AREA = {
    "missing_value": "value",
    "missing_value_source": "value",
    "missing_cost": "cost",
    "missing_cost_confidence": "cost",
    "missing_policy_decision": "routing",
    "provider_error": "provider",
    "memory_enabled_missing_source": "memory",
    "harness_blocking": "verifier",
}


_STRATEGY_REPORT_ORDER = {
    "bare_t3_baseline": 0,
    "enterprise_router_baseline": 1,
    "budgetflow_same_enterprise_router": 2,
    "budget_only_baseline": 10,
    "budgetflow_task_level": 11,
    "budgetflow_segment": 12,
}


def _strategy_report_sort_key(strategy: str) -> tuple[int, str]:
    return (_STRATEGY_REPORT_ORDER.get(strategy, 100), strategy)


def _decision_area_counts(records: list[dict]) -> dict[str, int]:
    counts: Counter = Counter()
    for record in records:
        for issue in _decision_issues(record):
            counts[_DECISION_ISSUE_AREA.get(issue, "runtime")] += 1
    return dict(counts.most_common())


_FRONTIER_SCORE_FIELDS = (
    "fit_gain",
    "marginal_yield_per_dollar",
    "budget_pressure_threshold",
    "planned_task_budget",
    "budget_allows_strongest",
    "has_trusted_model_fit",
)


def _numeric(value) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _frontier_diagnostics(records: list[dict]) -> dict[str, dict]:
    """Summarize frontier/model-fit signals used by routing decisions.

    This is intentionally diagnostic-only. It does not reinterpret outcomes or
    tune routing; it surfaces whether BudgetFlow had enough signal to justify
    Strongest Model use.
    """
    by_strategy: dict[str, dict] = {}
    for record in records:
        strategy = str(record.get("strategy") or "unknown")
        traces = record.get("turn_traces") or []
        if not isinstance(traces, list):
            traces = []

        source = str(record.get("model_fit_source") or "")
        confidence = str(record.get("model_fit_confidence") or "")
        has_model_fit_meta = bool(source or confidence or record.get("model_fit_active") is not None)
        has_frontier_trace = any(
            isinstance(trace, dict)
            and (
                trace.get("tier_frontier_score") is not None
                or trace.get("tier_frontier_active") is not None
                or trace.get("max_tier_before_frontier") is not None
                or trace.get("max_tier_after_frontier") is not None
            )
            for trace in traces
        )
        has_policy_scores = any(
            isinstance(trace, dict)
            and isinstance(trace.get("policy_decision"), dict)
            and isinstance(trace["policy_decision"].get("scores"), dict)
            and any(field in trace["policy_decision"]["scores"] for field in _FRONTIER_SCORE_FIELDS)
            for trace in traces
        )
        if not (has_model_fit_meta or has_frontier_trace or has_policy_scores):
            continue

        stats = by_strategy.setdefault(
            strategy,
            {
                "records": 0,
                "model_fit_sources": Counter(),
                "model_fit_confidence": Counter(),
                "model_fit_active_records": 0,
                "trace_count": 0,
                "frontier_scores": [],
                "frontier_allow_turns": 0,
                "frontier_block_turns": 0,
                "frontier_unknown_turns": 0,
                "max_tier_opened_turns": 0,
                "max_tier_unchanged_turns": 0,
                "max_tier_closed_turns": 0,
                "strongest_vs_reference_cost_ratios": [],
                "strongest_progress_deltas": [],
                "decision_reasons": Counter(),
                "decision_backends": Counter(),
                "score_fields": {field: [] for field in _FRONTIER_SCORE_FIELDS},
            },
        )
        stats["records"] += 1
        if source:
            stats["model_fit_sources"][source] += 1
        if confidence:
            stats["model_fit_confidence"][confidence] += 1
        if record.get("model_fit_active"):
            stats["model_fit_active_records"] += 1

        for trace in traces:
            if not isinstance(trace, dict):
                continue
            score = _numeric(trace.get("tier_frontier_score"))
            before = _numeric(trace.get("max_tier_before_frontier"))
            after = _numeric(trace.get("max_tier_after_frontier"))
            policy_decision = trace.get("policy_decision")
            policy_scores = {}
            has_trace_signal = (
                score is not None
                or before is not None
                or after is not None
                or trace.get("tier_frontier_active") is not None
            )
            if isinstance(policy_decision, dict):
                reason = str(policy_decision.get("reason") or "")
                backend = str(policy_decision.get("backend") or "")
                if reason:
                    stats["decision_reasons"][reason] += 1
                if backend:
                    stats["decision_backends"][backend] += 1
                if isinstance(policy_decision.get("scores"), dict):
                    policy_scores = policy_decision["scores"]
                    for field in _FRONTIER_SCORE_FIELDS:
                        value = _numeric(policy_scores.get(field))
                        if value is not None:
                            stats["score_fields"][field].append(value)
            if not has_trace_signal and not policy_scores:
                continue

            stats["trace_count"] += 1
            if score is None:
                stats["frontier_unknown_turns"] += 1
            else:
                stats["frontier_scores"].append(score)
                if score < 2.0:
                    stats["frontier_allow_turns"] += 1
                else:
                    stats["frontier_block_turns"] += 1
            if before is not None and after is not None:
                if after > before:
                    stats["max_tier_opened_turns"] += 1
                elif after == before:
                    stats["max_tier_unchanged_turns"] += 1
                else:
                    stats["max_tier_closed_turns"] += 1
            ratio = _numeric(trace.get("strongest_vs_reference_cost_ratio"))
            if ratio is not None:
                stats["strongest_vs_reference_cost_ratios"].append(ratio)
            progress_delta = trace.get("strongest_progress_delta")
            if isinstance(progress_delta, dict):
                for value in progress_delta.values():
                    numeric = _numeric(value)
                    if numeric is not None:
                        stats["strongest_progress_deltas"].append(numeric)

    result: dict[str, dict] = {}
    for strategy, stats in by_strategy.items():
        score_fields = {
            f"avg_{field}": _average(values)
            for field, values in stats["score_fields"].items()
            if values
        }
        result[strategy] = {
            "records": stats["records"],
            "model_fit_sources": dict(stats["model_fit_sources"].most_common()),
            "model_fit_confidence": dict(stats["model_fit_confidence"].most_common()),
            "model_fit_active_records": stats["model_fit_active_records"],
            "trace_count": stats["trace_count"],
            "frontier_allow_turns": stats["frontier_allow_turns"],
            "frontier_block_turns": stats["frontier_block_turns"],
            "frontier_unknown_turns": stats["frontier_unknown_turns"],
            "max_tier_opened_turns": stats["max_tier_opened_turns"],
            "max_tier_unchanged_turns": stats["max_tier_unchanged_turns"],
            "max_tier_closed_turns": stats["max_tier_closed_turns"],
            "avg_frontier_score": _average(stats["frontier_scores"]),
            "min_frontier_score": min(stats["frontier_scores"]) if stats["frontier_scores"] else 0.0,
            "max_frontier_score": max(stats["frontier_scores"]) if stats["frontier_scores"] else 0.0,
            "avg_strongest_vs_reference_cost_ratio": _average(stats["strongest_vs_reference_cost_ratios"]),
            "avg_strongest_progress_delta": _average(stats["strongest_progress_deltas"]),
            "decision_reasons": dict(stats["decision_reasons"].most_common()),
            "decision_backends": dict(stats["decision_backends"].most_common()),
            **score_fields,
        }
    return result


def _task_set_metrics(records: list[dict]) -> dict[str, dict[str, dict[str, dict]]]:
    grouped: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for record in records:
        kind = str(record.get("task_set_kind") or "unknown")
        task_set = str(record.get("task_set") or "unknown")
        strategy = str(record.get("strategy") or "unknown")
        grouped.setdefault(kind, {}).setdefault(task_set, {}).setdefault(strategy, []).append(record)

    result: dict[str, dict[str, dict[str, dict]]] = {}
    for kind, by_set in grouped.items():
        result[kind] = {}
        for task_set, by_strategy in by_set.items():
            result[kind][task_set] = {}
            for strategy, rows in by_strategy.items():
                scoreable_rows = [row for row in rows if not is_score_abort(row)]
                cost = sum(float(row.get("total_cost") or 0.0) for row in scoreable_rows)
                abort_cost = sum(float(row.get("total_cost") or 0.0) for row in rows if is_score_abort(row))
                resolved_value = sum(float(row.get("resolved_value") or 0.0) for row in scoreable_rows)
                task_value = sum(float(row.get("task_value") or 1.0) for row in scoreable_rows)
                result[kind][task_set][strategy] = {
                    "rows": len(rows),
                    "pass": sum(1 for row in rows if is_score_pass(row)),
                    "true_fail": sum(1 for row in rows if is_score_true_fail(row)),
                    "abort": sum(1 for row in rows if is_score_abort(row)),
                    "cost": cost,
                    "abort_cost": abort_cost,
                    "yield_score": resolved_value,
                    "yield_coverage": resolved_value / task_value if task_value > 0 else 0.0,
                    "yield_per_dollar": resolved_value / cost if cost > 0 else 0.0,
                }
    return result


def _first_t3_turn(record: dict, t3_tier: int) -> int | None:
    """Return the 0-indexed turn when T3 was first used, or None if never."""
    picks = record.get("backend_picks") or []
    for i, pick in enumerate(picks):
        if parse_tier_label(pick) >= t3_tier:
            return i
    return None


def _first_useful_action_turn(record: dict) -> int | None:
    """Return the turn index of the first trace with a useful action, or None."""
    traces = record.get("turn_traces") or []
    if not isinstance(traces, list):
        return None
    for i, trace in enumerate(traces):
        if not isinstance(trace, dict):
            continue
        if _trace_productive(trace) is True:
            return i
    return None


def _max_no_progress_streak(record: dict) -> int:
    """Max consecutive turns without useful progress."""
    traces = record.get("turn_traces") or []
    if not isinstance(traces, list):
        return 0
    max_streak = 0
    current = 0
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        productive = _trace_productive(trace)
        if productive is True:
            current = 0
        elif productive is False:
            current += 1
            max_streak = max(max_streak, current)
    return max_streak


def _first_non_empty_trace_value(record: dict, *fields: str) -> str:
    for trace in record.get("turn_traces") or []:
        if not isinstance(trace, dict):
            continue
        for field in fields:
            value = trace.get(field)
            if value not in (None, "", {}, []):
                return str(value)
    return ""


def _last_non_empty_trace_value(record: dict, *fields: str) -> str:
    traces = record.get("turn_traces") or []
    if not isinstance(traces, list):
        return ""
    for trace in reversed(traces):
        if not isinstance(trace, dict):
            continue
        for field in fields:
            value = trace.get(field)
            if value not in (None, "", {}, []):
                return str(value)
    return ""


def _first_policy_decision_field(record: dict, field: str) -> str:
    for trace in record.get("turn_traces") or []:
        if not isinstance(trace, dict):
            continue
        decision = trace.get("policy_decision")
        if isinstance(decision, dict):
            value = decision.get(field)
            if value not in (None, "", {}, []):
                return str(value)
    return ""


def _harness_trust_row(record: dict) -> dict:
    trust = build_harness_trust(record)
    return {
        "harness_trust": str(trust.get("harness_trust") or ""),
        "harness_owner": str(trust.get("harness_owner") or ""),
        "harness_severity": str(trust.get("severity") or ""),
        "harness_evidence_complete": bool(
            (record.get("harness_evidence") or {}).get("evidence_complete", False)
        ),
    }


def _per_task_comparison(records: list[dict], t3_tier: int) -> list[dict]:
    """Build per-instance_id cross-policy comparison rows.

    One row per (instance_id, strategy) with fields that explain
    *why* one policy won or lost relative to others on the same task.
    """
    by_task: dict[str, dict[str, dict]] = {}
    for record in records:
        iid = str(record.get("instance_id") or "")
        strat = str(record.get("strategy") or "unknown")
        if iid not in by_task:
            by_task[iid] = {}
        traces = record.get("turn_traces") or []
        first_trace = traces[0] if isinstance(traces, list) and traces else {}
        picks = record.get("backend_picks") or []
        first_pick = picks[0] if picks else "?"
        first_tier = parse_tier_label(first_pick) if first_pick != "?" else 0
        trust = _harness_trust_row(record)

        by_task[iid][strat] = {
            "instance_id": iid,
            "strategy": strat,
            "resolved": is_score_pass(record),
            "score_status": str(record.get("score_status") or ""),
            "cost": float(record.get("total_cost") or 0),
            "task_value": float(record.get("task_value") or 1.0),
            "yield_score": float(record.get("resolved_value") or 0.0),
            "turns": int(record.get("llm_turns") or 0),
            "first_backend": str(first_pick),
            "first_tier": first_tier,
            "first_segment": str(first_trace.get("workflow_segment") or "?"),
            "frozen_plan_name": str(record.get("frozen_plan_name") or ""),
            "frozen_plan_preferred_model": str(record.get("frozen_plan_preferred_model") or ""),
            "frozen_plan_priority": record.get("frozen_plan_priority"),
            "first_router_branch": _first_non_empty_trace_value(record, "router_branch"),
            "last_router_reason": _last_non_empty_trace_value(record, "router_reason"),
            "policy_type": _first_non_empty_trace_value(record, "policy_type"),
            "policy_name": _first_non_empty_trace_value(record, "policy_name"),
            "memory_mode": _first_non_empty_trace_value(record, "memory_mode"),
            "policy_backend": _first_policy_decision_field(record, "backend"),
            "policy_reason": _first_policy_decision_field(record, "reason"),
            "routing_learned_action": str(record.get("routing_learned_action") or ""),
            "routing_learned_action_segment": str(record.get("routing_learned_action_segment") or ""),
            "routing_repair_learned_action": str(record.get("routing_repair_learned_action") or ""),
            "routing_repair_learned_action_segment": str(record.get("routing_repair_learned_action_segment") or ""),
            "routing_imitation_active": bool(record.get("routing_imitation_active")),
            "routing_imitation_source": str(record.get("routing_imitation_source") or ""),
            "cost_source": str(record.get("cost_source") or _first_non_empty_trace_value(record, "cost_source")),
            "cost_estimate_source": _first_non_empty_trace_value(record, "cost_estimate_source"),
            "provider": _first_non_empty_trace_value(record, "provider"),
            "provider_status_code": _first_non_empty_trace_value(record, "provider_status_code"),
            "parser_error_type": _first_non_empty_trace_value(record, "parser_error_type"),
            "protocol": _first_non_empty_trace_value(record, "protocol"),
            "parser": _first_non_empty_trace_value(record, "parser"),
            "first_t3_turn": _first_t3_turn(record, t3_tier),
            "first_useful_action": _first_useful_action_turn(record),
            "max_no_progress_streak": _max_no_progress_streak(record),
            "no_patch": not bool(record.get("patch_extracted")),
            "failure_class": str(record.get("failure_class") or "pass"),
            "failure_subtype": str(record.get("failure_subtype") or ""),
            **trust,
            "exit_status": str(record.get("exit_status") or ""),
        }
    return [
        row
        for iid in sorted(by_task)
        for strat in sorted(by_task[iid], key=_strategy_report_sort_key)
        for row in [by_task[iid][strat]]
    ]


def build_compact_audit(records: list[dict]) -> dict:
    """Build a high-density audit summary from JSONL records.

    Returns a dict suitable for format_compact_audit().
    """
    total = len(records)
    resolved = sum(1 for r in records if is_score_pass(r))
    failed = sum(1 for r in records if is_score_true_fail(r))
    aborted = sum(1 for r in records if is_score_abort(r))
    total_cost = sum(float(r.get("total_cost") or 0) for r in records)
    scoreable_cost = sum(float(r.get("total_cost") or 0) for r in records if not is_score_abort(r))
    abort_cost = total_cost - scoreable_cost
    verdicts = {id(r): build_verdict(r) for r in records}
    t3_tier = _t3_id(records)
    t3_stats = _t3_productivity(records, t3_tier)
    t3_sources = _t3_source_breakdown(records, t3_tier)
    value_profiles = {
        str(record.get("task_value_profile") or "equal")
        for record in records
    }
    value_objectives = {
        str(record.get("value_objective") or "")
        for record in records
        if record.get("value_objective")
    }
    value_profile = next(iter(value_profiles)) if len(value_profiles) == 1 else "mixed"
    value_objective = next(iter(value_objectives)) if len(value_objectives) == 1 else "mixed" if value_objectives else ""

    suspicious = sum(
        1 for r in records
        if r.get("harness_resolved") and not (r.get("harness_evidence") or {}).get("evidence_complete", False)
    )
    no_trace = sum(1 for r in records if int(r.get("turn_trace_count") or 0) <= 0)

    # Per-strategy stats
    by_strategy: dict[str, dict] = {}
    for r in records:
        strat = str(r.get("strategy", "unknown"))
        if strat not in by_strategy:
            by_strategy[strat] = {
                "total": 0, "pass": 0, "fail": 0, "abort": 0,
                "cost": 0.0, "abort_cost": 0.0, "turns": 0, "tier_turns": {},
                "resolved_value": 0.0, "task_value": 0.0,
                "suspicious": 0, "no_trace": 0,
                "tasks": set(),
            }
        s = by_strategy[strat]
        s["total"] += 1
        row_cost = float(r.get("total_cost") or 0)
        if is_score_abort(r):
            s["abort_cost"] += row_cost
        else:
            s["cost"] += row_cost
            s["resolved_value"] += float(r.get("resolved_value") or 0.0)
            s["task_value"] += float(r.get("task_value") or 1.0)
        turns = int(r.get("llm_turns") or 0)
        s["turns"] += turns
        picks = r.get("backend_picks") or []
        for tier, count in _tier_counts(picks).items():
            s["tier_turns"][tier] = s["tier_turns"].get(tier, 0) + count
        s["tasks"].add(r.get("instance_id", "?"))
        if is_score_pass(r):
            s["pass"] += 1
        elif is_score_true_fail(r):
            s["fail"] += 1
        else:
            s["abort"] += 1
        if r.get("harness_resolved") and not (r.get("harness_evidence") or {}).get("evidence_complete", False):
            s["suspicious"] += 1
        if int(r.get("turn_trace_count") or 0) <= 0:
            s["no_trace"] += 1

    # Common-task set: tasks that every strategy attempted
    all_task_sets = [s["tasks"] for s in by_strategy.values()]
    common_tasks = set.intersection(*all_task_sets) if all_task_sets else set()

    # Per-strategy common-task stats
    common_stats: dict[str, dict] = {}
    for strat, s in by_strategy.items():
        ct_recs = [r for r in records if r.get("strategy") == strat and r.get("instance_id") in common_tasks]
        ct_cost = sum(float(r.get("total_cost") or 0) for r in ct_recs if not is_score_abort(r))
        ct_pass = sum(1 for r in ct_recs if is_score_pass(r))
        ct_fail = sum(1 for r in ct_recs if is_score_true_fail(r))
        ct_abort = sum(1 for r in ct_recs if is_score_abort(r))
        ct_tiers: dict[int, int] = {}
        for r in ct_recs:
            for tier, count in _tier_counts(r.get("backend_picks") or []).items():
                ct_tiers[tier] = ct_tiers.get(tier, 0) + count
        common_stats[strat] = {
            "tasks": len(ct_recs), "pass": ct_pass, "fail": ct_fail, "abort": ct_abort,
            "cost": ct_cost, "tier_turns": dict(sorted(ct_tiers.items())),
            "t2": ct_tiers.get(2, 0), "t3": ct_tiers.get(3, 0),
        }

    # Failure axis / class counts
    fail_classes = Counter(
        classify_failure(r)
        for r in records if is_score_true_fail(r)
    )
    fail_exits = Counter(
        str(r.get("exit_status") or "unknown")
        for r in records if is_score_true_fail(r)
    )

    # Failure subtypes (020)
    fail_subtypes = Counter(
        str(verdicts[id(r)].get("failure_subtype") or "unknown")
        for r in records if is_score_true_fail(r)
    )
    stored_verdict_mismatches = 0
    for r in records:
        verdict = verdicts[id(r)]
        for stored_key, recomputed_key in (
            ("verdict_axis", "verdict_axis"),
            ("failure_owner", "failure_owner"),
            ("failure_stage", "failure_stage"),
            ("failure_subtype", "failure_subtype"),
        ):
            stored = r.get(stored_key)
            if stored not in (None, "") and str(stored) != str(verdict.get(recomputed_key)):
                stored_verdict_mismatches += 1
                break

    # Invoice accuracy: check if at least one record has provider actual cost
    invoice_accurate = any(_has_invoice_accurate_cost(r) for r in records)

    # PolicyMemory detection from standardized current-schema records.
    policy_memory_used = any(_routing_memory_used(r) for r in records)
    policy_memory_source = ""
    prior_records = 0
    memory_filtering_summary: dict | None = None
    if policy_memory_used:
        for r in records:
            source = _routing_memory_source(r)
            if source:
                policy_memory_source = source
                break
        prior_records = round(max((_routing_prior_task_seen(r) for r in records), default=0.0) or 0.0, 2)
        # Collect memory filtering summary from the first record that has it
        for r in records:
            mfs = r.get("memory_filtering")
            if isinstance(mfs, dict):
                memory_filtering_summary = mfs
                break

    # StagnationExit PASS rate
    stag_pass = sum(
        1 for r in records
        if is_score_pass(r) and str(r.get("exit_status") or "").startswith("Stagnation")
    )

    # Failure owner / verdict axis counts
    owner_counts: dict[str, int] = {}
    axis_counts: dict[str, int] = {}
    for r in records:
        verdict = verdicts[id(r)]
        owner = str(verdict.get("failure_owner") or "")
        axis = str(verdict.get("verdict_axis") or "")
        if owner:
            owner_counts[owner] = owner_counts.get(owner, 0) + 1
        if axis:
            axis_counts[axis] = axis_counts.get(axis, 0) + 1

    # Harness trust audit
    trust_counts: dict[str, int] = {}
    ht_owner_counts: dict[str, int] = {}
    ht_severity_counts: dict[str, int] = {}
    for r in records:
        ht = build_harness_trust(r)
        trust_counts[ht["harness_trust"]] = trust_counts.get(ht["harness_trust"], 0) + 1
        ho = ht["harness_owner"]
        if ho != "none":
            ht_owner_counts[ho] = ht_owner_counts.get(ho, 0) + 1
        sev = ht.get("severity", "")
        if sev and sev != "none":
            ht_severity_counts[sev] = ht_severity_counts.get(sev, 0) + 1

    strategy_metrics = {
        strat: {
            "total": s["total"], "pass": s["pass"], "fail": s["fail"],
            "cost": s["cost"], "abort_cost": s["abort_cost"],
            "scoreable_cost": s["cost"],
            "total_spend": s["cost"] + s["abort_cost"],
            "avg_turns": s["turns"] / max(s["total"], 1),
            "resolved_value": s["resolved_value"],
            "total_task_value": s["task_value"],
            "yield_score": s["resolved_value"],
            "yield_coverage": (
                s["resolved_value"] / s["task_value"] if s["task_value"] > 0 else 0.0
            ),
            "yield_per_dollar": (
                s["resolved_value"] / s["cost"] if s["cost"] > 0 else 0.0
            ),
            "yield_per_scoreable_dollar": (
                s["resolved_value"] / s["cost"] if s["cost"] > 0 else 0.0
            ),
            "yield_per_total_dollar": (
                s["resolved_value"] / (s["cost"] + s["abort_cost"])
                if (s["cost"] + s["abort_cost"]) > 0 else 0.0
            ),
            "tier_turns": dict(sorted(s["tier_turns"].items())),
            "t1_turns": s["tier_turns"].get(1, 0),
            "t2_turns": s["tier_turns"].get(2, 0),
            "t3_turns": s["tier_turns"].get(3, 0),
            "t3_share": s["tier_turns"].get(3, 0) / max(sum(s["tier_turns"].values()), 1),
            "suspicious": s["suspicious"], "no_trace": s["no_trace"],
            "abort": s["abort"],
        }
        for strat, s in by_strategy.items()
    }

    return {
        "total": total,
        "pass": resolved,
        "fail": failed,
        "abort": aborted,
        "total_cost": total_cost,
        "scoreable_cost": scoreable_cost,
        "abort_cost": abort_cost,
        "suspicious": suspicious,
        "no_trace": no_trace,
        "stagnation_pass": stag_pass,
        "value_profile": value_profile,
        "value_objective": value_objective,
        "t3_tier": t3_tier,
        "t3_productivity": t3_stats,
        "t3_source_breakdown": t3_sources,
        "by_strategy": strategy_metrics,
        "common_task_count": len(common_tasks),
        "common_stats": common_stats,
        "mechanism_isolation_delta": _mechanism_isolation_delta(strategy_metrics),
        "fail_classes": dict(fail_classes.most_common()),
        "fail_exits": dict(fail_exits.most_common()),
        "fail_subtypes": dict(fail_subtypes.most_common()),
        "stored_verdict_mismatches": stored_verdict_mismatches,
        "invoice_accurate": invoice_accurate,
        "cost_modes": _cost_mode_counts(records),
        "canonical_cost_available": total > 0,
        "policy_memory_used": policy_memory_used,
        "policy_memory_source": policy_memory_source,
        "prior_records": prior_records,
        "memory_filtering": memory_filtering_summary,
        "verdict_owners": owner_counts,
        "verdict_axes": axis_counts,
        "exit_owners": _exit_owner_counts(records),
        "stagnation_owners": _stagnation_owner_counts(records),
        "baseline_contamination": _baseline_contamination_check(records),
        "harness_trust": trust_counts,
        "harness_owner": ht_owner_counts,
        "harness_severity": ht_severity_counts,
        "decision_issue_counts": _decision_issue_counts(records),
        "decision_area_counts": _decision_area_counts(records),
        "frontier_diagnostics": _frontier_diagnostics(records),
        "task_set_metrics": _task_set_metrics(records),
        "per_task_comparison": _per_task_comparison(records, t3_tier),
        "parser_abort_breakdown": _parser_abort_breakdown(records),
    }


def _exit_owner_counts(records: list[dict]) -> dict[str, int]:
    """Count exit_owner across all non-pass records."""
    counts: dict[str, int] = {}
    for r in records:
        if r.get("harness_resolved"):
            continue
        owner = compute_exit_owner(r)
        counts[owner] = counts.get(owner, 0) + 1
    return dict(sorted(counts.items()))


def _stagnation_owner_counts(records: list[dict]) -> dict[str, dict[str, int]]:
    """Break down stagnation exits by exit_owner and exit_reason."""
    by_owner: dict[str, dict[str, int]] = {}
    for r in records:
        reason = str(r.get("exit_reason") or "")
        if not reason.startswith("stagnation_"):
            continue
        owner = compute_exit_owner(r)
        if owner not in by_owner:
            by_owner[owner] = {}
        by_owner[owner][reason] = by_owner[owner].get(reason, 0) + 1
    return by_owner


def _baseline_contamination_check(records: list[dict]) -> dict:
    """Detect pre-fix records where bare/enterprise baselines were truncated
    by the BudgetFlow stall guard.

    Also flags post-fix records where a baseline strategy has
    exit_owner == 'budgetflow_stoploss', which should be impossible after
    the stall-guard gating fix — this is a hard gate fail.

    Returns a dict with:
      contaminated: bool
      agent_harness_stagnation_count: int
      baseline_budgetflow_stoploss_count: int — red flag if > 0
      affected_strategies: list[str]
      warn: str
    """
    agent_harness_affected: set[str] = set()
    agent_harness_count = 0
    baseline_stoploss_count = 0
    _BASELINE_STRATEGIES = frozenset({
        "bare_t2_baseline", "bare_t3_baseline", "enterprise_router_baseline",
    })
    for r in records:
        reason = str(r.get("exit_reason") or "")
        if not reason.startswith("stagnation_"):
            continue
        owner = compute_exit_owner(r)
        if owner == "agent_harness":
            agent_harness_count += 1
            agent_harness_affected.add(str(r.get("strategy") or "?"))
        elif owner == "budgetflow_stoploss" and str(r.get("strategy") or "") in _BASELINE_STRATEGIES:
            baseline_stoploss_count += 1
    contaminated = agent_harness_count > 0 or baseline_stoploss_count > 0
    parts: list[str] = []
    if agent_harness_count > 0:
        parts.append(
            "BASELINE CONTAMINATION: bare/enterprise baselines were truncated by "
            "BudgetFlow stall guard (check_stagnation). These exits are NOT vanilla "
            "mini-swe-agent behavior. Tag dataset as 'baseline-contaminated "
            "diagnostic, not clean evidence'."
        )
    if baseline_stoploss_count > 0:
        parts.append(
            "CRITICAL: baseline strategy has exit_owner='budgetflow_stoploss'. "
            "BudgetFlow stop-loss leaked into a non-BudgetFlow baseline. "
            "This is a hard gate fail — fix stall guard gating before rerun."
        )
    return {
        "contaminated": contaminated,
        "agent_harness_stagnation_count": agent_harness_count,
        "baseline_budgetflow_stoploss_count": baseline_stoploss_count,
        "affected_strategies": sorted(agent_harness_affected),
        "warn": " | ".join(parts),
    }


def _parser_abort_breakdown(records: list[dict]) -> dict:
    """Break down parser/protocol aborts by error type and retry outcome.

    For historical JSONL without protocol_retry fields, infers from
    parser_error_action_count in turn traces.
    """
    breakdown: dict[str, int] = {
        "found_0_actions": 0,
        "found_2_actions": 0,
        "unknown": 0,
        "retry_success": 0,
        "retry_failed": 0,
    }
    for r in records:
        # New runs keep per-turn retry outcomes in turn_traces. Prefer these
        # over top-level booleans so multiple retries in one task are not
        # collapsed into a single outcome.
        traces = r.get("turn_traces") or []
        trace_retry_rows = [
            trace for trace in traces
            if isinstance(trace, dict)
            and trace.get("protocol_retry_used")
            and int(trace.get("protocol_retry_attempts") or 0) > 0
        ] if isinstance(traces, list) else []
        if trace_retry_rows:
            for trace in trace_retry_rows:
                reason = str(trace.get("protocol_retry_reason") or "")
                if trace.get("protocol_retry_success"):
                    breakdown["retry_success"] += 1
                else:
                    breakdown["retry_failed"] += 1
                    if "found_2" in reason:
                        breakdown["found_2_actions"] += 1
                    elif "found_0" in reason:
                        breakdown["found_0_actions"] += 1
                    elif "empty" in reason:
                        breakdown["found_0_actions"] += 1
                    else:
                        breakdown["unknown"] += 1
            continue

        # Check for explicit top-level retry fields when turn traces are absent.
        if r.get("protocol_retry_used"):
            reason = str(r.get("protocol_retry_reason") or "")
            if r.get("protocol_retry_success"):
                breakdown["retry_success"] += 1
            else:
                breakdown["retry_failed"] += 1
                # Also count by reason category for retry_failed
                if "found_2" in reason:
                    breakdown["found_2_actions"] = breakdown.get("found_2_actions", 0) + 1
                elif "found_0" in reason or "empty" in reason:
                    breakdown["found_0_actions"] = breakdown.get("found_0_actions", 0) + 1
                else:
                    breakdown["unknown"] = breakdown.get("unknown", 0) + 1
            continue

        # Historical inference: parser/protocol aborts
        status = str(r.get("exit_status") or "")
        reason = str(r.get("exit_reason") or "")
        if not (reason.startswith("format_error_") or "format" in status.lower()):
            continue

        # Infer from turn traces
        action_count = _infer_parser_action_count(r)
        if action_count == 0:
            breakdown["found_0_actions"] += 1
        elif action_count is not None and action_count >= 2:
            breakdown["found_2_actions"] += 1
        elif action_count is None:
            breakdown["unknown"] += 1
        else:
            breakdown["found_0_actions"] += 1
    return breakdown


def _infer_parser_action_count(record: dict) -> int | None:
    """Infer parser_error_action_count from turn traces."""
    traces = record.get("turn_traces") or []
    if not isinstance(traces, list):
        return None
    for trace in reversed(traces):  # last trace usually has the error
        if not isinstance(trace, dict):
            continue
        count = trace.get("parser_error_action_count")
        if count is not None:
            try:
                return int(count)
            except (TypeError, ValueError):
                continue
    return None

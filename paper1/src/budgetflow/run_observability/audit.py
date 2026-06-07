"""Compact audit computation for BudgetFlow run JSONL records."""

from __future__ import annotations

from collections import Counter

from budgetflow.failure_classification import build_verdict, classify_failure
from budgetflow.model_tiers import parse_tier_label
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
    """Check if the record has provider-level actual cost data."""
    traces = record.get("turn_traces")
    if not isinstance(traces, list) or not traces:
        return False
    sample = traces[0]
    return "cache_hit" in sample or "provider_actual_cost" in sample


def build_compact_audit(records: list[dict]) -> dict:
    """Build a high-density audit summary from JSONL records.

    Returns a dict suitable for format_compact_audit().
    """
    total = len(records)
    resolved = sum(1 for r in records if r.get("harness_resolved"))
    failed = total - resolved
    total_cost = sum(float(r.get("total_cost") or 0) for r in records)
    verdicts = {id(r): build_verdict(r) for r in records}

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
                "total": 0, "pass": 0, "fail": 0,
                "cost": 0.0, "turns": 0, "tier_turns": {},
                "suspicious": 0, "no_trace": 0,
                "tasks": set(),
            }
        s = by_strategy[strat]
        s["total"] += 1
        s["cost"] += float(r.get("total_cost") or 0)
        turns = int(r.get("llm_turns") or 0)
        s["turns"] += turns
        picks = r.get("backend_picks") or []
        for tier, count in _tier_counts(picks).items():
            s["tier_turns"][tier] = s["tier_turns"].get(tier, 0) + count
        s["tasks"].add(r.get("instance_id", "?"))
        if r.get("harness_resolved"):
            s["pass"] += 1
        else:
            s["fail"] += 1
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
        ct_cost = sum(float(r.get("total_cost") or 0) for r in ct_recs)
        ct_pass = sum(1 for r in ct_recs if r.get("harness_resolved"))
        ct_tiers: dict[int, int] = {}
        for r in ct_recs:
            for tier, count in _tier_counts(r.get("backend_picks") or []).items():
                ct_tiers[tier] = ct_tiers.get(tier, 0) + count
        common_stats[strat] = {
            "tasks": len(ct_recs), "pass": ct_pass,
            "cost": ct_cost, "tier_turns": dict(sorted(ct_tiers.items())),
            "t2": ct_tiers.get(2, 0), "t3": ct_tiers.get(3, 0),
        }

    # Failure axis / class counts
    fail_classes = Counter(
        classify_failure(r)
        for r in records if not r.get("harness_resolved")
    )
    fail_exits = Counter(
        str(r.get("exit_status") or "unknown")
        for r in records if not r.get("harness_resolved")
    )

    # Failure subtypes (020)
    fail_subtypes = Counter(
        str(verdicts[id(r)].get("failure_subtype") or "unknown")
        for r in records if not r.get("harness_resolved")
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

    # PolicyMemory detection from standardized records, with legacy fallback.
    policy_memory_used = any(_routing_memory_used(r) for r in records)
    policy_memory_source = ""
    prior_records = 0
    if policy_memory_used:
        for r in records:
            source = _routing_memory_source(r)
            if source:
                policy_memory_source = source
                break
        prior_records = int(max((_routing_prior_task_seen(r) for r in records), default=0) or 0)

    # StagnationExit PASS rate
    stag_pass = sum(
        1 for r in records
        if r.get("harness_resolved") and str(r.get("exit_status") or "").startswith("Stagnation")
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

    return {
        "total": total,
        "pass": resolved,
        "fail": failed,
        "total_cost": total_cost,
        "suspicious": suspicious,
        "no_trace": no_trace,
        "stagnation_pass": stag_pass,
        "by_strategy": {
            strat: {
                "total": s["total"], "pass": s["pass"], "fail": s["fail"],
                "cost": s["cost"], "avg_turns": s["turns"] / max(s["total"], 1),
                "tier_turns": dict(sorted(s["tier_turns"].items())),
                "t1_turns": s["tier_turns"].get(1, 0),
                "t2_turns": s["tier_turns"].get(2, 0),
                "t3_turns": s["tier_turns"].get(3, 0),
                "t3_share": s["tier_turns"].get(3, 0) / max(sum(s["tier_turns"].values()), 1),
                "suspicious": s["suspicious"], "no_trace": s["no_trace"],
            }
            for strat, s in by_strategy.items()
        },
        "common_task_count": len(common_tasks),
        "common_stats": common_stats,
        "fail_classes": dict(fail_classes.most_common()),
        "fail_exits": dict(fail_exits.most_common()),
        "fail_subtypes": dict(fail_subtypes.most_common()),
        "stored_verdict_mismatches": stored_verdict_mismatches,
        "invoice_accurate": invoice_accurate,
        "canonical_cost_available": total > 0,
        "policy_memory_used": policy_memory_used,
        "policy_memory_source": policy_memory_source,
        "prior_records": prior_records,
        "verdict_owners": owner_counts,
        "verdict_axes": axis_counts,
        "harness_trust": trust_counts,
        "harness_owner": ht_owner_counts,
        "harness_severity": ht_severity_counts,
    }

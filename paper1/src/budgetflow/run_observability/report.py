"""Text rendering for run-observability audit results."""

from __future__ import annotations

def _format_tier_turns(turns: dict[int, int] | dict[str, int]) -> str:
    if not turns:
        return "-"
    normalized: dict[int, int] = {}
    for tier, count in turns.items():
        try:
            tier_i = int(tier)
        except (TypeError, ValueError):
            continue
        normalized[tier_i] = int(count)
    if not normalized:
        return "-"
    return " ".join(f"T{tier}={count}" for tier, count in sorted(normalized.items()))


def format_compact_audit(audit: dict) -> str:
    """Format compact audit dict as a dense text table."""
    lines = []
    banner = "=" * 64
    lines.append(banner)
    lines.append(f"COMPACT AUDIT  |  rows={audit['total']}  pass={audit['pass']}  fail={audit['fail']}  "
                 f"cost=${audit['total_cost']:.2f}")
    lines.append(f"  suspicious_pass={audit['suspicious']}  no_trace={audit['no_trace']}  "
                 f"stagnation_pass={audit['stagnation_pass']}")
    lines.append(f"  invoice_accurate={audit['invoice_accurate']}  "
                 f"policy_memory_used={audit.get('policy_memory_used', False)}")
    if audit.get("policy_memory_used"):
        lines.append(f"  policy_memory_source={audit.get('policy_memory_source', '?')}  "
                     f"prior_records={audit.get('prior_records', 0)}")

    # Per strategy
    lines.append(banner)
    lines.append(f"{'strategy':<26} {'rows':>4} {'P':>2} {'F':>2} {'cost':>8} {'t/task':>6} {'tiers':>18} {'susp':>4}")
    lines.append("-" * 64)
    for strat in sorted(audit["by_strategy"]):
        s = audit["by_strategy"][strat]
        lines.append(
            f"{strat:<26} {s['total']:>4} {s['pass']:>2} {s['fail']:>2} "
            f"${s['cost']:>7.2f} {s['avg_turns']:>5.0f} "
            f"{_format_tier_turns(s.get('tier_turns') or {}):>18} {s['suspicious']:>4}"
        )

    # Common-task comparison
    if audit["common_task_count"] > 0:
        lines.append(banner)
        lines.append(f"COMMON-TASK ({audit['common_task_count']} tasks shared across all strategies)")
        lines.append(f"{'strategy':<26} {'tasks':>5} {'P':>3} {'cost':>8} {'tiers':>18}")
        lines.append("-" * 64)
        for strat in sorted(audit["common_stats"]):
            cs = audit["common_stats"][strat]
            lines.append(
                f"{strat:<26} {cs['tasks']:>5} {cs['pass']:>3} "
                f"${cs['cost']:>7.2f} {_format_tier_turns(cs.get('tier_turns') or {}):>18}"
            )

    # Failure axis
    if audit["fail_classes"]:
        lines.append(banner)
        lines.append("FAILURE CLASSES: " + " | ".join(
            f"{k}={v}" for k, v in audit["fail_classes"].items()
        ))

    # Failure subtypes
    if audit.get("fail_subtypes"):
        lines.append("FAILURE SUBTYPES: " + " | ".join(
            f"{k}={v}" for k, v in audit["fail_subtypes"].items()
        ))

    # Verdict owner summary
    if audit.get("verdict_owners"):
        lines.append("OWNER SUMMARY: " + " | ".join(
            f"{k}={v}" for k, v in sorted(audit["verdict_owners"].items())
        ))
    if audit.get("verdict_axes"):
        lines.append("VERDICT AXES: " + " | ".join(
            f"{k}={v}" for k, v in sorted(audit["verdict_axes"].items())
        ))
    if audit.get("stored_verdict_mismatches"):
        lines.append(
            f"STORED VERDICT MISMATCHES: {audit['stored_verdict_mismatches']} "
            "(compact audit uses recomputed classifier output)"
        )

    if audit.get("strong_tier_usefulness"):
        lines.append(banner)
        lines.append(f"T2 STRONG-TIER USEFULNESS  |  strongest=T{audit.get('strong_tier', '?')}")
        lines.append(
            f"{'strategy':<26} {'strong':>6} {'useful':>6} {'rate':>7} "
            f"{'waste':>6} {'waste_cost':>10}"
        )
        lines.append("-" * 64)
        for strat in sorted(audit["strong_tier_usefulness"]):
            s = audit["strong_tier_usefulness"][strat]
            lines.append(
                f"{strat:<26} {s['strong_tier_turns']:>6} {s['useful_strong_tier_turns']:>6} "
                f"{s['useful_strong_tier_rate']:>6.0%} {s['wasted_strong_tier_turns']:>6} "
                f"${s['wasted_strong_tier_cost']:>9.4f}"
            )

    # Cost口径
    lines.append(banner)
    canonical_available = audit["total"] > 0
    lines.append(f"COST: canonical_cost_available={canonical_available}, provider_invoice_accurate={audit['invoice_accurate']}")
    if not audit["invoice_accurate"]:
        lines.append("   canonical_estimated_cost uses official API list price (paper's primary claim).")
        lines.append("   provider_actual_cost unavailable — no cache_hit/provider_actual_cost in trace data.")

    # Harness trust
    if audit.get("harness_trust"):
        lines.append(banner)
        lines.append("HARNESS TRUST: " + " | ".join(
            f"{k}={v}" for k, v in sorted(audit["harness_trust"].items())
        ))
        if audit.get("harness_severity"):
            lines.append("HARNESS SEVERITY: " + " | ".join(
                f"{k}={v}" for k, v in sorted(audit["harness_severity"].items())
            ))
        if audit.get("harness_owner"):
            lines.append("HARNESS OWNER: " + " | ".join(
                f"{k}={v}" for k, v in sorted(audit["harness_owner"].items())
            ))

    lines.append(banner)
    return "\n".join(lines)


# ── Phase Z Checker Warnings ──────────────────────────────────────────────────

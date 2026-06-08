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
    if audit.get("value_profile"):
        lines.append(f"  value_profile={audit.get('value_profile')}  "
                     f"value_objective={audit.get('value_objective') or '-'}")

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

    if any("yield_score" in s for s in audit["by_strategy"].values()):
        lines.append(banner)
        lines.append("PAPER METRICS")
        lines.append(f"{'strategy':<26} {'res_value':>9} {'task_value':>10} {'Yield':>7} {'coverage':>8} {'Yield/$':>9}")
        lines.append("-" * 64)
        for strat in sorted(audit["by_strategy"]):
            s = audit["by_strategy"][strat]
            lines.append(
                f"{strat:<26} {s.get('resolved_value', 0.0):>9.2f} "
                f"{s.get('total_task_value', 0.0):>10.2f} "
                f"{s.get('yield_score', 0.0):>7.2f} "
                f"{s.get('yield_coverage', 0.0):>8.2f} "
                f"{s.get('yield_per_dollar', 0.0):>9.2f}"
            )

    if audit.get("task_set_metrics"):
        lines.append(banner)
        lines.append("TASK SET METRICS")
        lines.append(f"{'kind':<10} {'task_set':<14} {'strategy':<26} {'rows':>5} {'P':>3} {'cost':>8} {'Yield':>7} {'Yield/$':>9}")
        lines.append("-" * 104)
        for kind in sorted(audit["task_set_metrics"]):
            for task_set in sorted(audit["task_set_metrics"][kind]):
                for strategy in sorted(audit["task_set_metrics"][kind][task_set]):
                    s = audit["task_set_metrics"][kind][task_set][strategy]
                    lines.append(
                        f"{kind:<10} {task_set:<14} {strategy:<26} {s['rows']:>5} {s['pass']:>3} "
                        f"${s['cost']:>7.2f} {s['yield_score']:>7.2f} {s['yield_per_dollar']:>9.2f}"
                    )

    # Common-task comparison
    if audit["common_task_count"] > 0:
        lines.append(banner)
        lines.append(f"COMMON-TASK POLICY COMPARISON ({audit['common_task_count']} tasks shared across all strategies)")
        lines.append(f"{'strategy':<26} {'tasks':>5} {'P':>3} {'cost':>8} {'tiers':>18}")
        lines.append("-" * 64)
        for strat in sorted(audit["common_stats"]):
            cs = audit["common_stats"][strat]
            lines.append(
                f"{strat:<26} {cs['tasks']:>5} {cs['pass']:>3} "
                f"${cs['cost']:>7.2f} {_format_tier_turns(cs.get('tier_turns') or {}):>18}"
            )

    control_delta = audit.get("segment_control_delta") or {}
    if control_delta:
        lines.append(banner)
        lines.append("SEGMENT CONTROL")
        lines.append(
            f"{control_delta['segment_aware_strategy']} - {control_delta['task_level_control']}: "
            f"delta_pass={control_delta['delta_pass']} "
            f"delta_cost=${control_delta['delta_cost']:.4f} "
            f"delta_yield={control_delta['delta_yield']:.4f} "
            f"delta_yield_per_dollar={control_delta['delta_yield_per_dollar']:.4f}"
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

    t3_productivity = audit.get("t3_productivity")
    if t3_productivity:
        lines.append(banner)
        lines.append(f"STRONGEST MODEL PRODUCTIVITY  |  strongest_model=T{audit.get('t3_tier', '?')}")
        lines.append(
            f"{'strategy':<26} {'t3':>6} {'productive':>10} {'rate':>7} "
            f"{'no_prog':>7} {'no_prog_cost':>12}"
        )
        lines.append("-" * 72)
        for strat in sorted(t3_productivity):
            s = t3_productivity[strat]
            lines.append(
                f"{strat:<26} {s['t3_turns']:>6} {s['t3_productive_turns']:>10} "
                f"{s['t3_productive_rate']:>6.0%} {s['t3_no_progress_turns']:>7} "
                f"${s['t3_no_progress_cost']:>11.4f}"
            )

    t3_sources = audit.get("t3_source_breakdown")
    if t3_sources:
        lines.append(banner)
        lines.append("T3 SOURCE BREAKDOWN")
        lines.append(
            f"{'strategy':<26} {'source':<20} {'t3':>5} {'productive':>10} "
            f"{'rate':>7} {'no_prog_cost':>12}"
        )
        lines.append("-" * 84)
        for strat in sorted(t3_sources):
            for source in sorted(t3_sources[strat]):
                s = t3_sources[strat][source]
                lines.append(
                    f"{strat:<26} {source:<20} {s['t3_turns']:>5} "
                    f"{s['t3_productive_turns']:>10} {s['t3_productive_rate']:>6.0%} "
                    f"${s['t3_no_progress_cost']:>11.4f}"
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

    if audit.get("decision_issue_counts"):
        lines.append(banner)
        if audit.get("decision_area_counts"):
            lines.append("DECISION ISSUE AREAS: " + " | ".join(
                f"{k}={v}" for k, v in sorted(audit["decision_area_counts"].items())
            ))
        lines.append("DECISION ISSUES: " + " | ".join(
            f"{k}={v}" for k, v in sorted(audit["decision_issue_counts"].items())
        ))

    lines.append(banner)
    return "\n".join(lines)


# ── Phase Z Checker Warnings ──────────────────────────────────────────────────

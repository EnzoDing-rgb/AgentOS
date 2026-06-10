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
    lines.append(
        f"COMPACT AUDIT  |  rows={audit['total']}  pass={audit['pass']}  "
        f"true_fail={audit['fail']}  abort={audit.get('abort', 0)}  cost=${audit['total_cost']:.2f}"
    )
    if audit.get("abort"):
        lines.append(
            f"  scoreable_cost=${audit.get('scoreable_cost', 0.0):.2f}  "
            f"abort_cost=${audit.get('abort_cost', 0.0):.2f}"
        )
    lines.append(f"  suspicious_pass={audit['suspicious']}  no_trace={audit['no_trace']}  "
                 f"stagnation_pass={audit['stagnation_pass']}")
    lines.append(f"  invoice_accurate={audit['invoice_accurate']}  "
                 f"policy_memory_used={audit.get('policy_memory_used', False)}")
    if audit.get("policy_memory_used"):
        lines.append(f"  policy_memory_source={audit.get('policy_memory_source', '?')}  "
                     f"prior_records={audit.get('prior_records', 0)}")
        mf = audit.get("memory_filtering")
        if mf:
            lines.append(
                f"  memory_filtering: seen={mf.get('records_seen', 0)} "
                f"accepted={mf.get('records_accepted', 0)} "
                f"skipped={mf.get('records_skipped', 0)} "
                f"skip_reasons={mf.get('skip_reasons', {})}"
            )
    if audit.get("value_profile"):
        lines.append(f"  value_profile={audit.get('value_profile')}  "
                     f"value_objective={audit.get('value_objective') or '-'}")

    # Per strategy
    lines.append(banner)
    lines.append(f"{'strategy':<26} {'rows':>4} {'P':>2} {'F':>2} {'A':>2} {'cost':>8} {'t/task':>6} {'tiers':>18} {'susp':>4}")
    lines.append("-" * 64)
    for strat in sorted(audit["by_strategy"]):
        s = audit["by_strategy"][strat]
        lines.append(
            f"{strat:<26} {s['total']:>4} {s['pass']:>2} {s['fail']:>2} {s.get('abort', 0):>2} "
            f"${s['cost']:>7.2f} {s['avg_turns']:>5.0f} "
            f"{_format_tier_turns(s.get('tier_turns') or {}):>18} {s['suspicious']:>4}"
        )

    if any("yield_score" in s for s in audit["by_strategy"].values()):
        lines.append(banner)
        lines.append("PAPER METRICS")
        lines.append(
            f"{'strategy':<26} {'res_value':>9} {'task_value':>10} {'Yield':>7} "
            f"{'coverage':>8} {'Yield/total$':>13} {'Yield/score$':>13} {'abort$':>8}"
        )
        lines.append("-" * 64)
        for strat in sorted(audit["by_strategy"]):
            s = audit["by_strategy"][strat]
            lines.append(
                f"{strat:<26} {s.get('resolved_value', 0.0):>9.2f} "
                f"{s.get('total_task_value', 0.0):>10.2f} "
                f"{s.get('yield_score', 0.0):>7.2f} "
                f"{s.get('yield_coverage', 0.0):>8.2f} "
                f"{s.get('yield_per_total_dollar', s.get('yield_per_dollar', 0.0)):>13.2f} "
                f"{s.get('yield_per_scoreable_dollar', s.get('yield_per_dollar', 0.0)):>13.2f} "
                f"${s.get('abort_cost', 0.0):>7.2f}"
            )

    if audit.get("task_set_metrics"):
        lines.append(banner)
        lines.append("TASK SET METRICS")
        lines.append(f"{'kind':<10} {'task_set':<14} {'strategy':<26} {'rows':>5} {'P':>3} {'F':>3} {'A':>3} {'cost':>8} {'Yield':>7} {'Yield/score$':>10}")
        lines.append("-" * 104)
        for kind in sorted(audit["task_set_metrics"]):
            for task_set in sorted(audit["task_set_metrics"][kind]):
                for strategy in sorted(audit["task_set_metrics"][kind][task_set]):
                    s = audit["task_set_metrics"][kind][task_set][strategy]
                    lines.append(
                        f"{kind:<10} {task_set:<14} {strategy:<26} {s['rows']:>5} {s['pass']:>3} "
                        f"{s.get('true_fail', 0):>3} {s.get('abort', 0):>3} "
                        f"${s['cost']:>7.2f} {s['yield_score']:>7.2f} {s['yield_per_dollar']:>9.2f}"
                    )

    # Common-task comparison
    if audit["common_task_count"] > 0:
        lines.append(banner)
        lines.append(f"COMMON-TASK POLICY COMPARISON ({audit['common_task_count']} tasks shared across all strategies)")
        lines.append(f"{'strategy':<26} {'tasks':>5} {'P':>3} {'F':>3} {'A':>3} {'cost':>8} {'tiers':>18}")
        lines.append("-" * 64)
        for strat in sorted(audit["common_stats"]):
            cs = audit["common_stats"][strat]
            lines.append(
                f"{strat:<26} {cs['tasks']:>5} {cs['pass']:>3} {cs.get('fail', 0):>3} {cs.get('abort', 0):>3} "
                f"${cs['cost']:>7.2f} {_format_tier_turns(cs.get('tier_turns') or {}):>18}"
            )

    control_delta = audit.get("mechanism_isolation_delta") or {}
    if control_delta:
        lines.append(banner)
        lines.append("MECHANISM ISOLATION DELTA")
        lines.append(
            f"{control_delta['mechanism_strategy']} - {control_delta['baseline_strategy']}: "
            f"delta_pass={control_delta['delta_pass']} "
            f"delta_cost=${control_delta['delta_cost']:.4f} "
            f"delta_yield={control_delta['delta_yield']:.4f} "
            f"delta_yield_per_dollar={control_delta['delta_yield_per_dollar']:.4f} "
            f"delta_yield_per_total_dollar={control_delta.get('delta_yield_per_total_dollar', 0.0):.4f}"
        )
        if "bare_t3_pass" in control_delta:
            lines.append(
                f"  bare_t3_baseline: pass={control_delta['bare_t3_pass']} "
                f"cost=${control_delta['bare_t3_cost']:.4f} "
                f"yield={control_delta['bare_t3_yield']:.4f}"
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
            f"{'no_prog':>7} {'unknown':>7} {'no_prog_cost':>12}"
        )
        lines.append("-" * 72)
        for strat in sorted(t3_productivity):
            s = t3_productivity[strat]
            lines.append(
                f"{strat:<26} {s['t3_turns']:>6} {s['t3_productive_turns']:>10} "
                f"{s['t3_productive_rate']:>6.0%} {s['t3_no_progress_turns']:>7} "
                f"{s.get('t3_unknown_progress_turns', 0):>7} "
                f"${s['t3_no_progress_cost']:>11.4f}"
            )

    t3_sources = audit.get("t3_source_breakdown")
    if t3_sources:
        lines.append(banner)
        lines.append("T3 SOURCE BREAKDOWN")
        lines.append(
            f"{'strategy':<26} {'source':<20} {'t3':>5} {'productive':>10} "
            f"{'rate':>7} {'unknown':>7} {'no_prog_cost':>12}"
        )
        lines.append("-" * 84)
        for strat in sorted(t3_sources):
            for source in sorted(t3_sources[strat]):
                s = t3_sources[strat][source]
                lines.append(
                    f"{strat:<26} {source:<20} {s['t3_turns']:>5} "
                    f"{s['t3_productive_turns']:>10} {s['t3_productive_rate']:>6.0%} "
                    f"{s.get('t3_unknown_progress_turns', 0):>7} "
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

    # Per-task cross-policy comparison
    per_task = audit.get("per_task_comparison")
    if per_task:
        lines.append(banner)
        lines.append("PER-TASK POLICY COMPARISON")
        lines.append(
            f"{'instance_id':<30} {'strategy':<34} {'S':>4} {'cost':>7} {'val':>5} "
            f"{'plan':>5} {'cap':>5} {'turn':>4} {'1st':>5} {'T3@':>4} {'use@':>4} {'gap':>3} "
            f"{'patch':>5} {'fail':<14} {'trust':<5}"
        )
        lines.append("-" * 140)
        for row in per_task:
            plan_model = row.get("frozen_plan_preferred_model") or "-"
            plan_cap = row.get("frozen_plan_base_cap")
            plan_cap_text = "-" if plan_cap in (None, "") else f"{float(plan_cap):.2f}"
            lines.append(
                f"{row['instance_id']:<30} {row['strategy']:<34} {str(row.get('score_status') or '-')[:4]:>4} "
                f"${row['cost']:>6.2f} {row['task_value']:>5.2f} "
                f"{plan_model:>5} {plan_cap_text:>5} "
                f"{row['turns']:>4} T{row['first_tier']:>4} "
                f"{row['first_t3_turn'] if row['first_t3_turn'] is not None else '-':>4} "
                f"{row['first_useful_action'] if row['first_useful_action'] is not None else '-':>4} "
                f"{row['max_no_progress_streak']:>3} "
                f"{'no' if row['no_patch'] else 'yes':>5} "
                f"{row['failure_class']:<14} "
                f"{row['harness_trust']:<5}"
            )
            detail = _format_per_task_decision_detail(row)
            if detail:
                lines.append(f"  decision: {detail}")
        # Legend
        lines.append(
            "  S=score_status(pass/true_fail/abort)  val=task_value  turn=llm_turns  1st=first_backend_tier  "
            "plan=frozen_plan_preferred_model  cap=frozen_plan_base_cap  "
            "T3@=first_T3_turn  use@=first_useful_action  gap=max_no_progress_streak"
        )

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


def _format_per_task_decision_detail(row: dict) -> str:
    parts: list[str] = []
    policy = _compact_pair("policy", row.get("policy_name") or row.get("policy_type"))
    route = _compact_pair(
        "route",
        row.get("last_router_reason") or row.get("first_router_branch") or row.get("policy_reason"),
    )
    memory = _compact_pair("memory", row.get("memory_mode"))
    learned = _compact_pair(
        "learned",
        row.get("routing_repair_learned_action") or row.get("routing_learned_action"),
    )
    imitation = _compact_pair(
        "imitation",
        row.get("routing_imitation_source") if row.get("routing_imitation_active") else "",
    )
    frozen = _compact_pair(
        "frozen",
        "/".join(
            str(value)
            for value in (
                row.get("frozen_plan_name"),
                row.get("frozen_plan_preferred_model"),
                row.get("frozen_plan_priority"),
            )
            if value not in (None, "")
        ),
    )
    cost = _compact_pair("cost", row.get("cost_estimate_source") or row.get("cost_source"))
    provider = _compact_pair("provider", row.get("provider_status_code") or row.get("provider"))
    parser = _compact_pair("parser", row.get("parser_error_type") or row.get("parser"))
    harness = _compact_pair(
        "harness",
        "/".join(
            value
            for value in (
                row.get("harness_trust"),
                row.get("harness_severity"),
                row.get("harness_owner"),
            )
            if value
        ),
    )
    for item in (policy, route, memory, learned, imitation, frozen, cost, provider, parser, harness):
        if item:
            parts.append(item)
    return " | ".join(parts)


def _compact_pair(label: str, value) -> str:
    if value in (None, "", {}, [], False):
        return ""
    text = str(value)
    if len(text) > 72:
        text = text[:69] + "..."
    return f"{label}={text}"


# ── Phase Z Checker Warnings ──────────────────────────────────────────────────

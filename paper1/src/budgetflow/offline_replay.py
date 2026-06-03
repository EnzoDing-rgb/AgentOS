"""Offline replay/audit tool — compare two JSONL runs without API calls.

Usage:
  python -m budgetflow.offline_replay --017 data/runs/postfix_017_10x5-0.jsonl \
                                      --018 data/runs/postfix_018_warmup_10x5.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def _load(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def _per_task_table(recs_017: list[dict], recs_018: list[dict]) -> str:
    """Build per-task comparison: smart vs budgetflow differences."""
    # Index by (strategy, instance_id)
    idx017: dict[tuple[str, str], dict] = {}
    idx018: dict[tuple[str, str], dict] = {}
    for r in recs_017:
        idx017[(r.get("strategy", ""), r.get("instance_id", ""))] = r
    for r in recs_018:
        idx018[(r.get("strategy", ""), r.get("instance_id", ""))] = r

    # Find common tasks
    tasks_017 = {r.get("instance_id") for r in recs_017}
    tasks_018 = {r.get("instance_id") for r in recs_018}
    common_tasks = sorted(tasks_017 & tasks_018)

    smart = "budget_only_tight"
    bf = "budgetflow_full_tight"

    lines = ["=== PER-TASK: smart vs budgetflow ==="]
    header = f"{'task':<35} {'smart_P':>7} {'bf_P':>7} {'smart_cost':>10} {'bf_cost':>10} {'delta':>8} {'winner':>8}"
    lines.append(header)
    lines.append("-" * len(header))

    for task in common_tasks:
        s017 = idx017.get((smart, task), {})
        b017 = idx017.get((bf, task), {})
        s018 = idx018.get((smart, task), {})
        b018 = idx018.get((bf, task), {})

        s_pass = "PASS" if s018.get("harness_resolved") else "FAIL"
        b_pass = "PASS" if b018.get("harness_resolved") else "FAIL"
        s_cost = float(s018.get("total_cost") or 0)
        b_cost = float(b018.get("total_cost") or 0)
        delta = b_cost - s_cost

        # Winner: who has better outcome
        s_won = s018.get("harness_resolved") and not b018.get("harness_resolved")
        b_won = b018.get("harness_resolved") and not s018.get("harness_resolved")
        if s_won:
            winner = "smart"
        elif b_won:
            winner = "bf"
        elif s_cost < b_cost:
            winner = "smart-$"
        elif b_cost < s_cost:
            winner = "bf-$"
        else:
            winner = "tie"

        lines.append(
            f"{task:<35} {s_pass:>7} {b_pass:>7} "
            f"${s_cost:>9.4f} ${b_cost:>9.4f} ${delta:>7.4f} {winner:>8}"
        )

    return "\n".join(lines)


def _budget_misestimates(recs: list[dict]) -> str:
    """Identify budget mis-estimates: cap too low vs actual."""
    lines = ["\n=== BUDGET MIS-ESTIMATES ==="]
    issues: list[str] = []
    for r in recs:
        cap = r.get("batch_budget_cap") or r.get("estimated_task_cap")
        if cap is None:
            continue
        cost = float(r.get("total_cost") or r.get("task_cost") or 0)
        if cost > float(cap) * 1.5:
            inst = r.get("instance_id", "?")
            strat = r.get("strategy", "?")
            issues.append(
                f"  UNDERBUDGET: {inst} {strat} cap=${float(cap):.4f} actual=${cost:.4f} "
                f"(ratio={cost/float(cap):.1f}x)"
            )
    if issues:
        lines.extend(issues)
    else:
        lines.append("  (no severe mis-estimates found)")
    return "\n".join(lines)


def _failure_ownership(recs: list[dict]) -> str:
    """Summarize failure ownership across records.

    Dynamically calls build_verdict() on every record so old JSONL
    without verdict_axis/failure_owner fields still produces output.
    """
    from budgetflow.failure_classification import build_verdict

    lines = ["\n=== FAILURE OWNERSHIP ==="]
    owners: dict[str, int] = Counter()
    axes: dict[str, int] = Counter()
    for r in recs:
        v = build_verdict(r)
        owner = v.get("failure_owner", "")
        axis = v.get("verdict_axis", "")
        if owner:
            owners[owner] += 1
        if axis:
            axes[axis] += 1

    if owners:
        lines.append("  By owner: " + " | ".join(f"{k}={v}" for k, v in owners.most_common()))
    else:
        lines.append("  By owner: (none — all rows pass or unclassifiable)")
    lines.append("  By axis:  " + " | ".join(f"{k}={v}" for k, v in axes.most_common()))
    return "\n".join(lines)


def _harness_trust_stats(recs: list[dict]) -> str:
    """Summarize harness trust across records."""
    from budgetflow.observability import build_harness_trust

    lines = ["\n=== HARNESS TRUST ==="]
    trust_counts: dict[str, int] = Counter()
    owner_counts: dict[str, int] = Counter()
    severity_counts: dict[str, int] = Counter()
    for r in recs:
        ht = build_harness_trust(r)
        trust_counts[ht["harness_trust"]] += 1
        if ht["harness_owner"] != "none":
            owner_counts[ht["harness_owner"]] += 1
        sev = ht.get("severity", "")
        if sev and sev != "none":
            severity_counts[sev] += 1

    lines.append("  Trust: " + " | ".join(f"{k}={v}" for k, v in sorted(trust_counts.items())))
    if severity_counts:
        lines.append("  Severity: " + " | ".join(f"{k}={v}" for k, v in sorted(severity_counts.items())))
    if owner_counts:
        lines.append("  Owner: " + " | ".join(f"{k}={v}" for k, v in sorted(owner_counts.items())))
    return "\n".join(lines)


def _policy_memory_effect(recs_017: list[dict], recs_018: list[dict]) -> str:
    """Compare policy_memory effect between two runs."""
    lines = ["\n=== POLICY MEMORY EFFECT ==="]

    pm_017 = any(r.get("policy_memory_enabled") for r in recs_017)
    pm_018 = any(r.get("policy_memory_enabled") for r in recs_018)

    lines.append(f"  017 policy_memory: {pm_017}")
    lines.append(f"  018 policy_memory: {pm_018}")

    if pm_018:
        # Action distribution in 018
        actions: dict[str, int] = Counter()
        for r in recs_018:
            prior = r.get("routing_prior_summary") or {}
            action = prior.get("learned_action", "default")
            actions[action] += 1
        lines.append("  018 learned_action dist: " + " | ".join(
            f"{k}={v}" for k, v in actions.most_common()
        ))

        # Compare pass rate for rows with vs without learned_action
        with_action = [r for r in recs_018 if (r.get("routing_prior_summary") or {}).get("learned_action", "default") != "default"]
        without_action = [r for r in recs_018 if (r.get("routing_prior_summary") or {}).get("learned_action", "default") == "default"]
        if with_action:
            pr_with = sum(1 for r in with_action if r.get("harness_resolved")) / max(len(with_action), 1)
            pr_without = sum(1 for r in without_action if r.get("harness_resolved")) / max(len(without_action), 1)
            lines.append(f"  Pass rate with action: {pr_with:.0%} ({len(with_action)} rows)")
            lines.append(f"  Pass rate default:     {pr_without:.0%} ({len(without_action)} rows)")

    return "\n".join(lines)


def _budget_dry_run(recs: list[dict]) -> str:
    """Simulate BudgetMemory estimates vs actual costs for a single JSONL."""
    from budgetflow.budget_memory import BudgetMemory

    lines = ["\n=== BUDGET DRY-RUN ==="]

    # Check if records already have budget_memory fields (post-020)
    has_bm_fields = any(r.get("budget_memory_enabled") for r in recs)

    if has_bm_fields:
        under_count = over_count = ok_count = 0
        lines.append(f"  {'task':<40} {'bm_cap':>10} {'actual':>10} {'delta':>10} {'verdict':>12}")
        lines.append(f"  {'-'*85}")
        for r in recs:
            bm_cap = float(r.get("budget_memory_estimated_budget", 0))
            actual = float(r.get("total_cost", 0))
            if not bm_cap:
                continue
            delta = bm_cap - actual
            if actual > bm_cap * 1.5:
                verdict = "UNDERBUDGET"
                under_count += 1
            elif bm_cap > actual * 3:
                verdict = "OVERBUDGET"
                over_count += 1
            else:
                verdict = "ok"
                ok_count += 1
            iid = str(r.get("instance_id", "?"))[:39]
            lines.append(f"  {iid:<40} ${bm_cap:>9.4f} ${actual:>9.4f} ${delta:>+9.4f} {verdict:>12}")
        lines.append(f"\n  underbudget_fixed={under_count} overbudget_reduced={over_count} ok={ok_count}")
    else:
        # Build BudgetMemory from the records and compute estimates
        bm = BudgetMemory()
        bm._learn(recs)
        lines.append(f"  BudgetMemory built from {bm.record_count} records, {bm.task_count} tasks")
        lines.append(f"  {'task':<40} {'auto_cap':>10} {'bm_cap':>10} {'bm_source':<20}")
        lines.append(f"  {'-'*85}")
        for iid in sorted(bm._task_stats.keys()):
            est = bm.estimate_task_budget(iid, strategy="budget_only_tight")
            task_costs = [float(r.get("total_cost", 0)) for r in recs if r.get("instance_id") == iid]
            auto_cap = sum(task_costs) / max(len(task_costs), 1)
            lines.append(f"  {iid:<40} ${auto_cap:>9.4f} ${est.estimated_task_budget:>9.4f} {est.budget_source:<20}")
        risky = sum(1 for iid in bm._task_stats if bm.estimate_task_budget(iid).risk_multiplier >= 2.0)
        lines.append(f"\n  risky={risky} unchanged=0")

    return "\n".join(lines)


def _failure_subtypes(recs: list[dict]) -> str:
    """Summarize failure subtypes."""
    from budgetflow.failure_classification import build_verdict, classify_failure_subtype

    lines = ["\n=== FAILURE SUBTYPES ==="]
    subtypes: Counter = Counter()
    for r in recs:
        if r.get("harness_resolved"):
            continue
        subtype = str(r.get("failure_subtype") or "")
        if not subtype or subtype == "unknown":
            v = build_verdict(r)
            subtype = classify_failure_subtype(
                r, axis=v.get("verdict_axis"), stage=v.get("failure_stage")
            )
        if subtype and subtype != "pass":
            subtypes[subtype] += 1
    if subtypes:
        lines.append("  " + " | ".join(f"{k}={v}" for k, v in subtypes.most_common()))
    else:
        lines.append("  (no failures)")
    return "\n".join(lines)


def _fallback_audit(recs: list[dict]) -> str:
    """Summarize fallback patch audit across records."""
    from budgetflow.observability import audit_fallback_patch

    lines = ["\n=== FALLBACK AUDIT ==="]
    comparison: Counter = Counter()
    audit_results: Counter = Counter()
    for r in recs:
        fa = audit_fallback_patch(r)
        comparison[fa["submitted_vs_fallback"]] += 1
        audit_results[fa["fallback_audit"]] += 1

    lines.append("  Submitted vs Fallback: " + " | ".join(
        f"{k}={v}" for k, v in comparison.most_common()
    ))
    lines.append("  Audit results: " + " | ".join(
        f"{k}={v}" for k, v in audit_results.most_common()
    ))
    return "\n".join(lines)


def _trusted_fallback_audit(recs: list[dict]) -> str:
    """Audit trusted_fallback rows specifically: patch comparison, evidence completeness."""
    from budgetflow.observability import audit_fallback_patch, build_harness_trust

    lines = ["\n=== TRUSTED_FALLBACK AUDIT ==="]
    tf_rows: list[dict] = []
    for r in recs:
        ht = build_harness_trust(r)
        if ht["harness_trust"] == "trusted_fallback":
            tf_rows.append(r)

    if not tf_rows:
        lines.append("  trusted_fallback_rows=0")
        return "\n".join(lines)

    lines.append(f"  trusted_fallback_rows={len(tf_rows)}")

    evidence_complete = sum(
        1 for r in tf_rows
        if (r.get("harness_evidence") or {}).get("evidence_complete", False)
    )
    lines.append(f"  evidence_complete={evidence_complete}")

    # Audit fallback patches for these rows
    comparison: Counter = Counter()
    for r in tf_rows:
        fa = audit_fallback_patch(r)
        svf = fa["submitted_vs_fallback"]
        if svf == "unknown":
            # Can't determine offline — patch files not accessible
            comparison["unknown_offline"] += 1
        else:
            comparison[svf] += 1

    for k in ("no_submission", "submitted_same", "submitted_different", "no_fallback", "no_patch", "unknown_offline"):
        if k in comparison:
            lines.append(f"  {k}={comparison[k]}")

    if "unknown_offline" in comparison:
        lines.append("  NOTE: unknown_offline = patch file paths not accessible in offline replay")

    # Evidence gaps for trusted_fallback rows that are PASS
    pass_tf = [r for r in tf_rows if r.get("harness_resolved")]
    if pass_tf:
        lines.append(f"  trusted_fallback_pass={len(pass_tf)} (PASS with worktree fallback)")

    return "\n".join(lines)


def _incomplete_fail_breakdown(recs: list[dict]) -> str:
    """Break down incomplete FAIL records."""
    from budgetflow.observability import classify_incomplete_fail

    lines = ["\n=== INCOMPLETE FAIL BREAKDOWN ==="]
    breakdown: Counter = Counter()
    for r in recs:
        cat = classify_incomplete_fail(r)
        if cat != "not_applicable":
            breakdown[cat] += 1
    if breakdown:
        lines.append("  " + " | ".join(f"{k}={v}" for k, v in breakdown.most_common()))
    else:
        lines.append("  (all rows pass or have complete evidence)")
    return "\n".join(lines)


def _summary_table(recs_017: list[dict], recs_018: list[dict]) -> str:
    """Overall summary table comparing 017 vs 018."""
    lines = ["\n=== SUMMARY: 017 vs 018 ==="]

    def stats(recs):
        total = len(recs)
        pass_n = sum(1 for r in recs if r.get("harness_resolved"))
        cost = sum(float(r.get("total_cost") or 0) for r in recs)
        suspicious = sum(
            1 for r in recs
            if r.get("harness_resolved") and not (r.get("harness_evidence") or {}).get("evidence_complete", False)
        )
        return total, pass_n, cost, suspicious

    t1, p1, c1, s1 = stats(recs_017)
    t2, p2, c2, s2 = stats(recs_018)

    lines.append(f"  {'metric':<25} {'017':>10} {'018':>10} {'delta':>10}")
    lines.append(f"  {'-'*55}")
    lines.append(f"  {'rows':<25} {t1:>10} {t2:>10} {t2-t1:>+10}")
    lines.append(f"  {'pass':<25} {p1:>10} {p2:>10} {p2-p1:>+10}")
    lines.append(f"  {'total_cost':<25} ${c1:>9.4f} ${c2:>9.4f} ${c2-c1:>+9.4f}")
    lines.append(f"  {'suspicious_pass':<25} {s1:>10} {s2:>10} {s2-s1:>+10}")

    # Per-strategy comparison for common strategies
    strats_017 = {r.get("strategy") for r in recs_017}
    strats_018 = {r.get("strategy") for r in recs_018}
    common_strats = strats_017 & strats_018

    if common_strats:
        lines.append(f"\n  Per-strategy pass rate:")
        lines.append(f"  {'strategy':<25} {'017':>10} {'018':>10} {'delta':>10}")
        for strat in sorted(common_strats):
            r1 = [r for r in recs_017 if r.get("strategy") == strat]
            r2 = [r for r in recs_018 if r.get("strategy") == strat]
            pr1 = sum(1 for r in r1 if r.get("harness_resolved")) / max(len(r1), 1)
            pr2 = sum(1 for r in r2 if r.get("harness_resolved")) / max(len(r2), 1)
            c1s = sum(float(r.get("total_cost") or 0) for r in r1)
            c2s = sum(float(r.get("total_cost") or 0) for r in r2)
            lines.append(
                f"  {strat:<25} {pr1:>9.0%} ${c1s:>7.4f} {pr2:>9.0%} ${c2s:>7.4f}"
            )

    return "\n".join(lines)


def run_replay(path_017: Path, path_018: Path) -> str:
    """Run offline replay comparing two experiment JSONL files."""
    recs_017 = _load(path_017)
    recs_018 = _load(path_018)

    if not recs_017:
        return f"ERROR: no records in {path_017}"
    if not recs_018:
        return f"ERROR: no records in {path_018}"

    sections = [
        _summary_table(recs_017, recs_018),
        _per_task_table(recs_017, recs_018),
        _budget_misestimates(recs_018),
        _budget_dry_run(recs_018),
        _failure_ownership(recs_018),
        _failure_subtypes(recs_018),
        _harness_trust_stats(recs_018),
        _trusted_fallback_audit(recs_018),
        _fallback_audit(recs_018),
        _incomplete_fail_breakdown(recs_018),
        _policy_memory_effect(recs_017, recs_018),
    ]
    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline replay: compare two experiment JSONL files")
    parser.add_argument("--017", type=str, required=True, dest="path_017", help="path to 017 JSONL (cold, no prior)")
    parser.add_argument("--018", type=str, required=True, dest="path_018", help="path to 018 JSONL (warm, with prior)")
    args = parser.parse_args()

    p017 = Path(args.path_017)
    p018 = Path(args.path_018)
    if not p017.is_file():
        print(f"ERROR: --017 file not found: {p017}")
        sys.exit(1)
    if not p018.is_file():
        print(f"ERROR: --018 file not found: {p018}")
        sys.exit(1)

    print(run_replay(p017, p018))


if __name__ == "__main__":
    main()

"""Quick observability checker for experiment JSONL files.

Usage:
  python -m budgetflow.check_run_observability --jsonl data/runs/compare_5x5.jsonl
  python -m budgetflow.check_run_observability --jsonl data/runs/compare_5x5.jsonl --heartbeat 600
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from budgetflow.observability import (
    build_harness_trust,
    build_observability_status,
    heartbeat_is_stale,
    load_heartbeat,
    parse_harness_evidence,
)

REQUIRED_FIELDS = frozenset({
    "instance_id", "strategy", "routing", "harness_resolved",
    "exit_status", "exit_reason", "total_cost", "llm_turns",
    "elapsed_s", "detail", "turn_trace_count",
    "run_series", "policy_lane", "task_order_index",
    "row_started_at", "row_finished_at",
    "harness_evidence", "observability_status",
})

OPTIONAL_BUT_DESIRED = frozenset({
    "failure_class", "forensic_summary", "backend_picks",
    "submitted_patch", "attempt_id",
})


def _check_duplicates(records: list[dict]) -> list[str]:
    issues: list[str] = []
    seen: set[tuple[str, str]] = set()
    for i, rec in enumerate(records):
        key = (str(rec.get("strategy", "")), str(rec.get("instance_id", "")))
        if not key[0] or not key[1]:
            continue
        if key in seen:
            issues.append(f"DUPLICATE row {i}: strategy={key[0]} instance={key[1]}")
        seen.add(key)
    return issues


def _check_pass_evidence(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        if not rec.get("harness_resolved"):
            continue
        evidence = rec.get("harness_evidence") or {}
        if isinstance(evidence, dict):
            complete = evidence.get("evidence_complete", False)
        else:
            ev = parse_harness_evidence(str(rec.get("detail") or ""))
            complete = ev.evidence_complete
        if not complete:
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            detail = str(rec.get("detail", ""))[:120]
            issues.append(
                f"SUSPICIOUS_PASS row {i}: {inst} {strat} — resolved but evidence incomplete. "
                f"detail={detail}"
            )
    return issues


def _check_trace_coverage(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        trace_count = int(rec.get("turn_trace_count") or 0)
        if trace_count <= 0:
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(f"NO_TRACE row {i}: {inst} {strat} — turn_trace_count={trace_count}")
    return issues


def _check_missing_fields(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        missing = [f for f in REQUIRED_FIELDS if f not in rec]
        if missing:
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(f"MISSING_FIELDS row {i}: {inst} {strat} — missing={missing}")
    return issues


def _check_desired_fields(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        missing = [f for f in OPTIONAL_BUT_DESIRED if f not in rec]
        if missing:
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(f"DESIRED_FIELDS row {i}: {inst} {strat} — missing={missing}")
    return issues


def _check_harness_trust(records: list[dict]) -> tuple[list[str], dict[str, int], dict[str, int], dict[str, int]]:
    """Audit harness trust across all records.

    Returns (issues, trust_counts, owner_counts, severity_counts).
    """
    issues: list[str] = []
    trust_counts: dict[str, int] = Counter()
    owner_counts: dict[str, int] = Counter()
    severity_counts: dict[str, int] = Counter()
    for i, rec in enumerate(records):
        ht = build_harness_trust(rec)
        trust = ht["harness_trust"]
        owner = ht["harness_owner"]
        sev = ht.get("severity", "")
        trust_counts[trust] += 1
        if owner != "none":
            owner_counts[owner] += 1
        if sev and sev != "none":
            severity_counts[sev] += 1
        if trust in ("suspicious", "invalid"):
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(
                f"HARNESS_{trust.upper()} row {i}: {inst} {strat} "
                f"owner={owner} severity={sev} issues={ht['harness_issues']}"
            )
    return issues, dict(trust_counts), dict(owner_counts), dict(severity_counts)


def _check_elapsed_sanity(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        elapsed = rec.get("elapsed_s")
        if elapsed is None:
            continue
        try:
            elapsed = float(elapsed)
        except (TypeError, ValueError):
            issues.append(f"BAD_ELAPSED row {i}: elapsed_s={elapsed}")
            continue
        started = rec.get("row_started_at")
        finished = rec.get("row_finished_at")
        if started and finished:
            try:
                computed = float(finished) - float(started)
                if abs(computed - elapsed) > 10:
                    issues.append(
                        f"ELAPSED_MISMATCH row {i}: elapsed_s={elapsed:.1f} "
                        f"computed={computed:.1f}"
                    )
            except (TypeError, ValueError):
                pass
    return issues


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _rows_stuck(hb: dict, stale_seconds: float) -> tuple[bool, str]:
    """Check if a run has stalled: no progress despite elapsed time.

    Returns (is_stuck, reason).
    """
    rows_done = int(hb.get("rows_done") or 0)
    total = int(hb.get("total_expected") or 0)
    if total <= 0 or rows_done >= total:
        return False, ""

    status = str(hb.get("status") or "")
    updated_at = float(hb.get("updated_at") or 0)
    started_at = float(hb.get("started_at") or 0)
    active_elapsed_s = float(hb.get("active_elapsed_s") or 0)
    active_strategy = str(hb.get("active_strategy") or "")
    active_instance = str(hb.get("active_instance") or "")
    now = time.time()
    since_update = now - updated_at
    elapsed = now - started_at

    # Completed but incomplete -> crashed before finishing
    if status == "completed" and rows_done < total:
        return True, f"status=completed but rows={rows_done}/{total} (crashed?)"

    # Aborted but pid still recorded as alive -> inconsistent
    if status.startswith("aborted") and rows_done < total:
        return True, f"status={status} rows={rows_done}/{total}"

    # Zero-progress stuck: fresh heartbeat but no rows and task stuck in prep
    if rows_done == 0 and elapsed > stale_seconds:
        has_active = bool(active_strategy) or bool(active_instance)
        if has_active and active_elapsed_s == 0:
            return True, (
                f"ZERO_PROGRESS rows=0/{total} elapsed={elapsed:.0f}s "
                f"active={active_strategy}:{active_instance} active_elapsed_s=0 "
                f"(stuck in prep, no task actually started)"
            )
        if has_active and active_elapsed_s > 0 and active_elapsed_s > stale_seconds:
            return True, (
                f"ZERO_PROGRESS rows=0/{total} elapsed={elapsed:.0f}s "
                f"active_elapsed_s={active_elapsed_s:.0f}s "
                f"(single task stuck for too long)"
            )
        if not has_active and elapsed > stale_seconds:
            return True, (
                f"ZERO_PROGRESS rows=0/{total} elapsed={elapsed:.0f}s "
                f"no active task (setup or thread pool blocked?)"
            )

    # Heartbeat not updating AND run not finished -> stuck
    if since_update > stale_seconds:
        return True, (
            f"no update for {since_update:.0f}s, rows={rows_done}/{total}, "
            f"elapsed={elapsed:.0f}s"
        )

    return False, ""


def _count_tier(backend_picks, tier: int) -> int:
    if not backend_picks:
        return 0
    suffix = str(tier)
    return sum(1 for p in backend_picks if str(p).endswith(suffix) or f"tier{suffix}" in str(p))


# ── Compact audit ────────────────────────────────────────────────────────────

def _pick_tier(pick) -> int:
    """Best-effort tier from a backend_pick string like 'tier2' or 'T2'."""
    s = str(pick).lower()
    if "tier3" in s or "t3" in s:
        return 3
    if "tier2" in s or "t2" in s:
        return 2
    if "tier1" in s or "t1" in s:
        return 1
    return 0


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
                "cost": 0.0, "turns": 0, "t1_turns": 0, "t2_turns": 0, "t3_turns": 0,
                "suspicious": 0, "no_trace": 0,
                "tasks": set(),
            }
        s = by_strategy[strat]
        s["total"] += 1
        s["cost"] += float(r.get("total_cost") or 0)
        turns = int(r.get("llm_turns") or 0)
        s["turns"] += turns
        picks = r.get("backend_picks") or []
        s["t1_turns"] += _count_tier(picks, 1)
        s["t2_turns"] += _count_tier(picks, 2)
        s["t3_turns"] += _count_tier(picks, 3)
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
        ct_t2 = sum(_count_tier(r.get("backend_picks") or [], 2) for r in ct_recs)
        ct_t3 = sum(_count_tier(r.get("backend_picks") or [], 3) for r in ct_recs)
        common_stats[strat] = {
            "tasks": len(ct_recs), "pass": ct_pass,
            "cost": ct_cost, "t2": ct_t2, "t3": ct_t3,
        }

    # Failure axis / class counts
    fail_classes = Counter(
        str(r.get("failure_class") or "unknown")
        for r in records if not r.get("harness_resolved")
    )
    fail_exits = Counter(
        str(r.get("exit_status") or "unknown")
        for r in records if not r.get("harness_resolved")
    )

    # Failure subtypes (020)
    fail_subtypes = Counter(
        str(r.get("failure_subtype") or "unknown")
        for r in records if not r.get("harness_resolved") and r.get("failure_subtype")
    )

    # Invoice accuracy: check if at least one record has provider actual cost
    invoice_accurate = any(_has_invoice_accurate_cost(r) for r in records)

    # PolicyMemory detection from records
    policy_memory_used = any(r.get("policy_memory_enabled") for r in records)
    policy_memory_source = ""
    prior_records = 0
    if policy_memory_used:
        for r in records:
            prior = r.get("routing_prior_summary") or {}
            if prior.get("policy_memory_source"):
                policy_memory_source = prior["policy_memory_source"]
                break
        prior_records = int(max(
            (r.get("routing_prior_summary") or {}).get("task_seen", 0)
            for r in records if r.get("routing_prior_summary")
        ) or 0)

    # StagnationExit PASS rate
    stag_pass = sum(
        1 for r in records
        if r.get("harness_resolved") and str(r.get("exit_status") or "").startswith("Stagnation")
    )

    # Failure owner / verdict axis counts
    owner_counts: dict[str, int] = {}
    axis_counts: dict[str, int] = {}
    for r in records:
        owner = str(r.get("failure_owner") or "")
        axis = str(r.get("verdict_axis") or "")
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
                "t1_turns": s["t1_turns"], "t2_turns": s["t2_turns"], "t3_turns": s["t3_turns"],
                "t3_share": s["t3_turns"] / max(s["t1_turns"] + s["t2_turns"] + s["t3_turns"], 1),
                "suspicious": s["suspicious"], "no_trace": s["no_trace"],
            }
            for strat, s in by_strategy.items()
        },
        "common_task_count": len(common_tasks),
        "common_stats": common_stats,
        "fail_classes": dict(fail_classes.most_common()),
        "fail_exits": dict(fail_exits.most_common()),
        "fail_subtypes": dict(fail_subtypes.most_common()),
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
    lines.append(f"{'strategy':<26} {'rows':>4} {'P':>2} {'F':>2} {'cost':>8} {'t/task':>6} {'T2':>4} {'T3':>4} {'T3%':>5} {'susp':>4}")
    lines.append("-" * 64)
    for strat in sorted(audit["by_strategy"]):
        s = audit["by_strategy"][strat]
        lines.append(
            f"{strat:<26} {s['total']:>4} {s['pass']:>2} {s['fail']:>2} "
            f"${s['cost']:>7.2f} {s['avg_turns']:>5.0f} "
            f"{s['t2_turns']:>4} {s['t3_turns']:>4} {s['t3_share']:>4.0%} {s['suspicious']:>4}"
        )

    # Common-task comparison
    if audit["common_task_count"] > 0:
        lines.append(banner)
        lines.append(f"COMMON-TASK ({audit['common_task_count']} tasks shared across all strategies)")
        lines.append(f"{'strategy':<26} {'tasks':>5} {'P':>3} {'cost':>8} {'T2':>4} {'T3':>4}")
        lines.append("-" * 64)
        for strat in sorted(audit["common_stats"]):
            cs = audit["common_stats"][strat]
            lines.append(
                f"{strat:<26} {cs['tasks']:>5} {cs['pass']:>3} "
                f"${cs['cost']:>7.2f} {cs['t2']:>4} {cs['t3']:>4}"
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


# ── Main checker (preserved from original) ────────────────────────────────────


def check_jsonl(jsonl_path: Path, heartbeat_stale_s: float = 600.0) -> dict:
    """Run all checks on a JSONL file. Returns summary dict."""
    records: list[dict] = []
    if not jsonl_path.is_file():
        return {"error": f"file not found: {jsonl_path}", "records": 0}

    for line in jsonl_path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    all_issues: list[str] = []
    all_issues.extend(_check_duplicates(records))
    all_issues.extend(_check_pass_evidence(records))
    all_issues.extend(_check_trace_coverage(records))
    all_issues.extend(_check_missing_fields(records))
    all_issues.extend(_check_desired_fields(records))
    all_issues.extend(_check_elapsed_sanity(records))
    ht_issues, ht_trust, ht_owner, ht_severity = _check_harness_trust(records)
    all_issues.extend(ht_issues)

    resolved = sum(1 for r in records if r.get("harness_resolved"))
    suspicious = sum(
        1 for r in records
        if r.get("harness_resolved") and not (r.get("harness_evidence") or {}).get("evidence_complete", False)
    )
    no_trace = sum(1 for r in records if int(r.get("turn_trace_count") or 0) <= 0)

    # Per-strategy summary
    by_strategy: dict[str, dict] = {}
    for r in records:
        strat = str(r.get("strategy", "unknown"))
        if strat not in by_strategy:
            by_strategy[strat] = {"total": 0, "pass": 0, "fail": 0, "no_trace": 0, "suspicious_pass": 0}
        by_strategy[strat]["total"] += 1
        if r.get("harness_resolved"):
            by_strategy[strat]["pass"] += 1
        else:
            by_strategy[strat]["fail"] += 1
        if int(r.get("turn_trace_count") or 0) <= 0:
            by_strategy[strat]["no_trace"] += 1
        if r.get("harness_resolved") and not (r.get("harness_evidence") or {}).get("evidence_complete", False):
            by_strategy[strat]["suspicious_pass"] += 1

    # Heartbeat check
    # Detect heartbeat files from JSONL run_series fields, AND from .heartbeat.json files
    # in the same directory (handles 0-record JSONL cases).
    runs_dir = jsonl_path.parent
    run_series_set = {str(r.get("run_series", "")) for r in records if r.get("run_series")}
    # Also scan for orphaned heartbeat files (JSONL has 0 rows but heartbeat exists)
    for hb_path in sorted(runs_dir.glob("*.heartbeat.json")):
        rs = hb_path.stem.replace(".heartbeat", "")
        if rs:
            run_series_set.add(rs)
    hb_stale = False
    hb_suspicious = False
    hb_summary = "no heartbeat files found"
    if run_series_set:
        hb_statuses: list[str] = []
        for rs in sorted(run_series_set):
            hb_path = runs_dir / f"{rs}.heartbeat.json"
            hb = load_heartbeat(hb_path)
            if hb is None:
                hb_statuses.append(f"{rs}: missing")
                continue

            done = int(hb.get("rows_done") or 0)
            total = int(hb.get("total_expected") or 0)
            status = str(hb.get("status") or "?")
            pid = int(hb.get("current_pid") or 0)
            stale = heartbeat_is_stale(hb, heartbeat_stale_s)
            pid_alive = _pid_is_alive(pid)

            # 0. Completed run: rows_done == total_expected → never stale
            if status == "completed" and done >= total:
                hb_statuses.append(f"{rs}: OK ({done}/{total} {status})")
                continue

            # 1. Dead PID detection — applies to ALL non-terminal states
            if pid > 0 and not pid_alive and done < total and status not in ("completed",):
                all_issues.append(
                    f"HEARTBEAT_DEAD_PID {rs}: pid={pid} status={status} rows={done}/{total}"
                )
                hb_suspicious = True
                hb_statuses.append(f"{rs}: DEAD_PID pid={pid} ({done}/{total} {status})")
                continue

            # 1.5 PREPARING_WITH_ACTIVE_TASK: status says preparing but task is running
            active_elapsed = float(hb.get("active_elapsed_s") or 0)
            active_str = str(hb.get("active_strategy") or "")
            active_inst = str(hb.get("active_instance") or "")
            if (status == "preparing" and active_str and active_inst
                    and active_elapsed > max(heartbeat_stale_s * 0.1, 30.0)):
                all_issues.append(
                    f"PREPARING_WITH_ACTIVE_TASK {rs}: status=preparing but "
                    f"active={active_str}:{active_inst} active_elapsed_s={active_elapsed:.0f}s "
                    f"rows={done}/{total} (pulse() may not transition preparing→running)"
                )
                hb_suspicious = True
                hb_statuses.append(f"{rs}: PREPARING_WITH_ACTIVE active_elapsed_s={active_elapsed:.0f}s")
                # Continue checking other conditions (may also be stuck/stale)

            # 2. Stale heartbeat — no update for too long
            if stale:
                hb_stale = True
                stuck, stuck_reason = _rows_stuck(hb, heartbeat_stale_s)
                if stuck:
                    all_issues.append(
                        f"HEARTBEAT_STUCK {rs}: pid={pid} status={status} {stuck_reason}"
                    )
                    hb_suspicious = True
                    hb_statuses.append(f"{rs}: STUCK pid={pid} ({done}/{total}) {stuck_reason}")
                else:
                    hb_statuses.append(f"{rs}: STALE pid={pid} updated={hb.get('updated_at', 0):.0f}")
                continue

            # 3. Rows stuck even with fresh heartbeat (pid alive but no progress)
            stuck, stuck_reason = _rows_stuck(hb, heartbeat_stale_s)
            if stuck:
                all_issues.append(
                    f"HEARTBEAT_STUCK {rs}: pid={pid} status={status} {stuck_reason}"
                )
                hb_suspicious = True
                hb_statuses.append(f"{rs}: STUCK pid={pid} ({done}/{total}) {stuck_reason}")
                continue

            hb_statuses.append(f"{rs}: OK ({done}/{total} {status})")
        hb_summary = "; ".join(hb_statuses)

    error_count = sum(1 for i in all_issues if i.startswith(("DUPLICATE", "SUSPICIOUS", "MISSING_FIELDS", "HEARTBEAT_DEAD_PID", "HEARTBEAT_STUCK")))
    warn_count = len(all_issues) - error_count

    compact = build_compact_audit(records)

    return {
        "records": len(records),
        "resolved": resolved,
        "failed": len(records) - resolved,
        "suspicious_passes": suspicious,
        "no_trace_rows": no_trace,
        "errors": error_count,
        "warnings": warn_count,
        "issues": all_issues,
        "by_strategy": by_strategy,
        "heartbeat_summary": hb_summary,
        "heartbeat_stale": hb_stale,
        "heartbeat_suspicious": hb_suspicious,
        "compact": compact,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick observability checker for experiment JSONL files")
    parser.add_argument("--jsonl", type=str, required=True, help="path to JSONL file")
    parser.add_argument("--heartbeat", type=float, default=600.0, help="stale heartbeat threshold in seconds (default 600)")
    parser.add_argument("--quiet", action="store_true", help="only print issues, no summary")
    parser.add_argument("--verbose", action="store_true", help="print old-style verbose output instead of compact")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    result = check_jsonl(jsonl_path, heartbeat_stale_s=args.heartbeat)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    if args.quiet:
        if result["issues"]:
            for issue in result["issues"]:
                print(issue)
        return

    # Default: compact audit
    print(format_compact_audit(result["compact"]))

    if result["issues"]:
        print()
        print(f"=== ISSUES ({len(result['issues'])}) ===")
        for issue in result["issues"]:
            prefix = "ERROR" if issue.startswith(("DUPLICATE", "SUSPICIOUS", "MISSING_FIELDS")) else "WARN"
            print(f"  [{prefix}] {issue}")

    # Verbose mode also shows the old by-strategy table
    if args.verbose:
        print()
        print(f"=== OBSERVABILITY CHECK ===")
        print(f"file: {jsonl_path}")
        print(f"records: {result['records']}  pass: {result['resolved']}  fail: {result['failed']}")
        print(f"suspicious_passes: {result['suspicious_passes']}  no_trace: {result['no_trace_rows']}")
        print(f"errors: {result['errors']}  warnings: {result['warnings']}")
        print(f"heartbeat: {result['heartbeat_summary']}")
        print()
        print("=== BY STRATEGY ===")
        for strat in sorted(result["by_strategy"]):
            s = result["by_strategy"][strat]
            print(
                f"  {strat:<28} total={s['total']:>2}  pass={s['pass']:>2}  fail={s['fail']:>2}  "
                f"no_trace={s['no_trace']:>2}  suspicious={s['suspicious_pass']:>2}"
            )
        print()

    if (result.get("heartbeat_stale") or result.get("heartbeat_suspicious")) and result.get("heartbeat_summary"):
        hb_msg = result["heartbeat_summary"]
        if any(tag in hb_msg for tag in ("STALE", "DEAD_PID", "STUCK")):
            print(f"\n⚠  HEARTBEAT WARNING: {hb_msg}")

    if result["errors"] > 0 or result.get("heartbeat_suspicious"):
        sys.exit(1)


if __name__ == "__main__":
    main()

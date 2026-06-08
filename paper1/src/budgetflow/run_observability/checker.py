"""Orchestrates run-observability checks for one JSONL artifact."""

from __future__ import annotations

import json
from pathlib import Path

from budgetflow.observability import heartbeat_is_stale, load_heartbeat
from budgetflow.failure_classification import is_score_abort, is_score_pass, is_score_true_fail

from .audit import build_compact_audit
from .checks import (
    _check_cross_series_duplicates,
    _check_partial_run,
    _check_policy_parallel,
    _check_shared_cap_starvation,
    _check_value_profile_fallback,
)
from .heartbeat import _pid_is_alive, _rows_stuck
from .schema import (
    _check_desired_fields,
    _check_duplicates,
    _check_elapsed_sanity,
    _check_harness_trust,
    _check_missing_fields,
    _check_observability_schema,
    _check_pass_evidence,
    _check_trace_coverage,
)

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
    all_issues.extend(_check_observability_schema(records))
    all_issues.extend(_check_elapsed_sanity(records))
    ht_issues, ht_trust, ht_owner, ht_severity = _check_harness_trust(records)
    all_issues.extend(ht_issues)
    runs_dir = jsonl_path.parent

    # Phase Z checker warnings
    all_issues.extend(_check_cross_series_duplicates(records))
    all_issues.extend(_check_partial_run(records, runs_dir))
    all_issues.extend(_check_shared_cap_starvation(records))
    all_issues.extend(_check_value_profile_fallback(records))
    all_issues.extend(_check_policy_parallel(records))

    resolved = sum(1 for r in records if is_score_pass(r))
    true_fail = sum(1 for r in records if is_score_true_fail(r))
    abort = sum(1 for r in records if is_score_abort(r))
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
            by_strategy[strat] = {
                "total": 0, "pass": 0, "fail": 0, "abort": 0,
                "no_trace": 0, "suspicious_pass": 0,
            }
        by_strategy[strat]["total"] += 1
        if is_score_pass(r):
            by_strategy[strat]["pass"] += 1
        elif is_score_true_fail(r):
            by_strategy[strat]["fail"] += 1
        else:
            by_strategy[strat]["abort"] += 1
        if int(r.get("turn_trace_count") or 0) <= 0:
            by_strategy[strat]["no_trace"] += 1
        if r.get("harness_resolved") and not (r.get("harness_evidence") or {}).get("evidence_complete", False):
            by_strategy[strat]["suspicious_pass"] += 1

    # Heartbeat check
    # Detect heartbeat files from JSONL run_series fields, AND from .heartbeat.json files
    # in the same directory (handles 0-record JSONL cases).
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

            # 0.5. Known-aborted runs: explicitly terminated, not current orphans
            if status.startswith("aborted"):
                hb_statuses.append(f"{rs}: ABORTED ({done}/{total} {status})")
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

    compact = build_compact_audit(records)
    if compact.get("stored_verdict_mismatches"):
        all_issues.append(
            f"STALE_VERDICT_FIELDS: {compact['stored_verdict_mismatches']} rows have "
            "stored verdict fields that differ from current classifier output"
        )

    error_count = sum(1 for i in all_issues if i.startswith((
        "DUPLICATE", "SUSPICIOUS", "MISSING_FIELDS",
        "HARNESS_INVALID", "STALE_VERDICT_FIELDS",
        "HEARTBEAT_DEAD_PID", "HEARTBEAT_STUCK",
        "CROSS_SERIES_DUPLICATE", "PARTIAL_RUN", "SHARED_CAP_STARVATION",
        "VALUE_FALLBACK", "SEQUENTIAL_POLICY", "SCORE_STATUS_INVALID",
        "ABORT_REASON_MISSING", "SCORE_PASS_MISMATCH", "SCORE_FAIL_MISMATCH",
    )))
    warn_count = len(all_issues) - error_count

    return {
        "records": len(records),
        "resolved": resolved,
        "failed": true_fail,
        "aborted": abort,
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

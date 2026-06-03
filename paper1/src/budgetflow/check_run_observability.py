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
    run_series_set = {str(r.get("run_series", "")) for r in records if r.get("run_series")}
    hb_stale = False
    hb_summary = "no heartbeat files found"
    if run_series_set:
        runs_dir = jsonl_path.parent
        hb_statuses: list[str] = []
        for rs in sorted(run_series_set):
            hb_path = runs_dir / f"{rs}.heartbeat.json"
            hb = load_heartbeat(hb_path)
            if hb is None:
                hb_statuses.append(f"{rs}: missing")
            elif heartbeat_is_stale(hb, heartbeat_stale_s):
                hb_stale = True
                hb_statuses.append(f"{rs}: STALE (updated={hb.get('updated_at', 0)})")
            else:
                done = hb.get("rows_done", 0)
                total = hb.get("total_expected", 0)
                status = hb.get("status", "?")
                pid = int(hb.get("current_pid") or 0)
                if status == "running" and done < total and not _pid_is_alive(pid):
                    all_issues.append(f"HEARTBEAT_DEAD_PID {rs}: pid={pid} status=running rows={done}/{total}")
                    hb_stale = True
                    hb_statuses.append(f"{rs}: DEAD_PID pid={pid} ({done}/{total} {status})")
                else:
                    hb_statuses.append(f"{rs}: OK ({done}/{total} {status})")
        hb_summary = "; ".join(hb_statuses)

    error_count = sum(1 for i in all_issues if i.startswith(("DUPLICATE", "SUSPICIOUS", "MISSING_FIELDS", "HEARTBEAT_DEAD_PID")))
    warn_count = len(all_issues) - error_count

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
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick observability checker for experiment JSONL files")
    parser.add_argument("--jsonl", type=str, required=True, help="path to JSONL file")
    parser.add_argument("--heartbeat", type=float, default=600.0, help="stale heartbeat threshold in seconds (default 600)")
    parser.add_argument("--quiet", action="store_true", help="only print issues, no summary")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    result = check_jsonl(jsonl_path, heartbeat_stale_s=args.heartbeat)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    if not args.quiet:
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

    if result["issues"]:
        print(f"=== ISSUES ({len(result['issues'])}) ===")
        for issue in result["issues"]:
            prefix = "ERROR" if issue.startswith(("DUPLICATE", "SUSPICIOUS", "MISSING_FIELDS")) else "WARN"
            print(f"  [{prefix}] {issue}")
    elif not args.quiet:
        print("No issues found.")

    if result["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

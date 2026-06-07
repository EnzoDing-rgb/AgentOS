"""CLI for run-observability checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checker import check_jsonl
from .report import format_compact_audit

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
            prefix = "ERROR" if issue.startswith((
                "DUPLICATE", "SUSPICIOUS", "MISSING_FIELDS",
                "HARNESS_INVALID", "STALE_VERDICT_FIELDS",
            )) else "WARN"
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

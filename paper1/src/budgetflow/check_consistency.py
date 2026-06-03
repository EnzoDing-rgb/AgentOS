"""Lightweight JSONL/checkpoint/summary consistency checker for BudgetFlow runs.

Usage:
  PYTHONPATH=paper1/src .venv/bin/python -m budgetflow.check_consistency --stem postfix_011_sanity-0
"""

import argparse
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = [
    "instance_id", "strategy", "total_cost",
    "harness_resolved", "llm_turns", "exit_status", "failure_class",
]


def load_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_checkpoint(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {}


def check_duplicates(rows: list[dict]) -> list[str]:
    seen: dict[tuple, int] = {}
    for r in rows:
        key = (r.get("instance_id"), r.get("strategy"))
        seen[key] = seen.get(key, 0) + 1
    return [f"  {k[0]} / {k[1]} appears {c} times"
            for k, c in seen.items() if c > 1]


def check_checkpoint_alignment(rows: list[dict], checkpoint: dict) -> list[str]:
    issues = []
    jsonl_keys = {(r["instance_id"], r["strategy"]) for r in rows}
    strategies = checkpoint.get("strategies") or {}

    for sname, sdata in strategies.items():
        completed = set(sdata.get("completed_tasks") or [])
        in_flight = sdata.get("in_flight_task")
        for iid in completed:
            if (iid, sname) not in jsonl_keys:
                issues.append(f"  cp completed_task {sname}/{iid} has no JSONL row")
        if in_flight and in_flight in completed:
            issues.append(f"  cp in_flight_task {sname}/{in_flight} also in completed_tasks")

    for iid, sname in jsonl_keys:
        sdata = strategies.get(sname)
        if sdata is None:
            issues.append(f"  JSONL strategy {sname} not in checkpoint")
            continue
        completed = set(sdata.get("completed_tasks") or [])
        in_flight = sdata.get("in_flight_task")
        if iid not in completed and iid != in_flight:
            issues.append(f"  JSONL row {sname}/{iid} not in cp completed_tasks or in_flight")

    return issues


def check_cost_consistency(rows: list[dict], checkpoint: dict) -> list[str]:
    """cp batch_spent must match last JSONL row's batch_spent for each strategy."""
    issues = []
    by_strategy: dict[str, list[dict]] = {}
    for r in rows:
        by_strategy.setdefault(r["strategy"], []).append(r)

    for sname, sdata in (checkpoint.get("strategies") or {}).items():
        cp_spent = sdata.get("batch_spent", 0.0)
        jrows = by_strategy.get(sname, [])
        if not jrows:
            continue
        last_bs = jrows[-1].get("batch_spent", 0.0)
        if abs(cp_spent - last_bs) > 0.0001:
            issues.append(
                f"  {sname}: cp batch_spent={cp_spent:.6f} != "
                f"last_row.batch_spent={last_bs:.6f}"
            )
    return issues


def check_missing_tasks(rows: list[dict], checkpoint: dict) -> list[str]:
    issues = []
    total_runs = checkpoint.get("total_runs", 0)
    if total_runs and len(rows) != total_runs:
        issues.append(f"  cp total_runs={total_runs} but JSONL has {len(rows)} rows")

    expected: set[tuple[str, str]] = set()
    for sname, sdata in (checkpoint.get("strategies") or {}).items():
        for iid in (sdata.get("completed_tasks") or []):
            expected.add((iid, sname))
        if sdata.get("in_flight_task"):
            expected.add((sdata["in_flight_task"], sname))

    actual = {(r["instance_id"], r["strategy"]) for r in rows}
    for iid, sname in sorted(expected - actual):
        issues.append(f"  expected {sname}/{iid} missing from JSONL")
    for iid, sname in sorted(actual - expected):
        issues.append(f"  extra {sname}/{iid} in JSONL not expected")
    return issues


def check_field_completeness(rows: list[dict]) -> list[str]:
    issues: list[str] = []
    missing: dict[str, int] = {}
    trace_zero = 0

    for r in rows:
        for field in REQUIRED_FIELDS:
            if field not in r or r[field] is None:
                missing[field] = missing.get(field, 0) + 1
        if r.get("turn_trace_count") in (None, 0):
            trace_zero += 1

    total = len(rows)
    for fname, count in missing.items():
        issues.append(f"  field '{fname}' missing in {count}/{total} rows")

    if trace_zero == total:
        issues.append(f"  turn_trace_count=0 in all {total} rows (traces not collected)")
    elif trace_zero > 0:
        issues.append(f"  turn_trace_count=0 in {trace_zero}/{total} rows")
    return issues


_CHECKS = [
    ("(a) No duplicates", "All (instance_id, strategy) pairs unique",
     "DUPLICATES FOUND", check_duplicates, ["rows"]),
    ("(b) Checkpoint/JSONL alignment", "All rows aligned between checkpoint and JSONL",
     "MISALIGNMENT FOUND", check_checkpoint_alignment, ["rows", "checkpoint"]),
    ("(c) Cost consistency", "batch_spent matches last JSONL row for each strategy",
     "COST MISMATCH", check_cost_consistency, ["rows", "checkpoint"]),
    ("(d) No missing tasks", "Row count matches total_runs, no missing pairs",
     "MISSING/EXTRA TASKS", check_missing_tasks, ["rows", "checkpoint"]),
    ("(e) Field completeness", "All required fields present and non-null",
     "FIELD ISSUES", check_field_completeness, ["rows"]),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="BudgetFlow consistency checker")
    parser.add_argument("--stem", required=True)
    parser.add_argument("--runs-dir", default="paper1/data/runs")
    args = parser.parse_args()
    runs_dir = Path(args.runs_dir)

    jsonl_path = runs_dir / f"{args.stem}.jsonl"
    cp_path = runs_dir / f"{args.stem}.checkpoint.json"
    if not jsonl_path.is_file():
        print(f"ERROR: JSONL not found: {jsonl_path}"); sys.exit(1)
    if not cp_path.is_file():
        print(f"ERROR: checkpoint not found: {cp_path}"); sys.exit(1)

    rows = load_jsonl(jsonl_path)
    checkpoint = load_checkpoint(cp_path)
    total_warnings = 0

    for title, ok_msg, fail_msg, check_fn, arg_names in _CHECKS:
        print(f"\n--- {title} ---")
        kwargs = {n: {"rows": rows, "checkpoint": checkpoint}[n] for n in arg_names}
        issues = check_fn(**kwargs)
        if issues:
            print(f"  ✗ {fail_msg} ({len(issues)})")
            for i in issues:
                print(i)
            total_warnings += len(issues)
        else:
            print(f"  ✓ {ok_msg}")

    print(f"\n--- (f) Summary ---")
    if total_warnings == 0:
        print("  CLEAN")
    else:
        print(f"  ISSUES FOUND ({total_warnings} warnings)")

    sys.exit(0 if total_warnings == 0 else 1)


if __name__ == "__main__":
    main()

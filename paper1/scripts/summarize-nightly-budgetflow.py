#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def summarize(stem: str, run_dir: Path) -> None:
    rows = load_rows(run_dir / f"{stem}.jsonl")
    print(f"=== {stem} ===")
    if not rows:
        print("missing or empty")
        print()
        return

    unique = {(row.get("strategy"), row.get("instance_id")) for row in rows}
    print(f"records={len(rows)} unique_runs={len(unique)}")
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_strategy[row["strategy"]].append(row)

    for strategy, items in sorted(by_strategy.items()):
        passed = sum(1 for row in items if row.get("harness_resolved"))
        cost = sum(float(row.get("task_cost") or row.get("total_cost") or 0) for row in items)
        turns = sum(int(row.get("llm_turns") or 0) for row in items)
        failures = Counter(row.get("failure_class") or "unknown" for row in items)
        fail_s = ",".join(f"{key}:{value}" for key, value in sorted(failures.items()))
        print(f"{strategy}: pass={passed}/{len(items)} cost={cost:.1f} turns={turns} classes={fail_s}")
    print()


def main() -> None:
    import sys

    run_dir = Path(__file__).resolve().parents[1] / "data" / "runs"
    stems = sys.argv[1:] or [
        "rescue_stoploss_targeted_v2",
        "budgetflow_goldpass5_autobudget_p030_v1",
    ]
    for stem in stems:
        summarize(stem, run_dir)


if __name__ == "__main__":
    main()

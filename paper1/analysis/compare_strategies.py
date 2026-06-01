#!/usr/bin/env python3
"""Compare budgetflow vs budget_only strategies from a jsonl run file."""
import json
import sys
from collections import defaultdict
from pathlib import Path

COST_SCALE = 100  # divide raw governor units for readable display (not RMB/USD)

def analyze(jsonl_path: str) -> None:
    lines = [json.loads(l) for l in Path(jsonl_path).read_text().splitlines() if l.strip()]
    # Filter out BadRequestError garbage records
    lines = [r for r in lines if r.get("exit_status") != "BadRequestError"]

    by_strat = defaultdict(list)
    for rec in lines:
        by_strat[rec["strategy"]].append(rec)

    abbrev = {
        "all_pro": "apro", "all_spark_tight": "as-T", "all_spark_loose": "as-L",
        "budgetflow_full_loose": "bf-L", "budgetflow_full_tight": "bf-T",
        "budget_only_loose": "bo-L", "budget_only_tight": "bo-T",
    }

    print(f"{'strategy':<6} {'tasks':>5} {'PASS':>5} {'FAIL':>5} {'resolve%':>8} {'avg_cost':>8} {'avg_turns':>9}")
    print("-" * 55)

    for strat in sorted(by_strat.keys()):
        tasks = by_strat[strat]
        n = len(tasks)
        resolved = sum(1 for t in tasks if t.get("harness_resolved"))
        avg_cost = sum(t["total_cost"] for t in tasks) / n / COST_SCALE if n else 0
        avg_turns = sum(t["llm_turns"] for t in tasks) / n if n else 0
        label = abbrev.get(strat, strat)
        print(f"{label:<6} {n:>5} {resolved:>5} {n-resolved:>5} {100*resolved/n:>7.1f}% {avg_cost:>8.1f} {avg_turns:>9.1f}")

    print()

    # Key comparisons
    def show_comparison(name1, group1, name2, group2):
        r1 = sum(1 for t in group1 if t.get("harness_resolved"))
        r2 = sum(1 for t in group2 if t.get("harness_resolved"))
        c1 = sum(t["total_cost"] for t in group1) / COST_SCALE
        c2 = sum(t["total_cost"] for t in group2) / COST_SCALE
        n1, n2 = len(group1), len(group2)
        if n1 == 0 or n2 == 0:
            return
        print(f"{name1}: {r1}/{n1} resolved, total={c1:.1f}, avg={c1/n1:.1f}")
        print(f"{name2}: {r2}/{n2} resolved, total={c2:.1f}, avg={c2/n2:.1f}")
        if r1 > r2:
            print(f"  => {name1} wins on resolution (+{r1-r2})")
        elif r2 > r1:
            print(f"  => {name2} wins on resolution (+{r2-r1})")
        print(f"  cost/resolve: {name1}={c1/max(1,r1):.1f}, {name2}={c2/max(1,r2):.1f}")
        print()

    bf_loose = [t for t in lines if t["strategy"] == "budgetflow_full_loose"]
    bo_loose = [t for t in lines if t["strategy"] == "budget_only_loose"]
    bf_tight = [t for t in lines if t["strategy"] == "budgetflow_full_tight"]
    bo_tight = [t for t in lines if t["strategy"] == "budget_only_tight"]
    all_pro = [t for t in lines if t["strategy"] == "all_pro"]

    print("=== LOOSE BUDGET ===")
    show_comparison("bf-loose", bf_loose, "bo-loose", bo_loose)
    show_comparison("bf-loose", bf_loose, "all_pro", all_pro)

    print("=== TIGHT BUDGET ===")
    show_comparison("bf-tight", bf_tight, "bo-tight", bo_tight)

    # Per-task
    print("=== PER-TASK (loose) ===")
    bf_by_task = {t["instance_id"]: t for t in bf_loose}
    bo_by_task = {t["instance_id"]: t for t in bo_loose}
    for task_id in sorted(set(list(bf_by_task) + list(bo_by_task))):
        bf = bf_by_task.get(task_id)
        bo = bo_by_task.get(task_id)
        bf_r = "PASS" if bf and bf.get("harness_resolved") else "FAIL" if bf else "---"
        bo_r = "PASS" if bo and bo.get("harness_resolved") else "FAIL" if bo else "---"
        bf_c = (bf["total_cost"] if bf else 0) / COST_SCALE
        bo_c = (bo["total_cost"] if bo else 0) / COST_SCALE
        short = task_id.split("__")[-1]
        print(f"  {short}: bf={bf_r}({bf_c:.1f}) bo={bo_r}({bo_c:.1f})")

if __name__ == "__main__":
    analyze(sys.argv[1] if len(sys.argv) > 1 else "data/runs/policy_10x7-1.jsonl")

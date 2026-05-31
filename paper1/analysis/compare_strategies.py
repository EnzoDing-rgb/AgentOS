#!/usr/bin/env python3
"""Compare budgetflow vs budget_only strategies from a jsonl run file."""
import json
import sys
from collections import defaultdict
from pathlib import Path

def analyze(jsonl_path: str) -> None:
    lines = [json.loads(l) for l in Path(jsonl_path).read_text().splitlines() if l.strip()]

    by_strat = defaultdict(list)
    for rec in lines:
        by_strat[rec["strategy"]].append(rec)

    print(f"{'strategy':<30} {'tasks':>5} {'resolved':>8} {'resolve%':>8} {'avg_cost':>9} {'avg_turns':>9} {'spark%':>6} {'flash%':>6} {'pro%':>6}")
    print("-" * 100)

    for strat in sorted(by_strat.keys()):
        tasks = by_strat[strat]
        n = len(tasks)
        resolved = sum(1 for t in tasks if t.get("harness_resolved"))
        avg_cost = sum(t["total_cost"] for t in tasks) / n if n else 0
        avg_turns = sum(t["llm_turns"] for t in tasks) / n if n else 0

        # Model mix
        total_picks = sum(len(t.get("backend_picks", [])) for t in tasks)
        spark = sum(sum(1 for p in t.get("backend_picks", []) if "spark" in p) for t in tasks)
        flash = sum(sum(1 for p in t.get("backend_picks", []) if "flash" in p) for t in tasks)
        pro = sum(sum(1 for p in t.get("backend_picks", []) if "pro" in p) for t in tasks)

        print(f"{strat:<30} {n:>5} {resolved:>8} {100*resolved/n:>7.1f}% {avg_cost:>9.0f} {avg_turns:>9.1f} {100*spark/total_picks:>5.0f}% {100*flash/total_picks:>5.0f}% {100*pro/total_picks:>5.0f}%")

    print()

    # Key comparison: budgetflow vs budget_only
    bf_loose = [t for t in lines if t["strategy"] == "budgetflow_full_loose"]
    bo_loose = [t for t in lines if t["strategy"] == "budget_only_loose"]
    bf_tight = [t for t in lines if t["strategy"] == "budgetflow_full_tight"]
    bo_tight = [t for t in lines if t["strategy"] == "budget_only_tight"]
    all_pro = [t for t in lines if t["strategy"] == "all_pro"]

    def show_comparison(name1, group1, name2, group2):
        r1 = sum(1 for t in group1 if t.get("harness_resolved"))
        r2 = sum(1 for t in group2 if t.get("harness_resolved"))
        c1 = sum(t["total_cost"] for t in group1)
        c2 = sum(t["total_cost"] for t in group2)
        n1, n2 = len(group1), len(group2)
        print(f"{name1}: {r1}/{n1} resolved, total_cost={c1:.0f}, avg={c1/n1:.0f}" if n1 else f"{name1}: no data")
        print(f"{name2}: {r2}/{n2} resolved, total_cost={c2:.0f}, avg={c2/n2:.0f}" if n2 else f"{name2}: no data")
        if r1 > r2:
            print(f"  => {name1} wins on resolution (+{r1-r2})")
        elif r2 > r1:
            print(f"  => {name2} wins on resolution (+{r2-r1})")
        if n1 and n2:
            print(f"  => cost per resolved: {name1}={c1/max(1,r1):.0f}, {name2}={c2/max(1,r2):.0f}")
        print()

    print("=== LOOSE BUDGET ===")
    show_comparison("budgetflow_full_loose", bf_loose, "budget_only_loose", bo_loose)
    show_comparison("budgetflow_full_loose", bf_loose, "all_pro", all_pro)

    print("=== TIGHT BUDGET ===")
    show_comparison("budgetflow_full_tight", bf_tight, "budget_only_tight", bo_tight)

    # Per-task comparison
    print("=== PER-TASK (loose) ===")
    bf_by_task = {t["instance_id"]: t for t in bf_loose}
    bo_by_task = {t["instance_id"]: t for t in bo_loose}
    for task_id in sorted(set(list(bf_by_task) + list(bo_by_task))):
        bf = bf_by_task.get(task_id)
        bo = bo_by_task.get(task_id)
        bf_r = "PASS" if bf and bf.get("harness_resolved") else "FAIL"
        bo_r = "PASS" if bo and bo.get("harness_resolved") else "FAIL"
        bf_c = bf["total_cost"] if bf else 0
        bo_c = bo["total_cost"] if bo else 0
        print(f"  {task_id.split('__')[-1]}: bf={bf_r}({bf_c:.0f}) bo={bo_r}({bo_c:.0f})")

if __name__ == "__main__":
    analyze(sys.argv[1] if len(sys.argv) > 1 else "data/runs/policy_10x7-1.jsonl")

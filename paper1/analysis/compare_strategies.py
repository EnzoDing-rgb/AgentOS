#!/usr/bin/env python3
"""Compare budgetflow vs budget_only strategies from a jsonl run file."""
import json
import sys
from collections import defaultdict
from pathlib import Path

COST_SCALE = 100

DISPLAY_NAMES = {
    "all_pro": "all_pro (T3)",
    "all_t1_tight": "t1-only tight",
    "all_t1_loose": "t1-only loose",
    "all_spark_tight": "t1-only tight",
    "all_spark_loose": "t1-only loose",
    "all_flash_tight": "t1-only tight",
    "all_flash_loose": "t1-only loose",
    "budgetflow_full_loose": "bf-full loose",
    "budgetflow_full_tight": "bf-full tight",
    "budget_only_loose": "bo-only loose",
    "budget_only_tight": "bo-only tight",
}

DISPLAY_ORDER = [
    "budget_only_tight", "budgetflow_full_tight",
    "budget_only_loose", "budgetflow_full_loose",
    "all_pro",
    "all_t1_tight", "all_t1_loose",
    "all_spark_tight", "all_spark_loose",
    "all_flash_tight", "all_flash_loose",
]


def analyze(jsonl_path: str) -> str:
    lines = [json.loads(l) for l in Path(jsonl_path).read_text().splitlines() if l.strip()]
    lines = [r for r in lines if r.get("exit_status") != "BadRequestError"]

    # Merge old strategy names
    _ALIASES = {"all_spark_tight": "all_t1_tight", "all_spark_loose": "all_t1_loose",
                 "all_flash_tight": "all_t1_tight", "all_flash_loose": "all_t1_loose"}
    for r in lines:
        r["strategy"] = _ALIASES.get(r["strategy"], r["strategy"])

    by_strat = defaultdict(list)
    for rec in lines:
        by_strat[rec["strategy"]].append(rec)

    out = []
    out.append(f"{'strategy':<22} {'done':>5} {'PASS':>5} {'FAIL':>5} {'rate':>6} {'avg_cost':>8} {'cost/res':>8}")
    out.append("-" * 68)

    ordered = [s for s in DISPLAY_ORDER if s in by_strat]
    remaining = [s for s in sorted(by_strat) if s not in DISPLAY_ORDER]
    for strat in ordered + remaining:
        tasks = by_strat[strat]
        n = len(tasks)
        resolved = sum(1 for t in tasks if t.get("harness_resolved"))
        avg_cost = sum(t["total_cost"] for t in tasks) / n / COST_SCALE if n else 0
        cost_per = sum(t["total_cost"] for t in tasks) / max(1, resolved) / COST_SCALE
        label = DISPLAY_NAMES.get(strat, strat)
        out.append(f"{label:<22} {n:>5} {resolved:>5} {n-resolved:>5} {100*resolved/n:>5.0f}% {avg_cost:>8.1f} {cost_per:>8.1f}")

    out.append("")

    def show(n1, g1, n2, g2):
        r1 = sum(1 for t in g1 if t.get("harness_resolved"))
        r2 = sum(1 for t in g2 if t.get("harness_resolved"))
        c1 = sum(t["total_cost"] for t in g1) / COST_SCALE
        c2 = sum(t["total_cost"] for t in g2) / COST_SCALE
        n1n, n2n = len(g1), len(g2)
        if n1n == 0 or n2n == 0:
            return
        out.append(f"  {n1}: {r1}/{n1n} resolves, cost/resolve={c1/max(1,r1):.1f}")
        out.append(f"  {n2}: {r2}/{n2n} resolves, cost/resolve={c2/max(1,r2):.1f}")
        delta = (c1/max(1,r1) - c2/max(1,r2)) / max(0.01, c2/max(1,r2)) * 100
        if r1 > r2:
            out.append(f"  => {n1} wins: +{r1-r2} resolves")
        elif r2 > r1:
            out.append(f"  => {n2} wins: +{r2-r1} resolves")
        else:
            winner = n1 if c1/max(1,r1) < c2/max(1,r2) else n2
            out.append(f"  => same resolves, {winner} cheaper ({abs(delta):.0f}%)")
        out.append("")

    bf_L = [t for t in lines if t["strategy"] == "budgetflow_full_loose"]
    bo_L = [t for t in lines if t["strategy"] == "budget_only_loose"]
    bf_T = [t for t in lines if t["strategy"] == "budgetflow_full_tight"]
    bo_T = [t for t in lines if t["strategy"] == "budget_only_tight"]
    apro = [t for t in lines if t["strategy"] == "all_pro"]

    out.append("=== LOOSE ===")
    show("bf-loose", bf_L, "bo-loose", bo_L)
    show("bf-loose", bf_L, "all_pro", apro)
    out.append("=== TIGHT ===")
    show("bf-tight", bf_T, "bo-tight", bo_T)

    return "\n".join(out)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/runs/policy_10x7-1.jsonl"
    print(analyze(path))

#!/usr/bin/env python3
"""Compare budgetflow vs budget_only strategies from a jsonl run file."""
import json
import sys
from collections import defaultdict
from pathlib import Path

COST_SCALE = 100

DISPLAY_NAMES = {
    "all_pro": "all_pro",
    "all_t1_tight": "T1-only tight",
    "all_t1_loose": "T1-only loose",
    "all_spark_tight": "T1-only tight",
    "all_spark_loose": "T1-only loose",
    "all_flash_tight": "T1-only tight",
    "all_flash_loose": "T1-only loose",
    "budgetflow_full_loose": "BudgetFlow loose",
    "budgetflow_full_tight": "BudgetFlow tight",
    "budget_only_loose": "BudgetOnly loose",
    "budget_only_tight": "BudgetOnly tight",
    "stage_blind_loose": "StageBlind loose",
    "stage_blind_tight": "StageBlind tight",
}

DISPLAY_ORDER = [
    "budget_only_tight", "stage_blind_tight", "budgetflow_full_tight",
    "budget_only_loose", "stage_blind_loose", "budgetflow_full_loose",
    "all_pro",
    "all_t1_tight", "all_t1_loose",
    "all_spark_tight", "all_spark_loose",
    "all_flash_tight", "all_flash_loose",
]


def _append_stage_tier_mix(out: list[str], lines: list[dict]) -> None:
    """Per-strategy stage→tier histogram from turn_traces."""
    from collections import Counter
    targets = {"budgetflow_full_tight", "budgetflow_full_loose",
               "budget_only_tight", "budget_only_loose",
               "stage_blind_tight", "stage_blind_loose"}
    out.append("--- Stage-tier mix (bf/bo/sb) ---")
    for strat in sorted(targets):
        tasks = [t for t in lines if t.get("strategy") == strat]
        if not tasks:
            continue
        stage_tier: dict[str, Counter] = defaultdict(Counter)
        total_turns = 0
        for t in tasks:
            for tr in (t.get("turn_traces") or []):
                stage = (tr.get("stage") or "unknown").lower()
                tier = tr.get("backend_tier", 0)
                stage_tier[stage][tier] += 1
                total_turns += 1
        if not total_turns:
            continue
        label = DISPLAY_NAMES.get(strat, strat)
        parts = [f"{label}: "]
        for stage in ("localization", "repair", "validation"):
            sc = stage_tier.get(stage)
            if sc:
                total = sum(sc.values())
                tier_str = "/".join(f"T{t}={sc[t]}" for t in sorted(sc))
                parts.append(f"{stage}[{total}]={{{tier_str}}} ")
        out.append("".join(parts))
    out.append("")


def _score_status(row: dict) -> str:
    status = str(row.get("score_status") or "")
    if status in {"pass", "true_fail", "abort"}:
        return status
    return "pass" if row.get("harness_resolved") else "true_fail"


def _is_pass(row: dict) -> bool:
    return _score_status(row) == "pass"


def _is_true_fail(row: dict) -> bool:
    return _score_status(row) == "true_fail"


def _is_abort(row: dict) -> bool:
    return _score_status(row) == "abort"


def _append_patch_but_fail(out: list[str], lines: list[dict]) -> None:
    """Count scoreable gold_edited=True but unresolved per strategy."""
    out.append("--- Patch-but-true-fail rate (scoreable gold_edited=True, score_status=true_fail) ---")
    targets = {"budgetflow_full_tight", "budgetflow_full_loose",
               "budget_only_tight", "budget_only_loose",
               "stage_blind_tight", "stage_blind_loose", "all_pro"}
    for strat in sorted(targets):
        tasks = [t for t in lines if t.get("strategy") == strat]
        gold_hit = sum(1 for t in tasks if t.get("agent_gold_edited"))
        gold_fail = sum(1 for t in tasks if t.get("agent_gold_edited") and _is_true_fail(t))
        gold_win = gold_hit - gold_fail
        label = DISPLAY_NAMES.get(strat, strat)
        if gold_hit:
            out.append(f"  {label:<22} gold_hit={gold_hit}  resolved={gold_win}  "
                       f"patch_but_fail={gold_fail} ({100*gold_fail/gold_hit:.0f}%)")
    out.append("")


def _append_no_progress_signature(out: list[str], lines: list[dict]) -> None:
    """Last 5 turns before StagnationExit: stage/tier distribution."""
    out.append("--- No-progress signature (last 5 turns of StagnationExit) ---")
    stag_tasks = [t for t in lines if t.get("exit_status") == "StagnationExit" and t.get("turn_traces")]
    if not stag_tasks:
        out.append("  (no StagnationExit tasks with turn traces)")
        out.append("")
        return
    from collections import Counter
    stage_before_stall: Counter = Counter()
    tier_before_stall: Counter = Counter()
    for t in stag_tasks:
        traces = t.get("turn_traces") or []
        for tr in traces[-5:]:
            stage_before_stall[tr.get("stage") or "unknown"] += 1
            tier_before_stall[tr.get("backend_tier", 0)] += 1
    out.append(f"  n={len(stag_tasks)} stagnation tasks")
    out.append(f"  stage (last 5 turns): {dict(stage_before_stall.most_common())}")
    out.append(f"  tier  (last 5 turns): {dict(sorted(tier_before_stall.items()))}")
    out.append("")


def _append_discordant_tasks(
    out: list[str], lines: list[dict],
    bf_L: list, bo_L: list, bf_T: list, bo_T: list,
) -> None:
    """Print tasks where BO and BF disagree on resolve."""
    out.append("--- Discordant tasks (bo != bf) ---")

    def _resolved_map(task_list):
        return {t["instance_id"]: _is_pass(t) for t in task_list if not _is_abort(t)}

    for label, bf, bo in [("loose", bf_L, bo_L), ("tight", bf_T, bo_T)]:
        bf_map = _resolved_map(bf)
        bo_map = _resolved_map(bo)
        common = set(bf_map) & set(bo_map)
        disc = []
        for iid in common:
            if bf_map[iid] != bo_map[iid]:
                disc.append((iid, bf_map[iid], bo_map[iid]))
        if disc:
            out.append(f"  {label}: {len(disc)} discordant tasks")
            for iid, bf_r, bo_r in disc:
                winner = "bf" if bf_r else "bo"
                out.append(f"    {iid}  bf={'PASS' if bf_r else 'FAIL'} bo={'PASS' if bo_r else 'FAIL'} -> {winner}")
        else:
            out.append(f"  {label}: 0 discordant")
    out.append("")


def analyze(jsonl_path: str) -> str:
    lines = [json.loads(l) for l in Path(jsonl_path).read_text().splitlines() if l.strip()]
    lines = [r for r in lines if not _is_abort(r)]

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
        resolved = sum(1 for t in tasks if _is_pass(t))
        avg_cost = sum(t["total_cost"] for t in tasks) / n / COST_SCALE if n else 0
        cost_per = sum(t["total_cost"] for t in tasks) / max(1, resolved) / COST_SCALE
        label = DISPLAY_NAMES.get(strat, strat)
        out.append(f"{label:<22} {n:>5} {resolved:>5} {n-resolved:>5} {100*resolved/n:>5.0f}% {avg_cost:>8.1f} {cost_per:>8.1f}")

    out.append("")

    def show(n1, g1, n2, g2):
        g1 = [t for t in g1 if not _is_abort(t)]
        g2 = [t for t in g2 if not _is_abort(t)]
        r1 = sum(1 for t in g1 if _is_pass(t))
        r2 = sum(1 for t in g2 if _is_pass(t))
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
    sb_L = [t for t in lines if t["strategy"] == "stage_blind_loose"]
    bf_T = [t for t in lines if t["strategy"] == "budgetflow_full_tight"]
    bo_T = [t for t in lines if t["strategy"] == "budget_only_tight"]
    sb_T = [t for t in lines if t["strategy"] == "stage_blind_tight"]
    apro = [t for t in lines if t["strategy"] == "all_pro"]

    out.append("=== LOOSE ===")
    show("bf-loose", bf_L, "bo-loose", bo_L)
    show("bf-loose", bf_L, "sb-loose", sb_L)
    show("bf-loose", bf_L, "all_pro", apro)
    out.append("=== TIGHT ===")
    show("bf-tight", bf_T, "bo-tight", bo_T)
    show("bf-tight", bf_T, "sb-tight", sb_T)

    # ── trace-driven diagnostics (only when turn_traces present) ──
    _has_traces = any(t.get("turn_traces") for t in lines)
    if _has_traces:
        out.append("=== DIAGNOSTICS (turn-trace) ===")
        _append_stage_tier_mix(out, lines)
        _append_patch_but_fail(out, lines)
        _append_no_progress_signature(out, lines)
        _append_discordant_tasks(out, lines, bf_L, bo_L, bf_T, bo_T)

    return "\n".join(out)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/runs/policy_10x7-1.jsonl"
    print(analyze(path))

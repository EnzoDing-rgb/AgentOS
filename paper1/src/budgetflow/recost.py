"""Offline recost / sensitivity tool for T3/T2 price ratio experiments.

Recalculates Yield, Yield/$, and strategy rankings from any completed
JSONL under different T3/T2 price multipliers.  Only cost fields are
changed; outcomes (resolved, patch, verdict) are never modified.

Usage (no-paid, pure analysis)::

    python -m budgetflow.recost data/runs/mainline_5x20_tight_v1-0.jsonl

This is a standalone module — it does not require provider access or
a paid experiment budget.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

# Reference token prices (per-token, not per-1M) from normalized experiment units.
# These are routing/cost-sensitivity units, not provider billing rates.
_REF_T2_INPUT = 0.90 / 1_000_000
_REF_T2_OUTPUT = 4.50 / 1_000_000
_REF_T3_INPUT = 4.50 / 1_000_000
_REF_T3_OUTPUT = 22.50 / 1_000_000
_T2_INPUT_KV_CACHE_DISCOUNT = 0.50

# Default T3/T2 ratios to test (diagnostic sweep).
DEFAULT_RATIOS = (1.5, 2.0, 3.0, 5.0, 10.0)


def recost_record(record: dict, *, t3_multiplier: float) -> dict:
    """Return a copy of *record* with costs recalculated for *t3_multiplier*.

    The multiplier is applied to T3 turns only.  T1 and T2 turn costs are
    recomputed from reference prices but not multiplied.

    Only modifies: ``total_cost``, ``batch_spent``, ``budget_spent``.
    Does NOT modify: ``harness_resolved``, ``score_status``, ``verdict_axis``,
    ``patch_extracted``, ``backend_picks``.
    """
    import copy
    rec = copy.deepcopy(record)

    backend_picks = rec.get("backend_picks") or []
    prompt_tokens = int(rec.get("prompt_tokens_total") or 0)
    completion_tokens = int(rec.get("completion_tokens_total") or 0)
    llm_turns = int(rec.get("llm_turns") or len(backend_picks))

    if llm_turns <= 0:
        return rec

    # Estimate per-turn token counts
    input_per_turn = prompt_tokens / llm_turns if llm_turns > 0 else 0
    output_per_turn = completion_tokens / llm_turns if llm_turns > 0 else 0

    # Count T3 turns
    t3_turns = sum(1 for p in backend_picks if str(p) in ("tier3", "3"))

    new_cost = 0.0
    for turn_index, pick in enumerate(backend_picks, start=1):
        tier = str(pick)
        if tier in ("tier3", "3"):
            new_cost += input_per_turn * _REF_T3_INPUT * t3_multiplier
            new_cost += output_per_turn * _REF_T3_OUTPUT * t3_multiplier
        elif tier in ("tier2", "2"):
            input_fraction = 1.0 if turn_index <= 1 else 1.0 - _T2_INPUT_KV_CACHE_DISCOUNT
            new_cost += input_per_turn * _REF_T2_INPUT * input_fraction
            new_cost += output_per_turn * _REF_T2_OUTPUT
        else:
            # T1: use reference T1 prices
            new_cost += input_per_turn * 0.30 / 1_000_000
            new_cost += output_per_turn * 1.50 / 1_000_000

    rec["total_cost"] = round(new_cost, 6)
    rec["budget_spent"] = round(new_cost, 6)

    # Update batch_spent if present
    if "batch_spent" in rec:
        rec["batch_spent"] = round(new_cost, 6)

    # Tag the recost metadata
    rec["recost_t3_multiplier"] = t3_multiplier
    rec["recost_t3_turns"] = t3_turns
    rec["recost_input_kv_cache_discount"] = _T2_INPUT_KV_CACHE_DISCOUNT

    return rec


def run_sensitivity(
    jsonl_path: Path,
    *,
    ratios: tuple[float, ...] = DEFAULT_RATIOS,
    output_path: Path | None = None,
) -> dict:
    """Recost a JSONL under multiple T3/T2 price ratios.

    Returns a dict mapping ratio → strategy-level summary:
    {ratio: {strategy: {pass, total_cost, yield, yield_per_dollar, ...}}}
    """
    # Load and dedup records: keep the last row for each task/strategy.
    latest_records: dict[tuple[str, str], tuple[float, int, dict]] = {}
    with jsonl_path.open() as f:
        for order, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            strategy = rec.get("strategy", "")
            instance_id = rec.get("instance_id", "")
            if not strategy or not instance_id:
                continue
            key = (strategy, instance_id)
            finished_at = float(rec.get("row_finished_at", 0) or 0)
            if key not in latest_records or (finished_at, order) >= (
                latest_records[key][0],
                latest_records[key][1],
            ):
                latest_records[key] = (finished_at, order, rec)
    records = [item[2] for item in latest_records.values()]

    results: dict[str, dict] = {}
    for ratio in ratios:
        ratio_key = f"{ratio:.1f}x"
        by_strategy: dict[str, dict] = defaultdict(
            lambda: {"pass": 0, "total": 0, "total_cost": 0.0, "total_value": 0.0}
        )

        for rec in records:
            r = recost_record(rec, t3_multiplier=ratio)
            strategy = r.get("strategy", "")
            if not strategy:
                continue
            score_status = str(r.get("score_status") or "")
            task_value = float(r.get("task_value") or 1.0)

            by_strategy[strategy]["total"] += 1
            by_strategy[strategy]["total_cost"] += float(r.get("total_cost") or 0)
            by_strategy[strategy]["total_value"] += task_value

            if score_status == "pass":
                by_strategy[strategy]["pass"] += 1
                by_strategy[strategy]["resolved_value"] = (
                    by_strategy[strategy].get("resolved_value", 0.0) + task_value
                )

        # Compute derived metrics
        summary: dict[str, dict] = {}
        for strat, stats in by_strategy.items():
            cost = stats["total_cost"]
            resolved_value = stats.get("resolved_value", 0.0)
            summary[strat] = {
                "pass": stats["pass"],
                "total": stats["total"],
                "total_cost": round(cost, 4),
                "total_value": round(stats["total_value"], 4),
                "resolved_value": round(resolved_value, 4),
                "yield": round(resolved_value, 4),
                "yield_per_dollar": round(resolved_value / cost, 4) if cost > 0 else 0.0,
                "pass_rate": round(stats["pass"] / stats["total"], 4) if stats["total"] > 0 else 0.0,
            }

        results[ratio_key] = summary

    report = {
        "source": str(jsonl_path),
        "ratios_tested": [f"{r:.1f}x" for r in ratios],
        "note": "Only cost fields recalculated. Outcomes, verdicts, and patches are unchanged.",
        "results": results,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Sensitivity report written to {output_path}")

    return report


def rank_strategies(sensitivity_report: dict, metric: str = "yield_per_dollar") -> dict:
    """Rank strategies within each ratio by *metric*."""
    rankings: dict[str, list[tuple[str, float]]] = {}
    for ratio_key, strategies in sensitivity_report["results"].items():
        scored = [
            (strat, stats.get(metric, 0.0))
            for strat, stats in strategies.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        rankings[ratio_key] = scored
    return rankings


# ── CLI entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: python -m budgetflow.recost <jsonl_path> [output_path]")
        print(f"  Recosts JSONL under T3/T2 ratios: {', '.join(f'{r:.1f}x' for r in DEFAULT_RATIOS)}")
        sys.exit(1)

    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    if not src.exists():
        print(f"Error: {src} not found")
        sys.exit(1)

    report = run_sensitivity(src, output_path=out)
    rankings = rank_strategies(report)

    print(f"Recost sensitivity for {src}")
    print(f"Ratios: {', '.join(report['ratios_tested'])}")
    print()
    for ratio_key in report["ratios_tested"]:
        print(f"--- {ratio_key} ---")
        for strat, stats in sorted(report["results"][ratio_key].items()):
            print(
                f"  {strat:40s} pass={stats['pass']}/{stats['total']} "
                f"cost=${stats['total_cost']:.4f} "
                f"yield={stats['yield']:.4f} "
                f"yield/$={stats['yield_per_dollar']:.4f}"
            )
        print(f"  Ranking by yield/$: {', '.join(f'{s}({v:.2f})' for s, v in rankings[ratio_key])}")
        print()

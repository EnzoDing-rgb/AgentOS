"""Offline recost / sensitivity tool for model-cost experiments.

Recalculates Yield, Yield/$, and strategy rankings from any completed
JSONL under different T3/T2 price multipliers and optional multi-turn
input-cache discounts.  Only cost fields are changed; outcomes (resolved,
patch, verdict) are never modified.

Usage (no-paid, pure analysis)::

    python -m budgetflow.recost data/runs/mainline_5x20_tight_v1-0.jsonl
    python -m budgetflow.recost data/runs/mainline_5x20_tight_v1-0.jsonl --kv-discount 0.25

This is a standalone module — it does not require provider access or
a paid experiment budget.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .model_tiers import MODEL_CATALOG, TurnCachePolicy, token_cost_rates

# Default target T3/T2 price ratios to test (diagnostic sweep).
DEFAULT_RATIOS = (1.5, 2.0, 3.0, 5.0, 10.0)


def recost_record(
    record: dict,
    *,
    t3_target_ratio: float,
    input_kv_cache_discount: float | None = None,
    input_discount_after_turn: int = 1,
    min_input_cost_fraction: float = 0.0,
) -> dict:
    """Return a copy of *record* with costs recalculated for a target T3/T2 ratio.

    T1 and T2 turn costs are recomputed from catalog prices. T3 turn costs
    are derived from T2 prices multiplied by ``t3_target_ratio`` so a 5.0
    sensitivity means "T3 is 5x T2", not "multiply the catalog T3 by 5
    again". When ``input_kv_cache_discount`` is set, it is applied as an
    explicit sensitivity policy to repeated input tokens for T2 and T3 turns.

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

    # Count T3 turns
    t3_turns = sum(1 for p in backend_picks if str(p) in ("tier3", "3"))
    sensitivity_cache_policy = (
        TurnCachePolicy(
            input_discount_after_turn=input_discount_after_turn,
            input_kv_cache_discount=input_kv_cache_discount,
            min_input_cost_fraction=min_input_cost_fraction,
        )
        if input_kv_cache_discount is not None
        else None
    )
    turn_inputs = _turn_inputs(rec, backend_picks, prompt_tokens, completion_tokens, llm_turns)
    tier_turn_counts: dict[str, int] = defaultdict(int)

    new_cost = 0.0
    for turn in turn_inputs:
        backend = _canonical_backend(turn["backend"])
        tier_turn_counts[backend] += 1
        input_tokens = int(turn["input_tokens"])
        output_tokens = int(turn["output_tokens"])
        if backend == "tier3":
            input_rate, output_rate = _target_t3_rates(input_tokens, t3_target_ratio)
        else:
            input_rate, output_rate = token_cost_rates(
                backend,
                input_tokens,
                turn_index=tier_turn_counts[backend],
            )
        if sensitivity_cache_policy is not None and backend in {"tier2", "tier3"}:
            cfg = MODEL_CATALOG.require_config("tier2" if backend == "tier3" else backend)
            base_input_rate = _base_input_rate(cfg, input_tokens)
            if backend == "tier3":
                base_input_rate *= t3_target_ratio
            input_rate = base_input_rate * sensitivity_cache_policy.input_cost_fraction(
                tier_turn_counts[backend]
            )
        new_cost += input_tokens * input_rate
        new_cost += output_tokens * output_rate

    rec["total_cost"] = round(new_cost, 6)
    rec["budget_spent"] = round(new_cost, 6)

    # Update batch_spent if present
    if "batch_spent" in rec:
        rec["batch_spent"] = round(new_cost, 6)

    # Tag the recost metadata
    rec["recost_t3_target_ratio"] = t3_target_ratio
    rec["recost_t3_turns"] = t3_turns
    rec["recost_input_kv_cache_discount"] = round(
        float(
            input_kv_cache_discount
            if input_kv_cache_discount is not None
            else MODEL_CATALOG.require_config("tier2").turn_cache_policy.input_kv_cache_discount
        ),
        6,
    )
    rec["recost_kv_discount_applies_to"] = (
        ["tier2", "tier3"] if input_kv_cache_discount is not None else []
    )

    return rec


def _turn_inputs(
    record: dict,
    backend_picks: list,
    prompt_tokens: int,
    completion_tokens: int,
    llm_turns: int,
) -> list[dict[str, int | str]]:
    traces = record.get("turn_traces") or []
    turns: list[dict[str, int | str]] = []
    for index, pick in enumerate(backend_picks):
        trace = traces[index] if index < len(traces) and isinstance(traces[index], dict) else {}
        backend = (
            trace.get("final_backend")
            or trace.get("backend_chosen")
            or trace.get("backend")
            or pick
        )
        turns.append({
            "backend": _canonical_backend(backend),
            "input_tokens": int(trace.get("prompt_tokens") or trace.get("input_tokens") or 0),
            "output_tokens": int(trace.get("completion_tokens") or trace.get("output_tokens") or 0),
        })
    if any(int(turn["input_tokens"]) or int(turn["output_tokens"]) for turn in turns):
        return turns

    input_per_turn = prompt_tokens / llm_turns if llm_turns > 0 else 0
    output_per_turn = completion_tokens / llm_turns if llm_turns > 0 else 0
    return [
        {
            "backend": _canonical_backend(pick),
            "input_tokens": int(input_per_turn),
            "output_tokens": int(output_per_turn),
        }
        for pick in backend_picks
    ]


def _canonical_backend(value: Any) -> str:
    tier = str(value)
    if tier in {"tier3", "3"}:
        return "tier3"
    if tier in {"tier2", "2"}:
        return "tier2"
    return "tier1"


def _base_input_rate(config: Any, input_tokens: int) -> float:
    for band in config.token_cost_bands:
        if band.max_input_tokens is None or input_tokens <= band.max_input_tokens:
            return band.input_per_1m / 1_000_000
    if config.token_cost_bands:
        return config.token_cost_bands[-1].input_per_1m / 1_000_000
    return config.cost_per_input_token


def _target_t3_rates(input_tokens: int, t3_target_ratio: float) -> tuple[float, float]:
    """Return T3 rates as a target multiple of current T2 rates."""
    t2_cfg = MODEL_CATALOG.require_config("tier2")
    input_rate = _base_input_rate(t2_cfg, input_tokens) * t3_target_ratio
    output_rate = t2_cfg.cost_per_output_token * t3_target_ratio
    return input_rate, output_rate


def run_sensitivity(
    jsonl_path: Path,
    *,
    ratios: tuple[float, ...] = DEFAULT_RATIOS,
    input_kv_cache_discount: float | None = None,
    input_discount_after_turn: int = 1,
    min_input_cost_fraction: float = 0.0,
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
            r = recost_record(
                rec,
                t3_target_ratio=ratio,
                input_kv_cache_discount=input_kv_cache_discount,
                input_discount_after_turn=input_discount_after_turn,
                min_input_cost_fraction=min_input_cost_fraction,
            )
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
        "input_kv_cache_discount": input_kv_cache_discount,
        "input_discount_after_turn": input_discount_after_turn,
        "min_input_cost_fraction": min_input_cost_fraction,
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
    import argparse

    parser = argparse.ArgumentParser(description="Offline BudgetFlow cost sensitivity.")
    parser.add_argument("jsonl_path", type=Path)
    parser.add_argument("output_path", type=Path, nargs="?")
    parser.add_argument(
        "--ratios",
        type=str,
        default=",".join(f"{ratio:.1f}" for ratio in DEFAULT_RATIOS),
        help="comma-separated T3 multipliers",
    )
    parser.add_argument(
        "--kv-discount",
        type=float,
        default=None,
        help="optional input-token KV-cache discount for T2/T3 turns after the first turn",
    )
    parser.add_argument(
        "--kv-after-turn",
        type=int,
        default=1,
        help="first turn after which --kv-discount applies within each tier",
    )
    parser.add_argument(
        "--kv-min-input-fraction",
        type=float,
        default=0.0,
        help="minimum charged input-token fraction when --kv-discount is set",
    )
    args = parser.parse_args()

    src = args.jsonl_path
    out = args.output_path
    if not src.exists():
        print(f"Error: {src} not found")
        raise SystemExit(1)
    ratios = tuple(float(part) for part in args.ratios.split(",") if part.strip())

    report = run_sensitivity(
        src,
        ratios=ratios,
        input_kv_cache_discount=args.kv_discount,
        input_discount_after_turn=args.kv_after_turn,
        min_input_cost_fraction=args.kv_min_input_fraction,
        output_path=out,
    )
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

"""Historical data ETL for Automatic Budgeting.

Reads old compare JSONL files, filters clean rows, normalizes tier mappings,
and writes task_cost_history.jsonl + a summary report.

Usage:
  cd paper1 && PYTHONPATH=src python -m budgetflow.historical_etl
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PAPER1_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PAPER1_ROOT / "data" / "runs"
DATA_DIR = PAPER1_ROOT / "data"
REPORTS_DIR = PAPER1_ROOT / "docs" / "reports"

OUTPUT_JSONL = DATA_DIR / "task_cost_history.jsonl"
OUTPUT_REPORT = REPORTS_DIR / "historical_budgeting_prior.md"

SOURCE_FILES = [
    RUNS_DIR / "policy_5x7-0.jsonl",
    RUNS_DIR / "budgetflow_goldpass5_qwen5pol_v2.jsonl",
]

# Map old backend name prefixes to normalized tiers.
# Old names: tier1_codex_spark, tier2_gpt54_mini, tier3_gpt53_codex
# New names: tier1, tier2, tier3
_TIER_NORMALIZE: dict[str, int] = {
    "tier1": 1, "tier2": 2, "tier3": 3,
}

# Rows to exclude by exit reason / status.
_EXCLUDE_REASONS = frozenset({
    "BadRequestError", "infra_error", "provider_all_unavailable",
    "billing_guard", "upstream_guard",
})
_EXCLUDE_STATUSES = frozenset({
    "BadRequestError", "APIError", "RateLimitError",
    "AuthenticationError", "ServiceUnavailableError",
    "UpstreamExit", "infra_error",
})


def _tier_from_backend_name(name: str) -> int | None:
    """Extract tier number from backend name like 'tier3_gpt53_codex' or 'tier3'."""
    for prefix, tier in _TIER_NORMALIZE.items():
        if name.startswith(prefix):
            return tier
    return None


def _normalize_tier_mix(picks: list[str]) -> dict[int, int]:
    """Count picks by normalized tier."""
    mix: dict[int, int] = {}
    for p in picks:
        t = _tier_from_backend_name(p)
        if t is not None:
            mix[t] = mix.get(t, 0) + 1
    return mix


def _classify_confidence(record: dict) -> tuple[str, str | None]:
    """Return (confidence, exclusion_reason)."""
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")

    if status in _EXCLUDE_STATUSES:
        return "exclude", f"infra_status:{status}"
    if reason in _EXCLUDE_REASONS:
        return "exclude", f"infra_reason:{reason}"
    if "format_error" in reason.lower() or "format" in status.lower():
        return "exclude", "parser_protocol_failure"
    if not record.get("patch_extracted") and not record.get("harness_resolved"):
        # No patch extracted, not resolved — likely parser/model failure
        if record.get("llm_turns", 0) <= 5:
            return "exclude", "too_few_turns_no_patch"

    picks = record.get("backend_picks") or []
    tiers = {_tier_from_backend_name(p) for p in picks}
    if None in tiers:
        return "exclude", "unknown_tier_mapping"

    # Clean enough to use as task prior
    if record.get("harness_resolved"):
        return "clean", None
    if record.get("patch_extracted") and record.get("agent_gold_edited"):
        return "usable_task_prior", None
    if record.get("patch_extracted"):
        return "usable_task_prior", None

    return "usable_task_prior", None


def _etl_row(record: dict, run_id: str) -> dict | None:
    """Transform one record into a standardized history row, or None if excluded."""
    confidence, exclusion = _classify_confidence(record)
    if confidence == "exclude":
        return None

    picks = record.get("backend_picks") or []
    tier_mix = _normalize_tier_mix(picks)
    dominant_tier = max(tier_mix, key=tier_mix.get) if tier_mix else None

    return {
        "instance_id": record["instance_id"],
        "run_id": run_id,
        "strategy": record.get("strategy", ""),
        "normalized_tier_mix": tier_mix,
        "dominant_tier": dominant_tier,
        "resolved": bool(record.get("harness_resolved")),
        "total_cost": float(record.get("total_cost") or record.get("task_cost") or 0),
        "turns": int(record.get("llm_turns") or 0),
        "failure_class": record.get("failure_class") or classify_failure(record),
        "exit_reason": record.get("exit_reason"),
        "patch_extracted": bool(record.get("patch_extracted")),
        "gold_edited": bool(record.get("agent_gold_edited")),
        "confidence": confidence,
        "exclusion_reason": exclusion,
    }


def classify_failure(record: dict) -> str:
    """Inline failure classification (avoids circular import)."""
    if record.get("harness_resolved"):
        return "pass"
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    if "budget" in status.lower() or "budget" in reason.lower():
        return "budget_fail"
    if "error" in status.lower():
        return "infra_fail"
    if not record.get("patch_extracted"):
        return "extract_fail"
    if not record.get("agent_gold_edited"):
        return "loc_fail"
    return "repair_fail"


def _build_report(rows: list[dict]) -> str:
    """Generate historical_budgeting_prior.md."""
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["instance_id"], []).append(r)

    lines = [
        "# Historical Budgeting Prior",
        "",
        f"Generated from {len(SOURCE_FILES)} source files, {len(rows)} clean rows.",
        "",
        "## Per-Task Summary",
        "",
        "| instance_id | records | resolved | median_cost | median_turns | dominant_tier | difficulty |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    task_summaries = []
    for instance_id, recs in sorted(by_task.items()):
        n = len(recs)
        resolved_n = sum(1 for r in recs if r["resolved"])
        costs = [r["total_cost"] for r in recs]
        turns = [r["turns"] for r in recs]
        import statistics
        median_cost = statistics.median(costs) if costs else 0
        median_turns = int(statistics.median(turns)) if turns else 0
        dominant_tiers = Counter(r["dominant_tier"] for r in recs)
        dom_tier = dominant_tiers.most_common(1)[0][0] if dominant_tiers else "-"
        # Difficulty relative to sympy__sympy-20212 anchor
        difficulty = "TBD"

        lines.append(
            f"| {instance_id} | {n} | {resolved_n}/{n} | {median_cost:.1f} | {median_turns} | T{dom_tier} | {difficulty} |"
        )
        task_summaries.append((instance_id, resolved_n, n, median_cost, median_turns, dom_tier))

    # Compute difficulty coefficients from known anchor (sympy__sympy-20212 = 1.0x)
    anchor_cost = None
    for tid, _, _, mcost, _, _ in task_summaries:
        if "20212" in tid:
            anchor_cost = mcost
            break

    lines.append("")
    lines.append("## Difficulty Coefficients")
    lines.append("")
    if anchor_cost and anchor_cost > 0:
        lines.append(f"Anchor: sympy__sympy-20212 = 1.0x (median_cost={anchor_cost:.1f})")
        lines.append("")
        lines.append("| task | difficulty | median_cost |")
        lines.append("|---|---:|---:|")
        for tid, _, _, mcost, _, _ in task_summaries:
            coef = mcost / anchor_cost if anchor_cost > 0 else 0
            lines.append(f"| {tid} | {coef:.2f}x | {mcost:.1f} |")

    lines.append("")
    lines.append("## Confidence Distribution")
    conf_dist = Counter(r["confidence"] for r in rows)
    for k, v in sorted(conf_dist.items()):
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Failure Class Distribution")
    fail_dist = Counter(r["failure_class"] for r in rows)
    for k, v in sorted(fail_dist.items()):
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Soft-Cap Recommendations")
    lines.append("")
    lines.append("Per-task soft cap from historical median successful cost:")
    lines.append("")
    for tid, resolved_n, _, mcost, mturns, dom_tier in sorted(task_summaries):
        # Get successful costs only
        succ_costs = [r["total_cost"] for r in by_task[tid] if r["resolved"]]
        if succ_costs:
            import statistics
            median_success = statistics.median(succ_costs)
            lines.append(
                f"- **{tid}**: soft_cap={median_success:.1f} (median success), "
                f"all_median={mcost:.1f}, resolved={resolved_n}/{len(by_task[tid])}, "
                f"typical_tier=T{dom_tier}"
            )
        else:
            lines.append(
                f"- **{tid}**: no successful records, all_median={mcost:.1f}, "
                f"typical_tier=T{dom_tier} — use pilot/feature estimate"
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    all_rows: list[dict] = []
    excluded = 0

    for src_path in SOURCE_FILES:
        if not src_path.is_file():
            print(f"[etl] skip missing: {src_path}")
            continue

        run_id = src_path.stem
        print(f"[etl] reading {src_path} ({run_id})")
        for line in src_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            row = _etl_row(record, run_id)
            if row is None:
                excluded += 1
                continue
            all_rows.append(row)

    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSONL.open("w") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[etl] wrote {len(all_rows)} rows to {OUTPUT_JSONL} ({excluded} excluded)")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = _build_report(all_rows)
    OUTPUT_REPORT.write_text(report)
    print(f"[etl] wrote report to {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()

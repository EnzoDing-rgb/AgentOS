"""Value Matrix and Progress Calibration — offline, defensible foundation.

Value Matrix:
  Generates a multi-profile value assignment for each task in the clean JSONL
  universe. No BF-specific signals. All profiles are ex-ante or cross-strategy.

Progress Calibration:
  Read-only (stage, tier) progress summary from existing turn_traces.
  Reports observed progress rates with selection-bias caveats.

Usage:
  PYTHONPATH=src python3 -m budgetflow.value_matrix \
    --data-dir data/runs \
    --output docs/reports/045_value_matrix.json

  PYTHONPATH=src python3 -m budgetflow.value_matrix \
    --data-dir data/runs \
    --output - \
    --progress-table
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ═══════════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TaskRecord:
    instance_id: str
    repo: str
    total_rows: int = 0
    resolved_rows: int = 0
    total_cost: float = 0.0
    strategies_seen: set[str] = field(default_factory=set)
    strategies_resolved: set[str] = field(default_factory=set)

    @property
    def resolve_rate(self) -> float:
        return self.resolved_rows / self.total_rows if self.total_rows > 0 else 0.0

    @property
    def avg_cost(self) -> float:
        return self.total_cost / self.total_rows if self.total_rows > 0 else 0.0

    @property
    def solve_rarity(self) -> float:
        """Fraction of strategies that solved this task. 0 = unsolved, 1 = all solved."""
        n = len(self.strategies_seen)
        return len(self.strategies_resolved) / n if n > 0 else 0.0

    @property
    def repo_name(self) -> str:
        return self.instance_id.split("__")[0] if "__" in self.instance_id else "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Value profiles
# ═══════════════════════════════════════════════════════════════════════════════

# Each profile is a Callable[[str, TaskRecord], float].
# The function signature is (instance_id, TaskRecord) so custom profiles
# can use cross-strategy stats or ignore them.

ValueFn = Callable[[str, TaskRecord], float]


def profile_equal(_iid: str, _rec: TaskRecord) -> float:
    """Equal value: every task counts 1.0."""
    return 1.0


def profile_difficulty(rec: TaskRecord) -> float:
    """Difficulty proxy: value ∝ avg_cost × (1 + failure_penalty).

    Rationale: tasks that consume more budget across ALL strategies and are
    harder to solve are more likely to contain deep bugs worth fixing.
    Cross-strategy stats avoid BF-specific tuning.

    Failure penalty: unresolved tasks get a 1.5× multiplier on the cost
    component to reflect that difficult-to-solve tasks are more valuable
    to solve correctly.

    This is an ex-ante proxy — it uses only historical stats that exist
    before any single strategy is evaluated.
    """
    base = rec.avg_cost
    if rec.resolve_rate < 1.0:
        base *= (1.0 + 0.5 * (1.0 - rec.resolve_rate))
    # Floor at 0.01 to avoid zero-value tasks
    return max(base, 0.01)


def profile_solve_rarity(rec: TaskRecord) -> float:
    """Solve-rarity proxy: fewer strategies can solve → higher value.

    Rationale: a task that only one strategy can solve is a discriminating
    signal — it separates good routers from bad ones. Tasks that everyone
    or no-one solves are less informative.

    Formula: value = 1.0 + 4.0 × (1.0 - solve_rarity)²
    - Everyone solves (rarity=1.0): value = 1.0
    - No one solves (rarity=0.0): value = 5.0  (hard but potentially valuable if solved)
    - Half solve (rarity=0.5): value = 2.0

    Note: 0-solved tasks are capped at 5.0 — they could be impossible rather
    than valuable. The quadratic form means moderate rarity (0.2-0.5) gets
    meaningful weight without over-weighting impossible tasks.
    """
    rarity = rec.solve_rarity
    # Quadratic: rarity=0 → 5.0, rarity=0.5 → 2.0, rarity=1.0 → 1.0
    return 1.0 + 4.0 * (1.0 - rarity) ** 2


def profile_combined(rec: TaskRecord) -> float:
    """Combined difficulty + rarity proxy (equal weight, log-scaled).

    Uses log1p to compress extreme difficulty values while preserving ordering.
    """
    diff = profile_difficulty(rec)
    rarity = profile_solve_rarity(rec)
    import math
    return round(math.log1p(diff) + rarity, 4)


def make_custom_profile(mapping: dict[str, float]) -> ValueFn:
    """Build a profile from an explicit instance_id → value mapping."""
    return lambda iid, _rec: mapping.get(iid, 1.0)


# Registry: name → (factory or direct function)
# For profiles that need TaskRecord, we wrap them.
def _wrap_record(fn: Callable[[TaskRecord], float]) -> ValueFn:
    return lambda _iid, rec: fn(rec)


PROFILES: dict[str, ValueFn] = {
    "equal": profile_equal,
    "difficulty": _wrap_record(profile_difficulty),
    "solve_rarity": _wrap_record(profile_solve_rarity),
    "combined": _wrap_record(profile_combined),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Robustness sensitivity
# ═══════════════════════════════════════════════════════════════════════════════


def sensitivity_variants(rec: TaskRecord) -> dict[str, float]:
    """Generate sensitivity variants of the difficulty profile.

    Returns a dict of profile_name → value for sensitivity analysis.
    The goal: show that conclusions don't hinge on a single magic number.
    """
    base_cost = rec.avg_cost
    base_rate = rec.resolve_rate
    # Three variants:
    # - cost_only: value = avg_cost (ignore solve rate)
    # - rate_only: value = 2.0 - resolve_rate (inverted: hard=high)
    # - cost_heavy: value = avg_cost * (2 - resolve_rate)
    # - rate_heavy: value = (1 + avg_cost) * (2 - resolve_rate)
    # - original: as per profile_difficulty
    return {
        "cost_only": max(base_cost, 0.01),
        "rate_only": max(2.0 - base_rate, 0.01),
        "cost_heavy": max(base_cost * (2.0 - base_rate), 0.01),
        "rate_heavy": max((1.0 + base_cost) * (2.0 - base_rate), 0.01),
        "difficulty_default": profile_difficulty(rec),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Core: build value matrix from JSONL
# ═══════════════════════════════════════════════════════════════════════════════


def scan_task_universe(data_dir: str | Path) -> dict[str, TaskRecord]:
    """Scan all clean JSONL files and build TaskRecord for each unique task."""
    data_dir = Path(data_dir)
    records: dict[str, TaskRecord] = {}

    jsonl_files = sorted(data_dir.glob("*.jsonl"))
    for fp in jsonl_files:
        # Skip non-experiment files
        if fp.name.startswith("auto_budget"):
            continue
        try:
            with open(fp) as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (json.JSONDecodeError, OSError):
            continue

        for r in rows:
            iid = r.get("instance_id", "")
            if not iid:
                continue
            if iid not in records:
                records[iid] = TaskRecord(instance_id=iid, repo=r.get("repo", ""))
            rec = records[iid]
            rec.total_rows += 1
            if r.get("harness_resolved"):
                rec.resolved_rows += 1
                rec.strategies_resolved.add(r.get("strategy", "?"))
            rec.total_cost += r.get("total_cost", r.get("task_cost", 0.0)) or 0.0
            rec.strategies_seen.add(r.get("strategy", "?"))

    return records


def build_value_matrix(
    records: dict[str, TaskRecord],
    profiles: dict[str, ValueFn] | None = None,
) -> dict[str, Any]:
    """Build a value matrix with all profiles and sensitivity analysis."""
    if profiles is None:
        profiles = PROFILES

    matrix: dict[str, Any] = {
        "meta": {
            "task_count": len(records),
            "profiles": list(profiles.keys()),
            "note": "All profiles are ex-ante or cross-strategy. No BF-specific signals.",
        },
        "tasks": {},
    }

    for iid in sorted(records.keys()):
        rec = records[iid]
        task_entry: dict[str, Any] = {
            "instance_id": iid,
            "repo": rec.repo_name,
            "total_rows": rec.total_rows,
            "resolved_rows": rec.resolved_rows,
            "resolve_rate": round(rec.resolve_rate, 4),
            "avg_cost": round(rec.avg_cost, 6),
            "solve_rarity": round(rec.solve_rarity, 4),
            "strategies_seen": sorted(rec.strategies_seen),
            "strategies_resolved": sorted(rec.strategies_resolved),
            "values": {},
            "sensitivity": {},
        }

        for pname, pfn in profiles.items():
            task_entry["values"][pname] = round(pfn(iid, rec), 4)

        task_entry["sensitivity"] = {
            k: round(v, 4) for k, v in sensitivity_variants(rec).items()
        }

        matrix["tasks"][iid] = task_entry

    # Add per-profile rankings
    matrix["rankings"] = {}
    for pname in profiles.keys():
        ranked = sorted(
            matrix["tasks"].items(),
            key=lambda kv: kv[1]["values"][pname],
            reverse=True,
        )
        matrix["rankings"][pname] = [
            {"rank": i + 1, "instance_id": iid, "value": entry["values"][pname]}
            for i, (iid, entry) in enumerate(ranked)
        ]

    # Add rank correlation between profiles
    matrix["rank_correlations"] = _rank_correlations(matrix["rankings"])

    return matrix


def _rank_correlations(rankings: dict[str, list]) -> dict[str, dict[str, float]]:
    """Spearman-like rank correlation between profiles."""
    profile_names = list(rankings.keys())
    result: dict[str, dict[str, float]] = {}
    for p1 in profile_names:
        result[p1] = {}
        ids1 = [r["instance_id"] for r in rankings[p1]]
        for p2 in profile_names:
            if p1 == p2:
                result[p1][p2] = 1.0
                continue
            ids2 = [r["instance_id"] for r in rankings[p2]]
            # Spearman footrule: 1 - 6*sum(d^2)/(n*(n^2-1))
            n = len(ids1)
            d2_sum = sum(
                (ids1.index(iid) - ids2.index(iid)) ** 2 for iid in ids1
            )
            rho = 1.0 - (6.0 * d2_sum) / (n * (n * n - 1)) if n > 1 else 1.0
            result[p1][p2] = round(rho, 4)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Progress calibration from turn traces
# ═══════════════════════════════════════════════════════════════════════════════


def calibrate_progress_table(data_dir: str | Path) -> dict[str, Any]:
    """Read-only calibration of (stage, tier) progress from existing traces."""
    data_dir = Path(data_dir)
    jsonl_files = sorted(data_dir.glob("*.jsonl"))

    # Raw aggregation
    stage_tier: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"turns": 0, "progress_turns": 0, "costs": [], "strategies": set()}
    )

    for fp in jsonl_files:
        if fp.name.startswith("auto_budget"):
            continue
        try:
            with open(fp) as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (json.JSONDecodeError, OSError):
            continue

        for r in rows:
            traces = r.get("turn_traces", [])
            for t in traces:
                stage = str(t.get("stage", "?"))
                tier = str(t.get("backend_tier", "?"))
                has_progress = bool(t.get("has_progress", False))
                cost = t.get("billable_cost", t.get("actual_cost", 0))
                if cost is None:
                    cost = 0.0

                key = (stage, tier)
                st = stage_tier[key]
                st["turns"] += 1
                if has_progress:
                    st["progress_turns"] += 1
                st["costs"].append(float(cost))
                st["strategies"].add(r.get("strategy", "?"))

    result: dict[str, Any] = {
        "meta": {
            "note": "Selection-bias caveat: T3 turns happen when the agent is stuck or under pressure. "
            "Raw T3 progress rate may be lower than T2 even if T3 is better, because T3 faces harder turns. "
            "Use these rates for calibration direction, not as unbiased effect estimates.",
            "total_turns": sum(st["turns"] for st in stage_tier.values()),
            "total_progress_turns": sum(st["progress_turns"] for st in stage_tier.values()),
        },
        "stage_tier": {},
        "deltas": [],
    }

    for (stage, tier) in sorted(stage_tier.keys(), key=lambda x: (x[0], int(x[1]))):
        st = stage_tier[(stage, tier)]
        turns = st["turns"]
        progress = st["progress_turns"]
        rate = progress / turns if turns > 0 else 0.0
        sorted_costs = sorted(st["costs"])
        avg_cost = sum(st["costs"]) / len(st["costs"]) if st["costs"] else 0.0
        med_cost = sorted_costs[len(sorted_costs) // 2] if sorted_costs else 0.0
        p10_cost = sorted_costs[int(len(sorted_costs) * 0.1)] if len(sorted_costs) >= 10 else sorted_costs[0] if sorted_costs else 0.0
        p90_cost = sorted_costs[int(len(sorted_costs) * 0.9)] if len(sorted_costs) >= 10 else sorted_costs[-1] if sorted_costs else 0.0

        if turns >= 100:
            confidence = "HIGH"
        elif turns >= 30:
            confidence = "MEDIUM"
        elif turns >= 10:
            confidence = "LOW"
        else:
            confidence = "INSUFFICIENT"

        result["stage_tier"][f"{stage}_T{tier}"] = {
            "stage": stage,
            "tier": int(tier),
            "turns": turns,
            "progress_turns": progress,
            "progress_rate": round(rate, 4),
            "avg_cost": round(avg_cost, 6),
            "median_cost": round(med_cost, 6),
            "p10_cost": round(p10_cost, 6),
            "p90_cost": round(p90_cost, 6),
            "confidence": confidence,
            "strategies_seen": sorted(st["strategies"]),
        }

    # Tier upgrade deltas
    for stage in ["LOCALIZATION", "REPAIR", "VALIDATION"]:
        k2 = f"{stage}_T2"
        k3 = f"{stage}_T3"
        if k2 in result["stage_tier"] and k3 in result["stage_tier"]:
            s2 = result["stage_tier"][k2]
            s3 = result["stage_tier"][k3]
            if s2["turns"] >= 5 and s3["turns"] >= 5:
                delta_progress = s3["progress_rate"] - s2["progress_rate"]
                delta_cost = s3["avg_cost"] - s2["avg_cost"]
                result["deltas"].append({
                    "stage": stage,
                    "t2_rate": s2["progress_rate"],
                    "t3_rate": s3["progress_rate"],
                    "delta_progress": round(delta_progress, 4),
                    "delta_cost": round(delta_cost, 6),
                    "t2_turns": s2["turns"],
                    "t3_turns": s3["turns"],
                    "caveat": "Negative delta does NOT mean T3 is worse — T3 turns are selected on harder situations.",
                })

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Value Matrix and Progress Calibration — offline foundation"
    )
    p.add_argument("--data-dir", default="data/runs",
                   help="Directory containing JSONL run files")
    p.add_argument("--output", default="-",
                   help="Output path for value matrix JSON (default: stdout)")
    p.add_argument("--progress-table", action="store_true",
                   help="Also output progress calibration table")
    p.add_argument("--profile", choices=list(PROFILES.keys()) + ["all"],
                   default="all", help="Which profile to compute (default: all)")
    return p


def main(argv: list[str] | None = None) -> dict:
    args = _make_parser().parse_args(argv)

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    records = scan_task_universe(data_dir)
    if not records:
        print("ERROR: no task records found", file=sys.stderr)
        sys.exit(1)

    # Select profiles
    if args.profile == "all":
        profiles = PROFILES
    else:
        profiles = {args.profile: PROFILES[args.profile]}

    matrix = build_value_matrix(records, profiles)

    if args.progress_table:
        matrix["progress_calibration"] = calibrate_progress_table(data_dir)

    # Output
    output_text = json.dumps(matrix, indent=2, ensure_ascii=False)

    if args.output == "-":
        sys.stdout.write(output_text + "\n")
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text + "\n")
        print(f"Written to {out_path}", file=sys.stderr)

    return matrix


if __name__ == "__main__":
    main()

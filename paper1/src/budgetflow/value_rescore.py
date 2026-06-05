"""Value-aware offline rescore for existing BudgetFlow JSONL runs.

Usage:
  PYTHONPATH=src python3 -m budgetflow.value_rescore \
    --input data/runs/postfix_031_loo_5x2.jsonl \
    --profile equal

Profiles:
  - equal:    value_i = 1 for all tasks
  - heuristic: cold-start heuristic based on difficulty coefficients
  - custom:   provide a JSON file mapping instance_id → value

Only reads JSONL — does not modify source data.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ── Value profiles ────────────────────────────────────────────────────────────

# Difficulty coefficients from progress.md / historical data.
# Anchor: sympy__sympy-20212 = 1.00×
# These are cold-start estimates — not trained, not calibrated.
_DIFFICULTY_COEFF = {
    "sympy__sympy-14774": 0.15,
    "sympy__sympy-13480": 0.31,
    "sympy__sympy-13647": 0.82,
    "sympy__sympy-20212": 1.00,
    "sympy__sympy-16988": 6.58,
    "sympy__sympy-18057": 2.50,
    "sympy__sympy-18189": 2.00,
    "sympy__sympy-18621": 1.50,
    "sympy__sympy-17630": 1.80,
    "django__django-10924": 1.20,
    "django__django-12113": 2.80,
}


def _heuristic_value(instance_id: str) -> float:
    """Cold-start heuristic: map difficulty → value.

    Rationale (clearly labeled, not a North Star commitment):
      - Harder tasks proxy for higher business value: a deep sympy bug in core
        symbolic logic matters more than a trivial test fix.
      - Repo modifier: django tasks ×1.1 (web framework bugs affect more users).
      - Unknown tasks default to 1.0 (neutral, no information).

    This is a labeled cold-start example. The interface supports swapping in
    any Callable[[str], float].
    """
    base = _DIFFICULTY_COEFF.get(instance_id, 1.0)
    if instance_id.startswith("django__"):
        base *= 1.1
    return round(base, 4)


def equal_value(instance_id: str) -> float:
    """Equal-value profile: every task counts as 1.0."""
    return 1.0


def make_custom_profile(mapping: dict[str, float]) -> Callable[[str], float]:
    """Build a profile from an explicit instance_id → value mapping."""
    return lambda iid: mapping.get(iid, 1.0)


PROFILES: dict[str, Callable[[str], float]] = {
    "equal": equal_value,
    "heuristic": _heuristic_value,
}


# ── Data types ────────────────────────────────────────────────────────────────


@dataclass
class TaskRow:
    instance_id: str
    strategy: str
    harness_resolved: bool
    total_cost: float
    exit_reason: str
    llm_turns: int
    budget_tier: str
    backend_picks: list[str]
    raw: dict


@dataclass
class StrategyResult:
    strategy: str
    resolved_count: int = 0
    total_count: int = 0
    total_cost: float = 0.0
    resolved_value: float = 0.0
    total_value: float = 0.0
    budget_fail_count: int = 0
    value_weighted_budget_fail: float = 0.0
    per_task_rows: list[dict] = field(default_factory=list)

    @property
    def resolved_rate(self) -> float:
        return self.resolved_count / self.total_count if self.total_count > 0 else 0.0

    @property
    def cost_per_resolved(self) -> float:
        return self.total_cost / self.resolved_count if self.resolved_count > 0 else float("inf")

    @property
    def resolved_value_per_dollar(self) -> float:
        return self.resolved_value / self.total_cost if self.total_cost > 0 else 0.0


# ── Core rescore logic ────────────────────────────────────────────────────────


def load_rows(path: Path, value_fn: Callable[[str], float] | None = None) -> list[TaskRow]:
    """Load JSONL rows into TaskRow objects, handling missing/dirty fields."""
    rows = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                print(f"WARNING: line {lineno} is not valid JSON — skipping", file=sys.stderr)
                continue

            cost = r.get("total_cost", r.get("task_cost", 0.0))
            if cost is None:
                cost = 0.0

            resolved = r.get("harness_resolved", False)
            if resolved is None:
                resolved = False

            exit_reason = r.get("exit_reason") or "unknown"

            rows.append(TaskRow(
                instance_id=r.get("instance_id", f"unknown-{lineno}"),
                strategy=r.get("strategy", "unknown"),
                harness_resolved=bool(resolved),
                total_cost=float(cost),
                exit_reason=str(exit_reason),
                llm_turns=int(r.get("llm_turns", 0) or 0),
                budget_tier=str(r.get("budget_tier", "")),
                backend_picks=list(r.get("backend_picks", []) or []),
                raw=r,
            ))
    return rows


def compute_results(rows: list[TaskRow], value_fn: Callable[[str], float]) -> dict[str, StrategyResult]:
    """Aggregate rows by strategy, applying value_fn to each task."""
    results: dict[str, StrategyResult] = {}
    for row in rows:
        sid = row.strategy
        if sid not in results:
            results[sid] = StrategyResult(strategy=sid)

        sr = results[sid]
        value = value_fn(row.instance_id)
        is_budget_fail = "budget" in row.exit_reason.lower()

        sr.total_count += 1
        sr.total_cost += row.total_cost
        sr.total_value += value

        if row.harness_resolved:
            sr.resolved_count += 1
            sr.resolved_value += value
        else:
            if is_budget_fail:
                sr.value_weighted_budget_fail += value

        if is_budget_fail:
            sr.budget_fail_count += 1

        sr.per_task_rows.append({
            "instance_id": row.instance_id,
            "harness_resolved": row.harness_resolved,
            "total_cost": row.total_cost,
            "value": value,
            "exit_reason": row.exit_reason,
            "llm_turns": row.llm_turns,
        })

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────


def _fmt_usd(v: float) -> str:
    if v >= 10:
        return f"${v:.2f}"
    if v >= 1:
        return f"${v:.3f}"
    return f"${v:.4f}"


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Value-aware offline rescore for BudgetFlow JSONL")
    p.add_argument("--input", required=True, help="Path to JSONL run file")
    p.add_argument("--profile", choices=["equal", "heuristic", "custom"], default="equal",
                   help="Value profile (default: equal)")
    p.add_argument("--custom-map", type=Path, default=None,
                   help="JSON file mapping instance_id → value (required for --profile custom)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    return p


def main(argv: list[str] | None = None) -> dict:
    parser = _make_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"ERROR: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.profile == "custom":
        if not args.custom_map or not args.custom_map.is_file():
            print("ERROR: --profile custom requires --custom-map <file>", file=sys.stderr)
            sys.exit(1)
        mapping = json.loads(args.custom_map.read_text())
        value_fn = make_custom_profile(mapping)
    else:
        value_fn = PROFILES[args.profile]

    rows = load_rows(input_path)
    results = compute_results(rows, value_fn)

    if args.json:
        out = {}
        for sid, sr in results.items():
            out[sid] = {
                "strategy": sr.strategy,
                "total_count": sr.total_count,
                "resolved_count": sr.resolved_count,
                "resolved_rate": round(sr.resolved_rate, 4),
                "total_cost": round(sr.total_cost, 6),
                "cost_per_resolved": round(sr.cost_per_resolved, 6),
                "total_value": round(sr.total_value, 4),
                "resolved_value": round(sr.resolved_value, 4),
                "resolved_value_per_dollar": round(sr.resolved_value_per_dollar, 4),
                "value_weighted_budget_fail": round(sr.value_weighted_budget_fail, 4),
                "budget_fail_count": sr.budget_fail_count,
            }
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return out

    # Text table
    print(f"{'Strategy':<28s} {'N':>3s} {'Res':>3s} {'Rate':>6s} {'TotalCost':>10s} "
          f"{'Cost/Res':>10s} {'ResVal':>8s} {'Val/$':>8s} {'VwBF':>8s}")
    print("-" * 100)
    for sid in sorted(results.keys()):
        sr = results[sid]
        print(f"{sid:<28s} {sr.total_count:3d} {sr.resolved_count:3d} "
              f"{sr.resolved_rate:6.1%} {_fmt_usd(sr.total_cost):>10s} "
              f"{_fmt_usd(sr.cost_per_resolved):>10s} "
              f"{sr.resolved_value:8.2f} {sr.resolved_value_per_dollar:8.2f} "
              f"{sr.value_weighted_budget_fail:8.2f}")

    print()
    print("Per-task detail:")
    for sid in sorted(results.keys()):
        sr = results[sid]
        print(f"\n  {sid}:")
        for t in sorted(sr.per_task_rows, key=lambda x: x["instance_id"]):
            marker = "PASS" if t["harness_resolved"] else "FAIL"
            print(f"    {t['instance_id']:<32s} {marker:<5s} "
                  f"cost={_fmt_usd(t['total_cost']):>10s} value={t['value']:.2f} "
                  f"exit={t['exit_reason']:<25s} turns={t['llm_turns']:3d}")

    return {sid: sr for sid, sr in results.items()}


if __name__ == "__main__":
    main()

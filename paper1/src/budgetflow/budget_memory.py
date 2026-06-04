"""BudgetMemory — statistical budget learning from historical JSONL.

Separate from PolicyMemory (routing priors) and AutoBudgetEstimator (task-feature
kNN).  BudgetMemory learns cost distributions per task, repo, and strategy, then
produces budget estimates with confidence and risk multipliers.

No ML, no task features — pure statistical aggregation from outcome records.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


def normalize_repo_key(raw: str) -> str:
    """Normalize repo identifiers to canonical short key.

    Handles:
      instance_id:  "sympy__sympy-13480" -> "sympy"
      repo slug:    "sympy__sympy"       -> "sympy"
      repo slug:    "sympy/sympy"        -> "sympy"
      plain key:    "sympy"              -> "sympy"
    """
    if not raw:
        return raw
    return raw.replace("/", "__").split("__")[0]


def _extract_repo(instance_id: str) -> str:
    return normalize_repo_key(instance_id)


@dataclass
class BudgetEstimate:
    """Result of estimate_task_budget()."""
    estimated_task_budget: float
    budget_source: str       # "exact_task", "repo_median", "strategy_median", "global_fallback"
    budget_confidence: str   # "high", "medium", "low"
    budget_reason: str       # human-readable explanation
    hard_budget_used: bool
    predicted_cost: float
    risk_multiplier: float


@dataclass
class _TaskCostStats:
    instance_id: str
    repo: str = ""
    count: int = 0
    pass_count: int = 0
    median_cost: float = 0.0
    pass_median_cost: float = 0.0
    fail_median_cost: float = 0.0
    strategy_costs: dict[str, float] = field(default_factory=dict)
    budget_exhaustion_rate: float = 0.0

    def __post_init__(self) -> None:
        if not self.repo:
            self.repo = _extract_repo(self.instance_id)


@dataclass
class _RepoCostStats:
    repo: str
    count: int = 0
    median_cost: float = 0.0
    pass_median_cost: float = 0.0
    fail_median_cost: float = 0.0
    budget_exhaustion_rate: float = 0.0


class BudgetMemory:
    """Statistical budget learner from JSONL outcome records.

    Learns: task median cost, repo median cost, strategy median cost,
    pass/fail median costs, budget exhaustion rate, stage cost stats.
    """

    def __init__(self):
        self._task_stats: dict[str, _TaskCostStats] = {}
        self._repo_stats: dict[str, _RepoCostStats] = {}
        self._strategy_costs: dict[str, list[float]] = defaultdict(list)
        self._global_costs: list[float] = []
        self._record_count: int = 0
        self._source_paths: list[str] = []

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def from_jsonl(
        cls,
        paths: str | Path | Iterable[str | Path],
        exclude_ids: set[str] | None = None,
    ) -> BudgetMemory:
        """Build BudgetMemory from one or more JSONL files.

        If *exclude_ids* is given, records matching those instance_ids are
        excluded from training (used for leave-one-task-out validation).
        """
        bm = cls()
        if isinstance(paths, (str, Path)):
            paths = [Path(paths)]
        else:
            paths = [Path(p) for p in paths]

        records: list[dict] = []
        for p in paths:
            p = Path(p)
            if not p.is_file():
                continue
            bm._source_paths.append(str(p))
            for line in p.read_text(errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        bm._learn(records, exclude_ids=exclude_ids)
        return bm

    # ── Learning ──────────────────────────────────────────────────────────

    def _learn(self, records: list[dict], exclude_ids: set[str] | None = None) -> None:
        exclude = exclude_ids or set()
        filtered = [r for r in records if str(r.get("instance_id") or "") not in exclude]
        self._record_count = len(filtered)

        # Group costs
        task_costs: dict[str, list[float]] = defaultdict(list)
        task_pass_costs: dict[str, list[float]] = defaultdict(list)
        task_fail_costs: dict[str, list[float]] = defaultdict(list)
        repo_costs: dict[str, list[float]] = defaultdict(list)
        repo_pass_costs: dict[str, list[float]] = defaultdict(list)
        repo_fail_costs: dict[str, list[float]] = defaultdict(list)
        task_budget_exhausted: dict[str, int] = defaultdict(int)
        repo_budget_exhausted: dict[str, int] = defaultdict(int)

        for r in filtered:
            iid = str(r.get("instance_id") or "")
            if not iid:
                continue
            repo = _extract_repo(iid)
            cost = float(r.get("total_cost") or r.get("task_cost") or 0)
            passed = r.get("harness_resolved") in (True, "True", "true")
            strat = str(r.get("strategy") or "unknown")
            exit_status = str(r.get("exit_status") or "")
            exit_reason = str(r.get("exit_reason") or "")

            task_costs[iid].append(cost)
            repo_costs[repo].append(cost)
            self._strategy_costs[strat].append(cost)
            self._global_costs.append(cost)

            if passed:
                task_pass_costs[iid].append(cost)
                repo_pass_costs[repo].append(cost)
            else:
                task_fail_costs[iid].append(cost)
                repo_fail_costs[repo].append(cost)

            if exit_status == "BudgetFlowBudgetError" or "budget" in exit_reason.lower():
                task_budget_exhausted[iid] += 1
                repo_budget_exhausted[repo] += 1

        # Build task stats
        for iid, costs in task_costs.items():
            repo = _extract_repo(iid)
            stats = _TaskCostStats(instance_id=iid, repo=repo)
            stats.count = len(costs)
            stats.pass_count = len(task_pass_costs.get(iid, []))
            stats.median_cost = _median(costs)
            stats.pass_median_cost = _median(task_pass_costs.get(iid, []))
            stats.fail_median_cost = _median(task_fail_costs.get(iid, []))
            stats.budget_exhaustion_rate = task_budget_exhausted[iid] / max(stats.count, 1)
            # Per-strategy median costs for this task
            task_recs = [r for r in filtered if r.get("instance_id") == iid]
            strat_groups: dict[str, list[float]] = defaultdict(list)
            for r in task_recs:
                s = str(r.get("strategy") or "unknown")
                strat_groups[s].append(float(r.get("total_cost") or r.get("task_cost") or 0))
            stats.strategy_costs = {s: _median(cs) for s, cs in strat_groups.items()}
            self._task_stats[iid] = stats

        # Build repo stats
        for repo, costs in repo_costs.items():
            rs = _RepoCostStats(repo=repo)
            rs.count = len(costs)
            rs.median_cost = _median(costs)
            rs.pass_median_cost = _median(repo_pass_costs.get(repo, []))
            rs.fail_median_cost = _median(repo_fail_costs.get(repo, []))
            rs.budget_exhaustion_rate = repo_budget_exhausted[repo] / max(rs.count, 1)
            self._repo_stats[repo] = rs

    # ── Estimation ────────────────────────────────────────────────────────

    def estimate_task_budget(
        self,
        instance_id: str,
        repo: str = "",
        strategy: str = "",
        task_value: float = 1.0,
        hard_budget: float | None = None,
    ) -> BudgetEstimate:
        """Estimate a task budget from learned statistics.

        Cascades: exact_task → repo_median → strategy_median → global_fallback.
        If hard_budget is set, the estimate is capped to it.
        task_value scales the estimate (1.0 = default difficulty, >1 = harder).
        """
        if not repo:
            repo = _extract_repo(instance_id)
        else:
            repo = normalize_repo_key(repo)
        hard_budget_used = hard_budget is not None and hard_budget > 0

        # 1. Exact task match
        task_stat = self._task_stats.get(instance_id)
        if task_stat is not None and task_stat.count >= 2:
            base_cost = task_stat.median_cost
            confidence = "high" if task_stat.count >= 4 else "medium"
            # Risk multiplier: higher if budget exhaustion is common
            risk = 1.0 + task_stat.budget_exhaustion_rate * 2.0
            predicted = base_cost * task_value * risk
            reason = (
                f"exact_task: {task_stat.count} records, "
                f"median=${base_cost:.4f}, pass_rate={task_stat.pass_count / max(task_stat.count, 1):.0%}, "
                f"budget_exhaust={task_stat.budget_exhaustion_rate:.0%}"
            )
            return self._finalize(
                predicted, "exact_task", confidence, reason,
                hard_budget, hard_budget_used, base_cost, risk,
            )

        # 2. Repo median
        repo_stat = self._repo_stats.get(repo)
        if repo_stat is not None and repo_stat.count >= 3:
            base_cost = repo_stat.median_cost
            confidence = "medium" if repo_stat.count >= 6 else "low"
            risk = 1.0 + repo_stat.budget_exhaustion_rate * 2.0
            predicted = base_cost * task_value * risk
            reason = (
                f"repo_median: {repo} {repo_stat.count} records, "
                f"median=${base_cost:.4f}"
            )
            return self._finalize(
                predicted, "repo_median", confidence, reason,
                hard_budget, hard_budget_used, base_cost, risk,
            )

        # 3. Strategy median
        if strategy and strategy in self._strategy_costs:
            strat_costs = self._strategy_costs[strategy]
            if len(strat_costs) >= 2:
                base_cost = _median(strat_costs)
                risk = 1.5  # higher risk for strategy-only estimate
                predicted = base_cost * task_value * risk
                reason = (
                    f"strategy_median: {strategy} {len(strat_costs)} records, "
                    f"median=${base_cost:.4f}"
                )
                return self._finalize(
                    predicted, "strategy_median", "low", reason,
                    hard_budget, hard_budget_used, base_cost, risk,
                )

        # 4. Global fallback
        if self._global_costs:
            base_cost = _median(self._global_costs)
            risk = 2.0
            predicted = base_cost * task_value * risk
            reason = f"global_fallback: {len(self._global_costs)} records, median=${base_cost:.4f}"
        else:
            base_cost = 0.50
            risk = 3.0
            predicted = base_cost * task_value * risk
            reason = "global_fallback: no data, default $0.50"
        return self._finalize(
            predicted, "global_fallback", "low", reason,
            hard_budget, hard_budget_used, base_cost, risk,
        )

    def _finalize(
        self,
        predicted: float,
        source: str,
        confidence: str,
        reason: str,
        hard_budget: float | None,
        hard_budget_used: bool,
        base_cost: float,
        risk: float,
    ) -> BudgetEstimate:
        budget = predicted
        if hard_budget_used:
            budget = min(predicted, hard_budget)
            reason += f", hard_budget=${hard_budget:.4f}"
        return BudgetEstimate(
            estimated_task_budget=round(budget, 4),
            budget_source=source,
            budget_confidence=confidence,
            budget_reason=reason,
            hard_budget_used=hard_budget_used,
            predicted_cost=round(predicted, 4),
            risk_multiplier=round(risk, 2),
        )

    # ── Query ─────────────────────────────────────────────────────────────

    @property
    def record_count(self) -> int:
        return self._record_count

    @property
    def task_count(self) -> int:
        return len(self._task_stats)

    @property
    def repo_count(self) -> int:
        return len(self._repo_stats)

    def task_stats(self, instance_id: str) -> _TaskCostStats | None:
        return self._task_stats.get(instance_id)

    def repo_stats(self, repo: str) -> _RepoCostStats | None:
        return self._repo_stats.get(repo)

    def summary_lines(self) -> list[str]:
        lines = ["budget_memory:"]
        lines.append(f"  records={self._record_count} tasks={self.task_count} repos={self.repo_count}")
        for repo, rs in sorted(self._repo_stats.items()):
            lines.append(
                f"  {repo}: n={rs.count} median=${rs.median_cost:.4f} "
                f"pass_median=${rs.pass_median_cost:.4f} fail_median=${rs.fail_median_cost:.4f} "
                f"budget_exhaust={rs.budget_exhaustion_rate:.0%}"
            )
        return lines


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


# ── Offline demo CLI (no API calls) ─────────────────────────────────────────

def run_demo(jsonl_paths: list[str]) -> str:
    """Load JSONL file(s), build BudgetMemory, print per-task estimates.

    Pure offline operation — no API calls, no experiment runs.
    """
    bm = BudgetMemory.from_jsonl(jsonl_paths)
    lines = ["=== BudgetMemory offline demo ==="]
    lines.append(f"source: {jsonl_paths}")
    lines.append(f"records={bm.record_count} tasks={bm.task_count} repos={bm.repo_count}")
    lines.append("")

    lines.append("Per-task estimates (strategy=budget_only_tight, task_value=1.0):")
    lines.append(f"  {'task':<35} {'est_budget':>10} {'source':<20} {'confidence':>10} {'risk':>6}")
    lines.append(f"  {'-'*85}")

    for iid in sorted(bm._task_stats.keys()):
        est = bm.estimate_task_budget(iid, strategy="budget_only_tight")
        lines.append(
            f"  {iid:<35} ${est.estimated_task_budget:>9.4f} "
            f"{est.budget_source:<20} {est.budget_confidence:<10} {est.risk_multiplier:>5.1f}x"
        )

    lines.append("")
    lines.append("Repo-level medians:")
    for repo in sorted(bm._repo_stats.keys()):
        rs = bm._repo_stats[repo]
        lines.append(
            f"  {repo}: n={rs.count} median=${rs.median_cost:.4f} "
            f"pass_median=${rs.pass_median_cost:.4f} fail_median=${rs.fail_median_cost:.4f}"
        )

    lines.append("")
    lines.append("NOTE: BudgetMemory is an offline learning skeleton.")
    lines.append("It is NOT yet integrated into run_mini_swe_compare real budget allocation.")
    lines.append("Use AutoBudgetEstimator (auto_budget.py) for live per-task cap estimation.")

    return "\n".join(lines)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="BudgetMemory offline demo — no API calls")
    parser.add_argument("--jsonl", type=str, nargs="+", required=True,
                        help="one or more JSONL files to learn from")
    args = parser.parse_args()
    print(run_demo(list(args.jsonl)))


if __name__ == "__main__":
    main()

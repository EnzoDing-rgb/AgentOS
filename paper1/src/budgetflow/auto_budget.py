from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# Embedded historical prior from paper1/docs/reports/historical_budgeting_prior.md.
# Costs recalibrated to real USD (2026-06).
# Updated 2026-06-03: added 5 tasks from postfix_011_sanity (5-strategy observed costs).
_HISTORICAL_PRIOR: dict[str, dict] = {
    # From 7×15 historical data (recalibrated).
    "sympy__sympy-13480": {"median_cost": 0.04, "median_turns": 14, "resolved": 7, "total": 8},
    "sympy__sympy-13647": {"median_cost": 0.11, "median_turns": 25, "resolved": 7, "total": 8},
    "sympy__sympy-16988": {"median_cost": 0.70, "median_turns": 141, "resolved": 3, "total": 8},
    "sympy__sympy-17139": {"median_cost": 0.24, "median_turns": 39, "resolved": 1, "total": 1},
    "sympy__sympy-20212": {"median_cost": 0.10, "median_turns": 46, "resolved": 8, "total": 8},
    # From postfix_011_sanity (2026-06-03, 4-5 strategies observed).
    "sympy__sympy-14774": {"median_cost": 0.05, "median_turns": 6, "resolved": 5, "total": 5},
    "sympy__sympy-18057": {"median_cost": 0.08, "median_turns": 5, "resolved": 3, "total": 4},
    "sympy__sympy-18189": {"median_cost": 0.12, "median_turns": 8, "resolved": 4, "total": 4},
    "sympy__sympy-18621": {"median_cost": 0.17, "median_turns": 7, "resolved": 4, "total": 4},
    "django__django-10924": {"median_cost": 0.13, "median_turns": 8, "resolved": 4, "total": 4},
}

# Difficulty bucket thresholds.
_EASY_PATCH_LINES = 15
_EASY_F2P_COUNT = 3
_HARD_PATCH_LINES = 30
_HARD_F2P_COUNT = 8

# Fallback cost estimates per bucket (before scale and repo adjustment).
# Values in real USD (calibrated 2026-06).
_FALLBACK_COST = {
    "easy": 0.20,
    "medium": 0.50,
    "hard": 1.50,
}

# Per-repo minimum estimated_cost before scaling.
# Ensures repos known to be harder (Django) get adequate budget even for "easy" tasks.
_REPO_FLOOR_ESTIMATED_COST: dict[str, float] = {
    "django/django": 1.00,
}


@dataclass(frozen=True)
class BudgetEstimate:
    instance_id: str
    estimated_cost: float
    cap: float
    source: str  # "history_exact", "memory_exact", "memory_exact_any", "memory_repo_knn", "global_fallback"
    confidence: str  # "high", "medium", "low"
    features: dict[str, float | int | str] = field(default_factory=dict)
    memory_neighbors: int = 0  # kNN count used (for memory-based estimates)


class AutoBudgetMemory:
    """Continuous learning memory: persists task cost records across runs.

    Stored as JSONL at ``memory_path``. Each record captures task features,
    strategy, outcome, and cap-sufficiency signal for future estimation.
    """

    def __init__(self, memory_path: Path | None = None):
        self._path = memory_path
        self._records: list[dict] = []
        if memory_path is not None and memory_path.is_file():
            self._records = self._load(memory_path)

    @staticmethod
    def _load(path: Path) -> list[dict]:
        records: list[dict] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    @property
    def records(self) -> list[dict]:
        return list(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def write_record(self, record: dict) -> None:
        """Append a memory record and flush to disk."""
        record.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S"))
        record.setdefault("estimator_version", "v1")
        self._records.append(dict(record))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @classmethod
    def build_record(
        cls,
        *,
        instance_id: str,
        repo: str,
        strategy: str,
        routing: str,
        resolved: bool,
        harness_resolved: bool,
        failure_class: str,
        forensic_primary_axis: str,
        total_cost: float,
        estimated_task_cap: float | None,
        estimated_task_cost: float | None,
        patch_extracted: bool,
        agent_gold_edited: bool,
        llm_turns: int,
        patch_lines: int,
        f2p_count: int,
        p2p_count: int,
        problem_length: int,
        gold_file_count: int,
        run_series: str = "",
        run_id: str = "",
        dominant_tier: str = "",
        exit_status: str = "",
        detail: str = "",
    ) -> dict:
        cap_was_sufficient = _classify_cap_sufficiency(
            resolved=resolved,
            harness_resolved=harness_resolved,
            exit_status=exit_status,
            failure_class=failure_class,
            patch_extracted=patch_extracted,
            agent_gold_edited=agent_gold_edited,
        )
        return {
            "instance_id": instance_id,
            "repo": repo,
            "strategy": strategy,
            "routing": routing,
            "dominant_tier": dominant_tier,
            "resolved": resolved,
            "harness_resolved": harness_resolved,
            "failure_class": failure_class,
            "forensic_primary_axis": forensic_primary_axis,
            "total_cost": total_cost,
            "estimated_task_cap": estimated_task_cap,
            "estimated_task_cost": estimated_task_cost,
            "cap_was_sufficient": cap_was_sufficient,
            "patch_extracted": patch_extracted,
            "agent_gold_edited": agent_gold_edited,
            "llm_turns": llm_turns,
            "patch_lines": patch_lines,
            "f2p_count": f2p_count,
            "p2p_count": p2p_count,
            "problem_length": problem_length,
            "gold_file_count": gold_file_count,
            "exit_status": exit_status,
            "detail": detail[:200] if detail else "",
            "run_series": run_series,
            "run_id": run_id,
        }


def _classify_cap_sufficiency(
    *,
    resolved: bool,
    harness_resolved: bool,
    exit_status: str,
    failure_class: str,
    patch_extracted: bool,
    agent_gold_edited: bool,
) -> str:
    """Classify whether the estimated cap was sufficient."""
    if resolved and harness_resolved:
        return "sufficient"
    # Harness failures: exclude from learning.
    if failure_class in ("harness_failure", "harness_error"):
        return "exclude_harness"
    # Budget exhausted but agent made progress.
    if exit_status in ("BudgetFlowBudgetError", "budget_exhausted"):
        if failure_class == "repair_quality":
            return "underbudget_or_model"
        if patch_extracted or agent_gold_edited:
            return "likely_underbudget"
        return "not_enough_evidence"
    # Corrupt patch / protocol failure.
    if failure_class in ("protocol_failure", "corrupt_patch"):
        return "exclude_corrupt"
    return "not_enough_evidence"


class AutoBudgetEstimator:
    def __init__(
        self,
        prior: dict[str, dict] | None = None,
        memory: AutoBudgetMemory | None = None,
        k: int = 3,
    ):
        self._prior = dict(prior) if prior is not None else dict(_HISTORICAL_PRIOR)
        self._memory = memory
        self._k = k

    @classmethod
    def from_history(cls, path: Path) -> "AutoBudgetEstimator":
        prior: dict[str, dict] = {}
        if path.is_file():
            records = []
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            from collections import defaultdict

            groups: dict[str, list[float]] = defaultdict(list)
            for r in records:
                iid = r.get("instance_id")
                cost = r.get("task_cost") or r.get("total_cost") or 0.0
                if iid and cost > 0:
                    groups[iid].append(cost)
            for iid, costs in groups.items():
                costs.sort()
                median = costs[len(costs) // 2]
                prior[iid] = {
                    "median_cost": median,
                    "median_turns": 0,
                    "resolved": len(costs),
                    "total": len(costs),
                }
        if not prior:
            prior = dict(_HISTORICAL_PRIOR)
        return cls(prior)

    @property
    def memory(self) -> AutoBudgetMemory | None:
        return self._memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate(
        self,
        task,
        *,
        scale: float = 1.5,
        min_cap: float = 0.10,
        max_cap: float = 10.0,
    ) -> BudgetEstimate:
        iid = task.instance_id
        patch_lines = len(task.patch.splitlines())
        f2p_count = len(task.fail_to_pass)
        p2p_count = len(task.pass_to_pass)
        repo = getattr(task, "repo", "") or ""
        base_features = {
            "patch_lines": patch_lines,
            "f2p_count": f2p_count,
            "p2p_count": p2p_count,
        }

        # 1. Memory: exact task + strategy match (most specific).
        if self._memory is not None:
            est = self._estimate_from_memory_exact(iid, patch_lines, f2p_count, p2p_count)
            if est is not None:
                return self._finalize(
                    est, scale, min_cap, max_cap, repo,
                    features=base_features,
                )

            # 2. Memory: same task, any strategy.
            est = self._estimate_from_memory_exact_any(iid, patch_lines, f2p_count, p2p_count)
            if est is not None:
                return self._finalize(
                    est, scale, min_cap, max_cap, repo,
                    features=base_features,
                )

        # 3. Embedded historical prior.
        hist = self._prior.get(iid)
        if hist is not None:
            median = float(hist["median_cost"])
            resolved_ratio = hist["resolved"] / max(hist["total"], 1)
            confidence = "high" if resolved_ratio >= 0.75 and hist["resolved"] >= 3 else "medium"
            cap = self._compute_cap(median, scale, min_cap, max_cap, repo)
            return BudgetEstimate(
                instance_id=iid,
                estimated_cost=median,
                cap=cap,
                source="history_exact",
                confidence=confidence,
                features={
                    **base_features,
                    "resolved_ratio": round(resolved_ratio, 2),
                },
            )

        # 4. Memory: same repo, kNN by features.
        if self._memory is not None:
            est = self._estimate_from_memory_knn(
                repo, patch_lines, f2p_count, p2p_count,
            )
            if est is not None and est.get("neighbors", 0) > 0:
                median = est["median_cost"]
                return self._finalize(
                    est, scale, min_cap, max_cap, repo,
                    features=base_features,
                )

        # 5. Global fallback.
        return self._fallback_estimate(
            iid, repo, patch_lines, f2p_count, p2p_count,
            scale, min_cap, max_cap,
        )

    # ------------------------------------------------------------------
    # Estimation helpers
    # ------------------------------------------------------------------

    def _finalize(
        self,
        est: dict,
        scale: float,
        min_cap: float,
        max_cap: float,
        repo: str,
        *,
        features: dict,
    ) -> BudgetEstimate:
        median = est["median_cost"]
        source = est.get("source", "memory_exact")
        neighbors = est.get("neighbors", 0)
        confidence = est.get("confidence", "low")
        if confidence == "low" and neighbors >= 2:
            confidence = "medium"
        cap = self._compute_cap(median, scale, min_cap, max_cap, repo)
        return BudgetEstimate(
            instance_id=est.get("instance_id", ""),
            estimated_cost=median,
            cap=cap,
            source=source,
            confidence=confidence,
            features=dict(features),
            memory_neighbors=neighbors,
        )

    def _compute_cap(
        self,
        estimated_cost: float,
        scale: float,
        min_cap: float,
        max_cap: float,
        repo: str,
    ) -> float:
        """cap = max(repo_floor, min_cap, estimated_cost * scale), clamped to max_cap."""
        floor = _REPO_FLOOR_ESTIMATED_COST.get(repo, 0.0)
        raw = max(floor, min_cap, estimated_cost * scale)
        return _clamp(raw, min_cap, max_cap)

    def _estimate_from_memory_exact(
        self, iid: str, patch_lines: int, f2p_count: int, p2p_count: int
    ) -> dict | None:
        """Find memory records for exact task. Return median of successful costs."""
        return self._median_from_records(
            [r for r in self._memory.records if r.get("instance_id") == iid],
            source="memory_exact",
            features={"patch_lines": patch_lines, "f2p_count": f2p_count, "p2p_count": p2p_count},
        )

    def _estimate_from_memory_exact_any(
        self, iid: str, patch_lines: int, f2p_count: int, p2p_count: int
    ) -> dict | None:
        """Memory records for same task, any strategy."""
        return self._median_from_records(
            [r for r in self._memory.records if r.get("instance_id") == iid],
            source="memory_exact_any",
            features={"patch_lines": patch_lines, "f2p_count": f2p_count, "p2p_count": p2p_count},
        )

    def _estimate_from_memory_knn(
        self, repo: str, patch_lines: int, f2p_count: int, p2p_count: int
    ) -> dict | None:
        """kNN by task features within same repo."""
        if not repo:
            return None
        same_repo = [r for r in self._memory.records if r.get("repo") == repo]
        if not same_repo:
            return None
        # Filter to records with cost data and usable outcomes.
        usable = [
            r for r in same_repo
            if r.get("total_cost", 0) > 0
            and r.get("cap_was_sufficient") not in ("exclude_harness", "exclude_corrupt")
        ]
        if not usable:
            return None
        # Compute distance to each record.
        scored = []
        for r in usable:
            rpl = r.get("patch_lines", 0)
            rf2p = r.get("f2p_count", 0)
            rp2p = r.get("p2p_count", 0)
            dist = math.sqrt(
                (patch_lines - rpl) ** 2
                + (f2p_count - rf2p) ** 2 * 4  # weight f2p higher
                + (p2p_count - rp2p) ** 2
            )
            scored.append((dist, r))
        scored.sort(key=lambda x: x[0])
        neighbors = scored[: self._k]
        costs = [r.get("total_cost", 0) for _, r in neighbors if r.get("total_cost", 0) > 0]
        if not costs:
            return None
        costs.sort()
        median = costs[len(costs) // 2]
        return {
            "instance_id": f"knn:{repo}",
            "median_cost": median,
            "source": "memory_repo_knn",
            "neighbors": len(neighbors),
            "confidence": "medium" if len(neighbors) >= 2 else "low",
        }

    def _median_from_records(self, records: list[dict], *, source: str, features: dict) -> dict | None:
        """Compute median total_cost from usable memory records."""
        usable = [
            r for r in records
            if r.get("total_cost", 0) > 0
            and r.get("cap_was_sufficient") not in ("exclude_harness", "exclude_corrupt")
        ]
        if not usable:
            return None
        # Check for underbudget signals → inflate.
        underbudget_costs = [
            r.get("total_cost", 0) for r in usable
            if r.get("cap_was_sufficient") == "likely_underbudget"
        ]
        costs = [r.get("total_cost", 0) for r in usable]
        costs.sort()
        median = costs[len(costs) // 2]
        # If underbudget exists, ensure estimated_cost >= max underbudget cost * 1.5
        if underbudget_costs:
            inflated = max(underbudget_costs) * 1.5
            median = max(median, inflated)
        resolved_count = sum(1 for r in usable if r.get("resolved"))
        confidence = "high" if resolved_count >= 3 and len(usable) >= 3 else "medium"
        result = {
            "median_cost": median,
            "source": source,
            "neighbors": len(usable),
            "confidence": confidence,
        }
        result.update({f"features_{k}": v for k, v in features.items()})
        return result

    def _fallback_estimate(
        self,
        iid: str,
        repo: str,
        patch_lines: int,
        f2p_count: int,
        p2p_count: int,
        scale: float,
        min_cap: float,
        max_cap: float,
    ) -> BudgetEstimate:
        difficulty_score = patch_lines + f2p_count * 2
        if difficulty_score <= _EASY_PATCH_LINES + _EASY_F2P_COUNT * 2:
            bucket = "easy"
        elif difficulty_score >= _HARD_PATCH_LINES + _HARD_F2P_COUNT * 2:
            bucket = "hard"
        else:
            bucket = "medium"

        base = _FALLBACK_COST[bucket]
        # Apply repo floor: some repos need higher baseline even for "easy" tasks.
        repo_floor = _REPO_FLOOR_ESTIMATED_COST.get(repo, 0.0)
        estimated_cost = max(base, repo_floor)
        cap = self._compute_cap(estimated_cost, scale, min_cap, max_cap, repo)

        features: dict[str, float | int | str] = {
            "patch_lines": patch_lines,
            "f2p_count": f2p_count,
            "p2p_count": p2p_count,
            "bucket": bucket,
            "difficulty_score": difficulty_score,
        }
        return BudgetEstimate(
            instance_id=iid,
            estimated_cost=estimated_cost,
            cap=cap,
            source="global_fallback",
            confidence="low",
            features=features,
        )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))

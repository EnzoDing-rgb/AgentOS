from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol

from .model_tiers import catalog_revision

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

_LEARNABLE_CAP_SUFFICIENCY = {
    "sufficient",
    "likely_underbudget",
    "underbudget_or_model",
}

@dataclass(frozen=True)
class CostTaskFeatures:
    instance_id: str
    repo: str
    patch_lines: int
    f2p_count: int
    p2p_count: int
    cost_floor: float = 0.0


class CostFeatureAdapter(Protocol):
    def cost_features(self, task: object) -> CostTaskFeatures: ...


@dataclass(frozen=True)
class BudgetEstimate:
    instance_id: str
    estimated_cost: float
    cap: float
    source: str  # "explicit_prior_exact", "memory_exact", "memory_exact_any", "memory_repo_knn", "global_fallback"
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
            "cost_catalog_revision": catalog_revision(),
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
        feature_adapter: CostFeatureAdapter | None = None,
        k: int = 3,
    ):
        self._prior = dict(prior) if prior is not None else {}
        self._memory = memory
        self._feature_adapter = feature_adapter
        self._k = k

    @classmethod
    def from_history(
        cls,
        path: Path,
        *,
        feature_adapter: CostFeatureAdapter | None = None,
    ) -> "AutoBudgetEstimator":
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
        return cls(prior, feature_adapter=feature_adapter)

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
        features = self._features(task)
        iid = features.instance_id
        repo = features.repo
        patch_lines = features.patch_lines
        f2p_count = features.f2p_count
        p2p_count = features.p2p_count
        cost_floor = features.cost_floor
        base_features = {
            "patch_lines": patch_lines,
            "f2p_count": f2p_count,
            "p2p_count": p2p_count,
            "cost_floor": cost_floor,
        }

        # 1. Memory: exact task + strategy match (most specific).
        if self._memory is not None:
            est = self._estimate_from_memory_exact(iid, patch_lines, f2p_count, p2p_count)
            if est is not None:
                return self._finalize(
                    est, scale, min_cap, max_cap, cost_floor,
                    features=base_features,
                )

            # 2. Memory: same task, any strategy.
            est = self._estimate_from_memory_exact_any(iid, patch_lines, f2p_count, p2p_count)
            if est is not None:
                return self._finalize(
                    est, scale, min_cap, max_cap, cost_floor,
                    features=base_features,
                )

        # 3. Explicit prior from a user-selected source.
        hist = self._prior.get(iid)
        if hist is not None:
            median = float(hist["median_cost"])
            resolved_ratio = hist["resolved"] / max(hist["total"], 1)
            confidence = "high" if resolved_ratio >= 0.75 and hist["resolved"] >= 3 else "medium"
            cap = self._compute_cap(median, scale, min_cap, max_cap, cost_floor)
            return BudgetEstimate(
                instance_id=iid,
                estimated_cost=median,
                cap=cap,
                source="explicit_prior_exact",
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
                    est, scale, min_cap, max_cap, cost_floor,
                    features=base_features,
                )

        # 5. Global fallback.
        return self._fallback_estimate(
            iid, repo, patch_lines, f2p_count, p2p_count,
            cost_floor, scale, min_cap, max_cap,
        )

    def _features(self, task: object) -> CostTaskFeatures:
        if self._feature_adapter is None:
            raise TypeError("AutoBudgetEstimator requires a CostFeatureAdapter")
        return self._feature_adapter.cost_features(task)

    # ------------------------------------------------------------------
    # Estimation helpers
    # ------------------------------------------------------------------

    def _finalize(
        self,
        est: dict,
        scale: float,
        min_cap: float,
        max_cap: float,
        cost_floor: float,
        *,
        features: dict,
    ) -> BudgetEstimate:
        median = float(est["median_cost"])
        source = est.get("source", "memory_exact")
        neighbors = est.get("neighbors", 0)
        confidence = est.get("confidence", "low")
        if confidence == "low" and neighbors >= 2:
            confidence = "medium"
        cap = self._compute_cap(median, scale, min_cap, max_cap, cost_floor)
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
        cost_floor: float = 0.0,
    ) -> float:
        """cap = max(adapter_floor, min_cap, estimated_cost * scale), clamped to max_cap."""
        raw = max(float(cost_floor or 0.0), min_cap, estimated_cost * scale)
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
            and r.get("cap_was_sufficient") in _LEARNABLE_CAP_SUFFICIENCY
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
            and r.get("cap_was_sufficient") in _LEARNABLE_CAP_SUFFICIENCY
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
        cost_floor: float,
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
        estimated_cost = max(base, float(cost_floor or 0.0))
        cap = self._compute_cap(estimated_cost, scale, min_cap, max_cap, cost_floor)

        features: dict[str, float | int | str] = {
            "patch_lines": patch_lines,
            "f2p_count": f2p_count,
            "p2p_count": p2p_count,
            "bucket": bucket,
            "difficulty_score": difficulty_score,
            "cost_floor": float(cost_floor or 0.0),
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

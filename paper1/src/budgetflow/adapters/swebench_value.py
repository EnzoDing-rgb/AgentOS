"""Value adapter: normalizes task-value signals for BudgetFlow core.

Cold start can use a default heuristic, a human-authored value matrix,
natural-language policy, benchmark solve rarity, or enterprise data import.
Warm start can learn from verified outcomes, accepted work, priority patterns,
human correction, or external systems.

The core only consumes a normalized ValueEstimate plus confidence.
It does not know the value-matrix schema, enterprise field names, or
SWE-bench task metadata.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ValueEstimate:
    """Normalized task-value estimate consumed by BudgetFlow core."""

    value: float
    source: str
    confidence: dict[str, float | str | bool] = field(default_factory=dict)


class ValueAdapter(Protocol):
    """Contract: normalize task-value signals into ValueEstimate.

    Concrete adapters may use value matrices, NL rules, enterprise imports,
    or learned estimates. BudgetFlow core only consumes ValueEstimate.
    """

    def estimate(self, task_id: str, **hints: Any) -> ValueEstimate: ...
    def learn(self, task_id: str, resolved: bool, **context: Any) -> None: ...


class SwebenchValueAdapter:
    """SWE-bench value adapter wrapping the existing value matrix.

    Cold-start: uses a JSON value-matrix file (built offline from
    cross-strategy stats) or falls back to equal-weight (1.0).

    The value matrix schema, profile names, and task metadata are
    SWE-bench adapter details. BudgetFlow core only sees ValueEstimate.
    """

    def __init__(
        self,
        value_profile: str = "equal",
        value_matrix_path: str | None = None,
    ) -> None:
        self.profile = value_profile
        self.matrix_path = value_matrix_path
        self._lookup: dict[str, float] | None = None
        self._median: float = 1.0
        if value_matrix_path:
            self._load_matrix(value_matrix_path, value_profile)

    # ValueAdapter protocol

    def estimate(self, task_id: str, **hints: Any) -> ValueEstimate:
        if self._lookup is not None and task_id in self._lookup:
            return ValueEstimate(
                value=float(self._lookup[task_id]),
                source=f"value_matrix:{self.profile}",
                confidence={"matrix_path": self.matrix_path or "none", "profile": self.profile},
            )
        if self.profile == "equal":
            return ValueEstimate(value=1.0, source="default_equal", confidence={})
        # Non-equal profiles: missing task is a readiness failure, not a
        # silent fallback. BudgetFlow value discipline requires every task
        # to have an explicit value before paid experiments.
        raise ValueError(
            f"ValueAdapter: task '{task_id}' not found in value matrix "
            f"'{self.matrix_path}' for profile '{self.profile}'. "
            f"Add this task to the matrix or use --value-profile=equal."
        )

    def learn(self, task_id: str, resolved: bool, **context: Any) -> None:
        # Cold-start adapter is read-only; warm-start learning is a future path.
        pass

    # Internal

    @property
    def median_task_value(self) -> float:
        return self._median

    def _load_matrix(self, path: str, profile: str) -> None:
        artifact = json.loads(Path(path).read_text())
        tasks = artifact.get("tasks")
        if isinstance(tasks, dict) and tasks:
            lookup: dict[str, float] = {}
            for instance_id, task_data in tasks.items():
                if not isinstance(task_data, dict):
                    continue
                values = task_data.get("values")
                if isinstance(values, dict) and profile in values:
                    lookup[instance_id] = float(values[profile])
            if lookup:
                self._lookup = lookup
                self._median = _median(lookup.values())
                return
        # Fallback: try legacy matrix format
        matrix = artifact.get("matrix", {})
        profile_data = matrix.get(profile) if isinstance(matrix, dict) else None
        if profile_data and isinstance(profile_data, dict):
            lookup = {
                task_id: float(entry.get("value", 1.0))
                for task_id, entry in profile_data.items()
                if isinstance(entry, dict)
            }
            if lookup:
                self._lookup = lookup
                self._median = _median(lookup.values())

    def task_value(self, instance_id: str) -> tuple[float, str]:
        estimate = self.estimate(instance_id)
        return estimate.value, estimate.source


# Cold-start task feature extraction (SWE-bench specific)


def cold_start_task_features(task: Any) -> dict[str, int]:
    """Ex-ante SWE-bench task features used by the cold-start value profile."""
    return {
        "patch_lines": len(str(getattr(task, "patch", "") or "").splitlines()),
        "f2p_count": len(getattr(task, "fail_to_pass", ()) or ()),
        "p2p_count": len(getattr(task, "pass_to_pass", ()) or ()),
        "problem_words": len(str(getattr(task, "problem_statement", "") or "").split()),
        "gold_file_count": len(getattr(task, "gold_files", ()) or ()),
    }


def cold_start_task_values(task: Any) -> dict[str, float]:
    """No-outcome cold-start values from SWE-bench task metadata only."""
    features = cold_start_task_features(task)
    raw = (
        1.0
        + features["patch_lines"]
        + 2.0 * features["f2p_count"]
        + math.log1p(features["p2p_count"])
        + 0.01 * features["problem_words"]
        + 1.5 * features["gold_file_count"]
    )
    return {
        "equal": 1.0,
        "cold_start_difficulty": round(raw, 4),
    }


def build_cold_start_value_matrix(tasks: list[Any], *, task_source: str) -> dict[str, Any]:
    """Build value matrix for a selected task set without historical outcomes."""
    matrix: dict[str, Any] = {
        "meta": {
            "task_count": len(tasks),
            "profiles": ["equal", "cold_start_difficulty"],
            "source": task_source,
            "source_class": "cold_start_ex_ante_metadata",
            "outcome_free": True,
            "note": (
                "Cold-start task values use only ex-ante SWE-bench task metadata: "
                "patch lines, fail/pass test counts, problem words, and gold file count. "
                "No strategy outcome, cost, solve rarity, or BudgetFlow signal is used."
            ),
            "formula": (
                "cold_start_difficulty = 1 + patch_lines + 2*f2p_count + "
                "log1p(p2p_count) + 0.01*problem_words + 1.5*gold_file_count"
            ),
        },
        "tasks": {},
    }
    for task in tasks:
        features = cold_start_task_features(task)
        values = cold_start_task_values(task)
        matrix["tasks"][task.instance_id] = {
            "instance_id": task.instance_id,
            "repo": task.repo,
            "features": features,
            "values": values,
        }
    matrix["rankings"] = {}
    for profile in ("equal", "cold_start_difficulty"):
        ranked = sorted(
            matrix["tasks"].items(),
            key=lambda item: item[1]["values"][profile],
            reverse=True,
        )
        matrix["rankings"][profile] = [
            {"rank": index + 1, "instance_id": iid, "value": entry["values"][profile]}
            for index, (iid, entry) in enumerate(ranked)
        ]
    return matrix


def _median(values: Any) -> float:
    vals = sorted(float(v) for v in values)
    if not vals:
        return 1.0
    n = len(vals)
    return (vals[n // 2 - 1] + vals[n // 2]) / 2.0 if n % 2 == 0 else vals[n // 2]

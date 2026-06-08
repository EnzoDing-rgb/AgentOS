"""Value adapter: normalizes task-value signals for BudgetFlow core.

Bootstrap value estimation can use a default heuristic, a human-authored value
matrix, natural-language policy, benchmark metadata, or enterprise data import.
Learn Policy can use verified outcomes, accepted work, priority patterns,
human correction, or external systems.

The core only consumes a normalized ValueEstimate plus confidence.
It does not know the value-matrix schema, enterprise field names, or
SWE-bench task metadata.
"""

from __future__ import annotations

import json
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

    Bootstrap profile: uses a JSON value-matrix file or falls back to
    equal-weight (1.0).

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
        # The SWE-bench bootstrap value adapter is read-only; learned value is a future path.
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


def _median(values: Any) -> float:
    vals = sorted(float(v) for v in values)
    if not vals:
        return 1.0
    n = len(vals)
    return (vals[n // 2 - 1] + vals[n // 2]) / 2.0 if n % 2 == 0 else vals[n // 2]

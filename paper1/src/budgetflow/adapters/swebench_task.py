"""SWE-bench task adapter.

**Boundary: TaskAdapter vs ValueSource**

``TaskAdapter`` normalises raw SWE-bench tasks into ``TaskFeatures`` (patch_lines,
f2p_count, p2p_count, problem_length). It answers "what is this task?"

``ValueSource`` (see ``swebench_value.py``) maps those features to a task value
via a pre-registered value matrix JSON. It answers "how much is this task worth?"

The value matrix is the canonical value source for paper runs. TaskAdapter does
not compute value — it delegates to ValueSource via ``value_estimate()``.
This keeps the two concerns separate: task standardisation (adapter) and value
assignment (pre-registered source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..auto_budget import CostTaskFeatures
from .swebench_value import SwebenchValueAdapter, ValueEstimate

SWEBENCH_COST_FLOORS: dict[str, float] = {
    "django/django": 1.00,
}


@dataclass(frozen=True)
class TaskFeatures:
    patch_lines: int = 0
    f2p_count: int = 0
    p2p_count: int = 0
    problem_length: int = 0
    extra: dict[str, int | float | str | bool] = field(default_factory=dict)

    def as_record(self) -> dict[str, int | float | str | bool]:
        return {
            "patch_lines": self.patch_lines,
            "f2p_count": self.f2p_count,
            "p2p_count": self.p2p_count,
            "problem_length": self.problem_length,
            **self.extra,
        }


class TaskAdapter(Protocol):
    def instance_id(self, task: Any) -> str: ...
    def features(self, task: Any) -> TaskFeatures: ...
    def value_estimate(self, task: Any) -> ValueEstimate: ...


class SwebenchTaskAdapter:
    """Normalize SWE-bench task records into BudgetFlow task fields."""

    def __init__(self, value_helper: SwebenchValueAdapter | None = None) -> None:
        self._value_helper = value_helper or SwebenchValueAdapter()

    def instance_id(self, task: Any) -> str:
        return str(getattr(task, "instance_id"))

    def features(self, task: Any) -> TaskFeatures:
        return TaskFeatures(
            patch_lines=len(str(getattr(task, "patch", "") or "").splitlines()),
            f2p_count=len(getattr(task, "fail_to_pass", ()) or ()),
            p2p_count=len(getattr(task, "pass_to_pass", ()) or ()),
            problem_length=len(str(getattr(task, "problem_statement", "") or "")),
        )

    def value_estimate(self, task: Any) -> ValueEstimate:
        return self._value_helper.estimate(self.instance_id(task))

    def cost_features(self, task: Any) -> CostTaskFeatures:
        features = self.features(task)
        repo = str(getattr(task, "repo", "") or "")
        return CostTaskFeatures(
            instance_id=self.instance_id(task),
            repo=repo,
            patch_lines=features.patch_lines,
            f2p_count=features.f2p_count,
            p2p_count=features.p2p_count,
            cost_floor=SWEBENCH_COST_FLOORS.get(repo, 0.0),
        )

"""SWE-bench task adapter.

Task metadata such as fail-to-pass tests, pass-to-pass tests, patch text, and
problem statement are SWE-bench details. BudgetFlow runtime records should
consume normalized task features.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


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


class SwebenchTaskAdapter:
    """Normalize SWE-bench task records into BudgetFlow task fields."""

    def instance_id(self, task: Any) -> str:
        return str(getattr(task, "instance_id"))

    def features(self, task: Any) -> TaskFeatures:
        return TaskFeatures(
            patch_lines=len(str(getattr(task, "patch", "") or "").splitlines()),
            f2p_count=len(getattr(task, "fail_to_pass", ()) or ()),
            p2p_count=len(getattr(task, "pass_to_pass", ()) or ()),
            problem_length=len(str(getattr(task, "problem_statement", "") or "")),
        )

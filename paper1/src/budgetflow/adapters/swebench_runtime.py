"""SWE-bench runtime adapter."""

from __future__ import annotations

from typing import Any, Protocol


class RuntimeAdapter(Protocol):
    def run_task(self, task: Any, **kwargs: Any) -> Any: ...


class MiniSweRuntimeAdapter:
    """Call the existing mini-SWE runner behind a runtime adapter boundary."""

    def run_task(self, task: Any, **kwargs: Any) -> Any:
        from budgetflow.adapter.runner import run_mini_swe_task

        return run_mini_swe_task(task, **kwargs)

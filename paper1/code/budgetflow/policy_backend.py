"""Policy Backend: pluggable strategy interface for cap, routing, escalation, stop.

BudgetFlow Mechanism owns the budget ledger, settlement, and verified outcomes.
Policy backends own routing and stop/continue recommendations.
BootstrapPolicy is the default explainable startup policy; it is a first-class
policy backend, not benchmark-tuned code hidden in the BudgetFlow Mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Backend, WorkflowSegment, TurnInfo


@dataclass
class PolicyDecision:
    """Structured recommendation from a policy backend for one turn.

    The BudgetFlow Mechanism consumes this without knowing SWE-bench, provider price files,
    value-matrix schemas, or pytest output.
    """

    backend: str
    cap_usd: float | None = None
    should_stop: bool = False
    should_escalate: bool = False
    reason: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    confidence: dict[str, float | str | bool] = field(default_factory=dict)


class PolicyBackend(ABC):
    """Pluggable strategy that recommends cap, backend, escalation, and stop.

    Every policy backend receives *normalized* inputs: task, value, cost,
    budget, segment, history, and returns recommendations with reasons.
    It must NOT read SWE-bench files, parse pytest output, inspect worktrees
    directly, or load provider price files by itself.
    """

    @abstractmethod
    def estimate_cap(
        self,
        task_id: str,
        task_value: float,
        budget_remaining: float,
        budget_total: float,
        **kwargs: object,
    ) -> float:
        """Recommend a per-task cap in USD."""
        ...

    @abstractmethod
    def choose_backend(
        self,
        turn_info: TurnInfo,
        backends: list[Backend],
        budget_pressure: float,
        expected_costs: dict[str, float],
        segment: WorkflowSegment | None = None,
        **kwargs: object,
    ) -> PolicyDecision:
        """Recommend a backend (model tier) for this turn."""
        ...

    @abstractmethod
    def should_escalate(
        self,
        task_id: str,
        current_backend: str,
        progress_streak: int,
        no_progress_streak: int,
        **kwargs: object,
    ) -> bool:
        """Recommend whether to escalate to a stronger tier."""
        ...

    @abstractmethod
    def should_stop(
        self,
        task_id: str,
        budget_remaining: float,
        budget_total: float,
        turns_used: int,
        **kwargs: object,
    ) -> bool:
        """Recommend whether to stop work on this task."""
        ...


class BootstrapPolicy(PolicyBackend):
    """Default explainable policy backed by BudgetFlowSelector.

    This wraps the current BudgetFlowSelector tier-selection logic behind
    the PolicyBackend interface. It is the customer-facing startup policy:
    enterprises can use it as-is or replace it with a Learn Policy.
    """

    def __init__(
        self,
        selector: object,  # BudgetFlowSelector | ValueAwareSelector | ConservativeSelector
        name: str = "bootstrap",
    ) -> None:
        self._selector = selector
        self.name = name
        self._last_decision: PolicyDecision | None = None

    @property
    def last_decision(self) -> PolicyDecision | None:
        return self._last_decision

    def estimate_cap(
        self,
        task_id: str,
        task_value: float,
        budget_remaining: float,
        budget_total: float,
        **kwargs: object,
    ) -> float:
        """Not yet wired into runtime; returns budget_remaining as pass-through.

        Cap estimation is owned by Value-Driven Budget Allocation and
        per-task cap gating in the execution layer. This method exists to
        satisfy the PolicyBackend interface contract but must not affect runtime
        budget behavior in this slice. Future slices will wire a value-aware
        formula here once the cap-allocation path is refactored.
        """
        return budget_remaining

    def choose_backend(
        self,
        turn_info: TurnInfo,
        backends: list[Backend],
        budget_pressure: float,
        expected_costs: dict[str, float],
        segment: WorkflowSegment | None = None,
        **kwargs: object,
    ) -> PolicyDecision:
        # Delegate to the wrapped selector; extract task_value for VA selectors.
        task_value = kwargs.get("task_value", None)
        selector = self._selector

        if hasattr(selector, 'select_backend'):
            import inspect
            sig = inspect.signature(selector.select_backend)
            if 'task_value' in sig.parameters:
                selection = selector.select_backend(
                    turn_info=turn_info,
                    backends=list(backends),
                    budget_pressure=budget_pressure,
                    expected_costs=expected_costs,
                    task_value=float(task_value) if task_value is not None else None,
                )
            else:
                selection = selector.select_backend(
                    turn_info=turn_info,
                    backends=list(backends),
                    budget_pressure=budget_pressure,
                    expected_costs=expected_costs,
                )
            backend_name = selection.backend.name
            self._last_decision = PolicyDecision(
                backend=backend_name,
                reason=f"bootstrap:{selector.__class__.__name__}",
                scores={"selection_score": selection.score},
                confidence={},
            )
            return self._last_decision
        else:
            raise TypeError(f"Unexpected selector type: {type(selector)}")

    def should_escalate(
        self,
        task_id: str,
        current_backend: str,
        progress_streak: int,
        no_progress_streak: int,
        **kwargs: object,
    ) -> bool:
        # Default escalation rule: escalate when stuck long enough.
        return no_progress_streak >= 6 and progress_streak < 2

    def should_stop(
        self,
        task_id: str,
        budget_remaining: float,
        budget_total: float,
        turns_used: int,
        **kwargs: object,
    ) -> bool:
        # Default stop rule: stop when budget is exhausted or turns are very high.
        if budget_remaining <= 0.001:
            return True
        max_turns = int(kwargs.get("max_turns", 60))
        return turns_used >= max_turns

from __future__ import annotations

from dataclasses import dataclass

from .loop import MinimalAgentLoop, WorkflowResult, WorkflowSpec
from .selector import RouterDecision
from .types import Backend, TurnInfo


@dataclass(frozen=True)
class PolicyRunSummary:
    policy_name: str
    resolved_count: int
    total_cost: float
    workflow_results: tuple[WorkflowResult, ...]


class WorkflowLevelRouter:
    def choose_backend(self, average_w_i: float, backends: list[Backend], budget_pressure: float) -> Backend:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        if budget_pressure <= 0.2:
            return ordered[-1]
        if budget_pressure <= 0.45:
            if average_w_i >= 2.1:
                return ordered[2] if len(ordered) >= 3 else ordered[-1]
            return ordered[1] if len(ordered) >= 2 else ordered[0]
        if average_w_i >= 2.4:
            return ordered[1] if len(ordered) >= 2 else ordered[0]
        return ordered[0]


class BudgetOnlyStepRouter:
    def choose_backend(self, turn_info: TurnInfo, backends: list[Backend], budget_pressure: float) -> RouterDecision:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        n = len(ordered)
        if n <= 1:
            return RouterDecision(
                backend=ordered[0], reason="single_backend", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if budget_pressure >= 1.2:
            return RouterDecision(
                backend=ordered[0], reason=f"high_pressure={budget_pressure:.3f}", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if n == 2:
            return RouterDecision(
                backend=ordered[0], reason="cheapest_baseline_n2", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if budget_pressure >= 0.7:
            return RouterDecision(
                backend=ordered[0], reason=f"moderate_pressure={budget_pressure:.3f}", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if budget_pressure >= 0.35:
            return RouterDecision(
                backend=ordered[1], reason=f"low_pressure={budget_pressure:.3f}_tier2", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        return RouterDecision(
            backend=ordered[1], reason=f"very_low_pressure={budget_pressure:.3f}_tier2", scores={},
            pressure=budget_pressure, branch="budget_only",
        )


def summarize_policy_run(policy_name: str, results: list[WorkflowResult]) -> PolicyRunSummary:
    return PolicyRunSummary(
        policy_name=policy_name,
        resolved_count=sum(1 for result in results if result.resolved),
        total_cost=sum(result.total_cost for result in results),
        workflow_results=tuple(results),
    )

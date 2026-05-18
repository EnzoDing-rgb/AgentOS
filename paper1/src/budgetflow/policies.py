from __future__ import annotations

from dataclasses import dataclass

from .loop import MinimalAgentLoop, WorkflowResult, WorkflowSpec
from .types import Backend, TurnInfo


@dataclass(frozen=True)
class PolicyRunSummary:
    policy_name: str
    resolved_count: int
    total_cost: float
    workflow_results: tuple[WorkflowResult, ...]


class WorkflowLevelRouter:
    def choose_backend(self, turn_info: TurnInfo, backends: list[Backend]) -> Backend:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        return ordered[-1] if turn_info.w_i >= 2.5 else ordered[0]


class BudgetOnlyStepRouter:
    def choose_backend(self, turn_info: TurnInfo, backends: list[Backend], budget_pressure: float) -> Backend:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        return ordered[0] if budget_pressure > 2.0 else ordered[-1]


def summarize_policy_run(policy_name: str, results: list[WorkflowResult]) -> PolicyRunSummary:
    return PolicyRunSummary(
        policy_name=policy_name,
        resolved_count=sum(1 for result in results if result.resolved),
        total_cost=sum(result.total_cost for result in results),
        workflow_results=tuple(results),
    )

from __future__ import annotations

from dataclasses import dataclass

from .loop import MinimalAgentLoop, WorkflowResult, WorkflowSpec
from .model_tiers import ModelCatalog
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
            return ModelCatalog.strongest(ordered)
        if budget_pressure <= 0.45:
            if average_w_i >= 2.1:
                return ModelCatalog.strongest(ordered)
            return ModelCatalog.second_cheapest(ordered)
        if average_w_i >= 2.4:
            return ModelCatalog.second_cheapest(ordered)
        return ModelCatalog.cheapest(ordered)


class BudgetOnlyStepRouter:
    def choose_backend(self, turn_info: TurnInfo, backends: list[Backend], budget_pressure: float) -> RouterDecision:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        n = len(ordered)
        if n <= 1:
            return RouterDecision(
                backend=ModelCatalog.cheapest(ordered), reason="single_backend", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if budget_pressure >= 1.2:
            return RouterDecision(
                backend=ModelCatalog.cheapest(ordered), reason=f"high_pressure={budget_pressure:.3f}", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if n == 2:
            # When budget is mostly unspent, allow the strongest tier to handle
            # tasks the cheaper tier cannot solve.
            if budget_pressure < 0.15:
                return RouterDecision(
                    backend=ModelCatalog.strongest(ordered), reason=f"very_low_pressure={budget_pressure:.3f}_strongest", scores={},
                    pressure=budget_pressure, branch="budget_only",
                )
            return RouterDecision(
                backend=ModelCatalog.cheapest(ordered), reason="cheapest_baseline_n2", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if budget_pressure >= 0.7:
            return RouterDecision(
                backend=ModelCatalog.cheapest(ordered), reason=f"moderate_pressure={budget_pressure:.3f}", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        # When budget is mostly unspent, allow strongest-tier rescue.
        if n >= 3 and budget_pressure < 0.15:
            return RouterDecision(
                backend=ModelCatalog.strongest(ordered), reason=f"very_low_pressure={budget_pressure:.3f}_strongest", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        if budget_pressure >= 0.35:
            return RouterDecision(
                backend=ModelCatalog.second_cheapest(ordered), reason=f"low_pressure={budget_pressure:.3f}_second_cheapest", scores={},
                pressure=budget_pressure, branch="budget_only",
            )
        return RouterDecision(
            backend=ModelCatalog.second_cheapest(ordered), reason=f"very_low_pressure={budget_pressure:.3f}_second_cheapest", scores={},
            pressure=budget_pressure, branch="budget_only",
        )


class BudgetOnlyT2Router:
    """True cost-only baseline: always picks the cheapest available tier.

    Unlike BudgetOnlyStepRouter, this never escalates regardless of budget
    pressure. This is the correct "dumb" baseline for cost-efficiency comparison:
    any strategy using stronger tiers must justify the extra cost with better
    outcomes.
    """
    def choose_backend(self, turn_info: TurnInfo, backends: list[Backend], budget_pressure: float) -> RouterDecision:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        return RouterDecision(
            backend=ModelCatalog.cheapest(ordered), reason="cheapest_only_baseline", scores={},
            pressure=budget_pressure, branch="budget_only_t2",
        )


def summarize_policy_run(policy_name: str, results: list[WorkflowResult]) -> PolicyRunSummary:
    return PolicyRunSummary(
        policy_name=policy_name,
        resolved_count=sum(1 for result in results if result.resolved),
        total_cost=sum(result.total_cost for result in results),
        workflow_results=tuple(results),
    )

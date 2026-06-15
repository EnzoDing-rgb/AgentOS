from __future__ import annotations

from .governor import BudgetGovernor
from .ledger import WorkflowLedgerStore
from .loop import WorkflowSpec, build_default_loop
from .policies import BudgetOnlyStepRouter, PolicyRunSummary, WorkflowLevelRouter, summarize_policy_run
from .types import Backend, GovernorConfig, TurnInfo


class ComparisonRunner:
    def __init__(self, backends: list[Backend], total_budget: float, default_max_output_tokens: int) -> None:
        self.backends = backends
        self.total_budget = total_budget
        self.default_max_output_tokens = default_max_output_tokens

    def run_budgetflow_segment(self, workflows: list[WorkflowSpec], budget_pressure: float) -> PolicyRunSummary:
        ledger = WorkflowLedgerStore()
        governor = BudgetGovernor(
            GovernorConfig(total_budget=self.total_budget, default_max_output_tokens=self.default_max_output_tokens),
            ledger,
        )
        loop = build_default_loop(self.backends, governor, ledger, budget_pressure=budget_pressure)
        results = [loop.run_workflow(workflow) for workflow in workflows]
        return summarize_policy_run("budgetflow_segment", results)

    def run_workflow_level_router(self, workflows: list[WorkflowSpec], budget_pressure: float) -> PolicyRunSummary:
        router = WorkflowLevelRouter()
        chosen_by_workflow = {
            workflow.workflow_id: router.choose_backend(
                sum(step.w_i for step in workflow.steps) / len(workflow.steps),
                self.backends,
                budget_pressure,
            )
            for workflow in workflows
        }

        def backend_picker(turn: TurnInfo, backends: list[Backend], *_args) -> Backend:
            return chosen_by_workflow[turn.workflow_id]

        ledger = WorkflowLedgerStore()
        governor = BudgetGovernor(
            GovernorConfig(total_budget=self.total_budget, default_max_output_tokens=self.default_max_output_tokens),
            ledger,
        )
        loop = build_default_loop(self.backends, governor, ledger, budget_pressure=budget_pressure, backend_picker=backend_picker)
        results = [loop.run_workflow(workflow) for workflow in workflows]
        return summarize_policy_run("workflow_level_router", results)

    def run_budget_only_step_router(self, workflows: list[WorkflowSpec], budget_pressure: float) -> PolicyRunSummary:
        router = BudgetOnlyStepRouter()

        def backend_picker(turn: TurnInfo, backends: list[Backend], *_args) -> Backend:
            return router.choose_backend(turn, backends, budget_pressure=budget_pressure).backend

        ledger = WorkflowLedgerStore()
        governor = BudgetGovernor(
            GovernorConfig(total_budget=self.total_budget, default_max_output_tokens=self.default_max_output_tokens),
            ledger,
        )
        loop = build_default_loop(self.backends, governor, ledger, budget_pressure=budget_pressure, backend_picker=backend_picker)
        results = [loop.run_workflow(workflow) for workflow in workflows]
        return summarize_policy_run("budget_only_step_router", results)

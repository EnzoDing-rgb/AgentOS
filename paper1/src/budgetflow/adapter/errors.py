from __future__ import annotations


class BudgetFlowBudgetError(RuntimeError):
    """Raised when governor cannot reserve budget for the next LLM call."""

    def __init__(
        self,
        workflow_id: str,
        *,
        exit_reason: str = "budget_exhausted",
        budget_snapshot: dict[str, float] | None = None,
        step_index: int = 0,
        backend: str | None = None,
    ) -> None:
        self.workflow_id = workflow_id
        self.exit_reason = exit_reason
        self.budget_snapshot = budget_snapshot or {}
        self.step_index = step_index
        self.backend = backend
        detail = (
            f"{exit_reason} workflow={workflow_id} step={step_index} "
            f"budget={self.budget_snapshot}"
        )
        super().__init__(detail)

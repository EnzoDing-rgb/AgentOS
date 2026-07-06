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


class BudgetFlowStagnationError(RuntimeError):
    """Raised when the agent loops without material progress (repeat cmds or read-only streak)."""

    def __init__(
        self,
        workflow_id: str,
        *,
        exit_reason: str = "stagnation_no_progress",
        step_index: int = 0,
        repeat_command: str | None = None,
        no_progress_streak: int = 0,
    ) -> None:
        self.workflow_id = workflow_id
        self.exit_reason = exit_reason
        self.step_index = step_index
        self.repeat_command = repeat_command
        self.no_progress_streak = no_progress_streak
        detail = (
            f"{exit_reason} workflow={workflow_id} step={step_index} "
            f"streak={no_progress_streak} repeat={repeat_command!r}"
        )
        super().__init__(detail)


class BudgetFlowUpstreamError(RuntimeError):
    """Raised when consecutive upstream/provider errors suggest infra misconfiguration."""

    def __init__(
        self,
        workflow_id: str,
        *,
        exit_reason: str = "upstream_guard",
        step_index: int = 0,
        backend: str | None = None,
        sample: str = "",
    ) -> None:
        self.workflow_id = workflow_id
        self.exit_reason = exit_reason
        self.step_index = step_index
        self.backend = backend
        self.sample = sample[:200]
        detail = f"{exit_reason} workflow={workflow_id} step={step_index} backend={backend} {self.sample}"
        super().__init__(detail)

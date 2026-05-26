from __future__ import annotations

from dataclasses import dataclass

from .governor import BudgetGovernor
from .ledger import WorkflowLedgerStore
from .lite_tasks import LiteTaskRecord, summarize_repair_error
from .local_harness import clone_or_checkout, evaluate_local_harness
from .react_loop import DEFAULT_TOTAL_BUDGET, MAX_TURNS_MONOLITHIC, run_monolithic_react
from .repair_workspace import failure_class
from .staged_react_agent import ReActRunResult
from .types import GovernorConfig


def run_monolithic_react_agent(
    task: LiteTaskRecord,
    strategy: str = "monolithic_react_budgetflow",
    total_budget: float = DEFAULT_TOTAL_BUDGET,
) -> ReActRunResult:
    repo_dir = clone_or_checkout(task)
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=total_budget, default_max_output_tokens=4096), ledger)
    harness_state = {"resolved": False, "detail": ""}

    def on_submit(patch_text: str) -> tuple[bool, str]:
        harness = evaluate_local_harness(task, patch_text)
        harness_state["resolved"] = harness.harness_resolved
        harness_state["detail"] = harness.detail
        return harness.harness_resolved, summarize_repair_error(harness.detail)

    result = run_monolithic_react(
        task=task,
        repo_dir=repo_dir,
        strategy=strategy,
        governor=governor,
        ledger=ledger,
        max_turns=MAX_TURNS_MONOLITHIC,
        on_submit=on_submit,
    )

    last_failure = "resolved" if harness_state["resolved"] else failure_class(harness_state["detail"] or result.stop_reason)

    return ReActRunResult(
        instance_id=task.instance_id,
        strategy=strategy,
        model_patch=result.patch_text,
        patch_extracted=result.patch_text is not None,
        harness_resolved=harness_state["resolved"],
        total_cost=result.total_cost,
        backend_picks=tuple(result.backend_picks),
        localization_text="",
        llm_turns=result.llm_turns,
        tool_calls=result.tool_calls,
        stop_reason=result.stop_reason,
        last_failure_class=last_failure,
    )

from __future__ import annotations

from dataclasses import dataclass

from .governor import BudgetGovernor
from .ledger import WorkflowLedgerStore
from .lite_tasks import (
    LiteTaskRecord,
    build_react_issue_prompt,
    build_react_system_prompt,
    format_tool_schema,
    summarize_repair_error,
)
from .local_harness import clone_or_checkout, evaluate_local_harness
from .react_loop import DEFAULT_TOTAL_BUDGET, MAX_TURNS_L, MAX_TURNS_R, run_react_stage
from .repair_workspace import failure_class
from .tool_sandbox import tool_schemas
from .types import GovernorConfig, Stage


@dataclass(frozen=True)
class ReActRunResult:
    instance_id: str
    strategy: str
    model_patch: str | None
    patch_extracted: bool
    harness_resolved: bool
    total_cost: float
    backend_picks: tuple[str, ...]
    localization_text: str
    llm_turns: int
    tool_calls: int
    stop_reason: str
    last_failure_class: str


def run_staged_react_agent(
    task: LiteTaskRecord,
    strategy: str = "budgetflow_staged_react",
    total_budget: float = DEFAULT_TOTAL_BUDGET,
) -> ReActRunResult:
    repo_dir = clone_or_checkout(task)
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=total_budget, default_max_output_tokens=4096), ledger)

    loc = run_react_stage(
        task=task,
        repo_dir=repo_dir,
        stage=Stage.LOCALIZATION,
        strategy=strategy,
        governor=governor,
        ledger=ledger,
        max_turns=MAX_TURNS_L,
        w_i=1.0,
        allow_finish_localization=True,
    )

    repo_dir = clone_or_checkout(task)
    harness_state = {"resolved": False, "detail": ""}

    def on_submit(patch_text: str) -> tuple[bool, str]:
        harness = evaluate_local_harness(task, patch_text)
        harness_state["resolved"] = harness.harness_resolved
        harness_state["detail"] = harness.detail
        return harness.harness_resolved, summarize_repair_error(harness.detail)

    schema_text = format_tool_schema(tool_schemas(Stage.REPAIR))
    repair_messages = [
        {"role": "system", "content": build_react_system_prompt(Stage.REPAIR, schema_text)},
        {
            "role": "user",
            "content": build_react_issue_prompt(
                task,
                extra=f"Localization summary:\n{loc.summary[:1200]}",
            ),
        },
    ]

    repair = run_react_stage(
        task=task,
        repo_dir=repo_dir,
        stage=Stage.REPAIR,
        strategy=strategy,
        governor=governor,
        ledger=ledger,
        max_turns=MAX_TURNS_R,
        w_i=3.0,
        allow_finish_localization=False,
        on_submit=on_submit,
        initial_messages=repair_messages,
    )

    total_cost = loc.total_cost + repair.total_cost
    patch = repair.patch_text
    picks = tuple(loc.backend_picks + repair.backend_picks)
    last_failure = "resolved" if harness_state["resolved"] else failure_class(harness_state["detail"] or repair.stop_reason)

    return ReActRunResult(
        instance_id=task.instance_id,
        strategy=strategy,
        model_patch=patch,
        patch_extracted=patch is not None,
        harness_resolved=harness_state["resolved"],
        total_cost=total_cost,
        backend_picks=picks,
        localization_text=loc.summary,
        llm_turns=loc.llm_turns + repair.llm_turns,
        tool_calls=loc.tool_calls + repair.tool_calls,
        stop_reason=repair.stop_reason,
        last_failure_class=last_failure,
    )

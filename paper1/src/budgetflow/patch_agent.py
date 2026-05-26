from __future__ import annotations

from dataclasses import dataclass

from .deepseek_backend import DeepSeekBackend
from .governor import BudgetGovernor
from .ledger import WorkflowLedgerStore
from .lite_tasks import (
    LiteTaskRecord,
    build_lite_stage_prompt,
    build_repair_patch_prompt,
    build_repair_retry_prompt,
)
from .local_harness import clone_or_checkout, evaluate_local_harness
from .loop import WorkflowSpec, WorkflowStep, build_default_loop
from .repo_context import build_repair_file_context
from .repair_workspace import apply_repair_edits, export_workspace_patch, parse_repair_edits
from .run_deepseek_compare import FROZEN_BUDGET_PRESSURE, build_backends, fixed_backend_picker
from .selector import build_deepseek_progress_table
from .types import Backend, GovernorConfig, Stage, TurnInfo

# Frozen — not tuned on eval tasks.
MAX_REPAIR_ATTEMPTS = 5


@dataclass(frozen=True)
class PatchRunResult:
    instance_id: str
    strategy: str
    workflow_steps_ok: bool
    model_patch: str | None
    patch_extracted: bool
    total_cost: float
    backend_picks: tuple[str, ...]
    localization_text: str
    repair_text: str
    repair_attempts: int
    harness_resolved: bool


def _strategy_kwargs(strategy: str, backends: list[Backend]) -> dict:
    kwargs: dict = {}
    if strategy == "all_flash":
        kwargs["backend_picker"] = fixed_backend_picker("deepseek_flash")
    elif strategy == "all_pro":
        kwargs["backend_picker"] = fixed_backend_picker("deepseek_pro")
    elif strategy == "budgetflow_full":
        kwargs["progress_table"] = build_deepseek_progress_table(backends)
    else:
        raise ValueError(f"unknown strategy: {strategy}")
    return kwargs


def _build_clients(
    backends: list[Backend],
    task: LiteTaskRecord,
    localization_text: str,
    file_context: str,
    repair_feedback: dict,
):
    def prompt_builder(turn: TurnInfo, input_tokens: int) -> str:
        if turn.stage is Stage.LOCALIZATION:
            return build_lite_stage_prompt(task, turn.stage)
        attempt = repair_feedback.get("attempt", 1)
        error = repair_feedback.get("error", "")
        previous_patch = repair_feedback.get("previous_patch", "")
        if attempt > 1 and (error or previous_patch):
            return build_repair_retry_prompt(
                task,
                localization_text,
                file_context,
                previous_patch,
                error,
                attempt,
            )
        return build_repair_patch_prompt(task, localization_text, file_context)

    repair_max_tokens = {Stage.REPAIR: 4096}
    repair_no_thinking = {Stage.REPAIR: False}
    return {
        "deepseek_flash": DeepSeekBackend(
            backends[0],
            model_name="deepseek-v4-flash",
            enable_thinking=False,
            prompt_builder=prompt_builder,
            stage_max_tokens=repair_max_tokens,
            stage_enable_thinking=repair_no_thinking,
        ),
        "deepseek_pro": DeepSeekBackend(
            backends[1],
            model_name="deepseek-v4-pro",
            enable_thinking=True,
            reasoning_effort="high",
            prompt_builder=prompt_builder,
            stage_max_tokens=repair_max_tokens,
            stage_enable_thinking=repair_no_thinking,
        ),
    }


def _run_stage(
    task: LiteTaskRecord,
    stage: Stage,
    strategy: str,
    backends: list[Backend],
    clients: dict,
    input_tokens: int,
    w_i: float,
) -> tuple[str, str, float]:
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=50.0, default_max_output_tokens=2048), ledger)

    def runner(backend: Backend, turn: TurnInfo, tokens: int):
        return clients[backend.name].run(turn, tokens)

    kwargs = {"budget_pressure": FROZEN_BUDGET_PRESSURE, "backend_runner": runner, **_strategy_kwargs(strategy, backends)}
    loop = build_default_loop(backends, governor, ledger, **kwargs)
    spec = WorkflowSpec(
        workflow_id=task.instance_id,
        steps=(WorkflowStep(stage=stage, input_tokens=input_tokens, w_i=w_i),),
    )
    result = loop.run_workflow(spec)
    trace = result.traces[0]
    return trace.chosen_backend, trace.response_text, result.total_cost


def run_patch_agent(
    task: LiteTaskRecord,
    strategy: str,
    budget_pressure: float = FROZEN_BUDGET_PRESSURE,
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> PatchRunResult:
    del budget_pressure  # frozen constant used in _run_stage
    backends = build_backends()
    loc_step = task.workflow.steps[0]
    repair_step = task.workflow.steps[1]

    repair_feedback: dict = {"attempt": 1, "error": "", "previous_patch": ""}
    clients = _build_clients(backends, task, "", "", repair_feedback)

    loc_backend, localization_text, total_cost = _run_stage(
        task,
        Stage.LOCALIZATION,
        strategy,
        backends,
        clients,
        loc_step.input_tokens,
        loc_step.w_i,
    )
    picks: list[str] = [loc_backend]

    file_context, _paths = build_repair_file_context(task, localization_text)
    clients = _build_clients(backends, task, localization_text, file_context, repair_feedback)

    best_patch: str | None = None
    last_repair_text = ""
    resolved = False
    attempts_used = 0

    for attempt in range(1, max_repair_attempts + 1):
        attempts_used = attempt
        repair_feedback["attempt"] = attempt
        repair_backend, repair_text, repair_cost = _run_stage(
            task,
            Stage.REPAIR,
            strategy,
            backends,
            clients,
            repair_step.input_tokens,
            repair_step.w_i,
        )
        picks.append(repair_backend)
        total_cost += repair_cost
        last_repair_text = repair_text
        edits, edit_error = parse_repair_edits(repair_text)
        if edits is None:
            repair_feedback["error"] = edit_error or "invalid repair edits"
            repair_feedback["previous_patch"] = repair_text[:1500]
            continue

        repo_dir = clone_or_checkout(task)
        ok, apply_error = apply_repair_edits(repo_dir, edits)
        if not ok:
            repair_feedback["error"] = apply_error or "failed to apply repair edits"
            repair_feedback["previous_patch"] = repair_text[:1500]
            continue

        workspace_patch = export_workspace_patch(repo_dir)
        if workspace_patch.patch_text is None:
            repair_feedback["error"] = workspace_patch.error or "git diff produced no patch"
            repair_feedback["previous_patch"] = repair_text[:1500]
            continue

        model_patch = workspace_patch.patch_text
        harness = evaluate_local_harness(task, model_patch)
        best_patch = model_patch
        if harness.harness_resolved:
            resolved = True
            break
        repair_feedback["error"] = harness.detail
        repair_feedback["previous_patch"] = repair_text[:1500]

    return PatchRunResult(
        instance_id=task.instance_id,
        strategy=strategy,
        workflow_steps_ok=best_patch is not None,
        model_patch=best_patch,
        patch_extracted=best_patch is not None,
        total_cost=total_cost,
        backend_picks=tuple(picks),
        localization_text=localization_text,
        repair_text=last_repair_text,
        repair_attempts=attempts_used,
        harness_resolved=resolved,
    )

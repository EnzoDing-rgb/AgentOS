from __future__ import annotations

from dataclasses import dataclass

from .deepseek_backend import DeepSeekBackend
from .governor import BudgetGovernor
from .ledger import WorkflowLedgerStore
from .lite_tasks import LiteTaskRecord, build_lite_stage_prompt, build_repair_patch_prompt
from .loop import WorkflowResult, build_default_loop
from .patch_utils import normalize_model_patch
from .run_deepseek_compare import FROZEN_BUDGET_PRESSURE, build_backends, fixed_backend_picker
from .selector import build_deepseek_progress_table
from .types import Backend, GovernorConfig, Stage, TurnInfo


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


def build_patch_runner(
    backends: list[Backend],
    task: LiteTaskRecord,
    stage_texts: dict[tuple[int, Stage], str],
):
    def prompt_builder(turn: TurnInfo, input_tokens: int) -> str:
        if turn.stage is Stage.REPAIR:
            loc = stage_texts.get((1, Stage.LOCALIZATION), "")
            return build_repair_patch_prompt(task, loc)
        return build_lite_stage_prompt(task, turn.stage)

    repair_max_tokens = {Stage.REPAIR: 2048}
    repair_no_thinking = {Stage.REPAIR: False}
    clients = {
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

    def runner(backend: Backend, turn: TurnInfo, input_tokens: int):
        result = clients[backend.name].run(turn, input_tokens)
        stage_texts[(turn.step_index, turn.stage)] = result.response_text
        return result

    return runner


def run_patch_agent(task: LiteTaskRecord, strategy: str, budget_pressure: float = FROZEN_BUDGET_PRESSURE) -> PatchRunResult:
    backends = build_backends()
    stage_texts: dict[tuple[int, Stage], str] = {}
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=20.0, default_max_output_tokens=2048), ledger)
    runner = build_patch_runner(backends, task, stage_texts)

    kwargs: dict = {
        "budget_pressure": budget_pressure,
        "backend_runner": runner,
    }
    if strategy == "all_flash":
        kwargs["backend_picker"] = fixed_backend_picker("deepseek_flash")
    elif strategy == "all_pro":
        kwargs["backend_picker"] = fixed_backend_picker("deepseek_pro")
    elif strategy == "budgetflow_full":
        kwargs["progress_table"] = build_deepseek_progress_table(backends)
    else:
        raise ValueError(f"unknown strategy: {strategy}")

    loop = build_default_loop(backends, governor, ledger, **kwargs)
    result: WorkflowResult = loop.run_workflow(task.workflow)
    picks = tuple(trace.chosen_backend for trace in result.traces)
    localization_text = ""
    repair_text = ""
    for trace in result.traces:
        if trace.stage is Stage.LOCALIZATION:
            localization_text = trace.response_text
        if trace.stage is Stage.REPAIR:
            repair_text = trace.response_text
    model_patch = normalize_model_patch(repair_text)
    return PatchRunResult(
        instance_id=task.instance_id,
        strategy=strategy,
        workflow_steps_ok=result.resolved,
        model_patch=model_patch,
        patch_extracted=model_patch is not None,
        total_cost=result.total_cost,
        backend_picks=picks,
        localization_text=localization_text,
        repair_text=repair_text,
    )

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .deepseek_backend import DeepSeekBackend, evaluate_react_progress
from .governor import BudgetGovernor
from .ledger import WorkflowLedgerStore
from .lite_tasks import LiteTaskRecord, build_react_issue_prompt, build_react_system_prompt, format_tool_schema
from .loop import WorkflowSpec, WorkflowStep, build_default_loop
from .run_deepseek_compare import FROZEN_BUDGET_PRESSURE, build_backends
from .selector import build_deepseek_progress_table
from .stage_classifier import classify_stage
from .tool_sandbox import ToolResult, execute_tool, parse_tool_action, tool_schemas
from .types import Backend, BackendCallResult, GovernorConfig, Stage, TurnInfo, WorkflowStatus


DEFAULT_TOTAL_BUDGET = 50.0
MAX_TURNS_L = 12
MAX_TURNS_R = 20
MAX_TURNS_MONOLITHIC = 32


@dataclass
class ReActStageResult:
    stage: Stage
    summary: str
    patch_text: str | None
    total_cost: float
    backend_picks: list[str] = field(default_factory=list)
    llm_turns: int = 0
    tool_calls: int = 0
    stop_reason: str = "unknown"
    messages: list[dict[str, str]] = field(default_factory=list)


def _estimate_input_tokens(messages: list[dict[str, str]]) -> int:
    text = "\n".join(m["content"] for m in messages)
    return max(60, len(text.split()) * 4 // 3)


def _strategy_kwargs(strategy: str, backends: list[Backend]) -> dict:
    from .run_deepseek_compare import fixed_backend_picker
    from .selector import build_deepseek_progress_table

    if strategy == "all_flash":
        return {"backend_picker": fixed_backend_picker("deepseek_flash")}
    if strategy == "all_pro":
        return {"backend_picker": fixed_backend_picker("deepseek_pro")}
    if strategy in {"budgetflow_full", "monolithic_react_budgetflow", "budgetflow_staged_react"}:
        return {"progress_table": build_deepseek_progress_table(backends)}
    if strategy == "monolithic_react_all_pro":
        return {"backend_picker": fixed_backend_picker("deepseek_pro")}
    raise ValueError(f"unknown strategy: {strategy}")


def _run_budgeted_chat(
    *,
    task: LiteTaskRecord,
    stage: Stage,
    w_i: float,
    step_index: int,
    messages: list[dict[str, str]],
    strategy: str,
    clients: dict[str, DeepSeekBackend],
    governor: BudgetGovernor,
    ledger: WorkflowLedgerStore,
    backends: list[Backend],
) -> tuple[BackendCallResult | None, str | None, float]:
    input_tokens = _estimate_input_tokens(messages)
    turn = TurnInfo(
        workflow_id=task.instance_id,
        step_index=step_index,
        stage=stage,
        w_i=w_i,
        context_len=input_tokens,
    )

    def runner(backend: Backend, turn_info: TurnInfo, tokens: int) -> BackendCallResult:
        del tokens
        return clients[backend.name].complete_chat(messages, stage)

    loop = build_default_loop(
        backends,
        governor,
        ledger,
        budget_pressure=FROZEN_BUDGET_PRESSURE,
        backend_runner=runner,
        **_strategy_kwargs(strategy, backends),
    )
    spec = WorkflowSpec(
        workflow_id=task.instance_id,
        steps=(WorkflowStep(stage=stage, input_tokens=input_tokens, w_i=w_i),),
    )
    result = loop.run_workflow(spec)
    if not result.traces:
        return None, "budget_reject", 0.0
    trace = result.traces[0]
    if trace.status != WorkflowStatus.COMPLETED.value:
        return None, trace.status, 0.0
    return BackendCallResult(
        backend_name=trace.chosen_backend,
        input_tokens=input_tokens,
        output_tokens=0,
        progress_made=trace.progress_made,
        latency_ms=0,
        response_text=trace.response_text,
    ), trace.chosen_backend, result.total_cost


def run_react_stage(
    *,
    task: LiteTaskRecord,
    repo_dir,
    stage: Stage,
    strategy: str,
    governor: BudgetGovernor,
    ledger: WorkflowLedgerStore,
    initial_messages: list[dict[str, str]] | None = None,
    max_turns: int,
    w_i: float,
    allow_finish_localization: bool = False,
    on_submit: Callable[[str], tuple[bool, str]] | None = None,
) -> ReActStageResult:
    backends = build_backends()
    clients = {
        "deepseek_flash": DeepSeekBackend(
            backends[0],
            model_name="deepseek-v4-flash",
            enable_thinking=False,
            stage_max_tokens={Stage.LOCALIZATION: 2048, Stage.REPAIR: 4096},
            stage_enable_thinking={Stage.REPAIR: False},
        ),
        "deepseek_pro": DeepSeekBackend(
            backends[1],
            model_name="deepseek-v4-pro",
            enable_thinking=True,
            reasoning_effort="high",
            stage_max_tokens={Stage.LOCALIZATION: 2048, Stage.REPAIR: 4096},
            stage_enable_thinking={Stage.REPAIR: False},
        ),
    }

    schema_text = format_tool_schema(tool_schemas(stage))
    messages: list[dict[str, str]] = list(initial_messages or [])
    if not messages:
        messages = [
            {"role": "system", "content": build_react_system_prompt(stage, schema_text)},
            {"role": "user", "content": build_react_issue_prompt(task)},
        ]

    total_cost = 0.0
    backend_picks: list[str] = []
    llm_turns = 0
    tool_calls = 0
    patch_text: str | None = None
    summary = ""
    stop_reason = "max_turns"

    for turn_index in range(1, max_turns + 1):
        if governor.state.available_budget <= 0:
            stop_reason = "budget_exhausted"
            break

        llm_turns += 1
        call, backend_name, turn_cost = _run_budgeted_chat(
            task=task,
            stage=stage,
            w_i=w_i,
            step_index=turn_index,
            messages=messages,
            strategy=strategy,
            clients=clients,
            governor=governor,
            ledger=ledger,
            backends=backends,
        )
        if call is None or backend_name is None:
            stop_reason = backend_name or "budget_reject"
            break
        total_cost += turn_cost
        backend_picks.append(backend_name)
        assistant_text = call.response_text.strip()
        messages.append({"role": "assistant", "content": assistant_text})

        action, args, parse_err = parse_tool_action(assistant_text)
        if parse_err is not None:
            messages.append({"role": "user", "content": f"Observation: parse error — {parse_err}. Emit one valid JSON action."})
            continue

        assert action is not None
        assert args is not None

        if allow_finish_localization and action == "finish_localization":
            summary = str(args.get("summary", "")).strip() or assistant_text
            stop_reason = "finish_localization"
            break

        tool_result: ToolResult
        if action == "submit_patch":
            tool_result = execute_tool(repo_dir, stage, action, args)
            tool_calls += 1
            if tool_result.ok:
                patch_text = tool_result.output
                stop_reason = "submit_patch"
                if on_submit is not None:
                    ok, detail = on_submit(patch_text)
                    if ok:
                        break
                    messages.append({"role": "user", "content": f"Observation: harness failed — {detail}\nContinue repairing and submit_patch again."})
                    patch_text = None
                    stop_reason = "harness_retry"
                    continue
                break
            messages.append({"role": "user", "content": f"Observation: {tool_result.error or tool_result.output}"})
            continue

        tool_result = execute_tool(repo_dir, stage, action, args)
        tool_calls += 1
        obs = tool_result.output if tool_result.ok else (tool_result.error or "tool failed")
        messages.append({"role": "user", "content": f"Observation:\n{obs}"})

        classify_stage(action, obs)
        evaluate_react_progress(stage, action, tool_result.ok)

    if not summary and messages:
        summary = messages[-1]["content"][:2000]

    return ReActStageResult(
        stage=stage,
        summary=summary,
        patch_text=patch_text,
        total_cost=total_cost,
        backend_picks=backend_picks,
        llm_turns=llm_turns,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        messages=messages,
    )


def run_monolithic_react(
    *,
    task: LiteTaskRecord,
    repo_dir,
    strategy: str,
    governor: BudgetGovernor,
    ledger: WorkflowLedgerStore,
    max_turns: int = MAX_TURNS_MONOLITHIC,
    on_submit: Callable[[str], tuple[bool, str]] | None = None,
) -> ReActStageResult:
    from .lite_tasks import build_react_monolithic_system_prompt

    backends = build_backends()
    clients = {
        "deepseek_flash": DeepSeekBackend(
            backends[0],
            model_name="deepseek-v4-flash",
            enable_thinking=False,
            stage_max_tokens={Stage.LOCALIZATION: 2048, Stage.REPAIR: 4096},
        ),
        "deepseek_pro": DeepSeekBackend(
            backends[1],
            model_name="deepseek-v4-pro",
            enable_thinking=True,
            reasoning_effort="high",
            stage_max_tokens={Stage.LOCALIZATION: 2048, Stage.REPAIR: 4096},
            stage_enable_thinking={Stage.REPAIR: False},
        ),
    }

    all_tools = tool_schemas(Stage.REPAIR)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_react_monolithic_system_prompt(format_tool_schema(all_tools))},
        {"role": "user", "content": build_react_issue_prompt(task)},
    ]

    total_cost = 0.0
    backend_picks: list[str] = []
    llm_turns = 0
    tool_calls = 0
    patch_text: str | None = None
    stop_reason = "max_turns"

    for turn_index in range(1, max_turns + 1):
        if governor.state.available_budget <= 0:
            stop_reason = "budget_exhausted"
            break

        stage = Stage.REPAIR if patch_text or turn_index > 3 else Stage.LOCALIZATION
        w_i = 3.0 if stage is Stage.REPAIR else 1.0
        llm_turns += 1
        call, backend_name, turn_cost = _run_budgeted_chat(
            task=task,
            stage=stage,
            w_i=w_i,
            step_index=turn_index,
            messages=messages,
            strategy=strategy,
            clients=clients,
            governor=governor,
            ledger=ledger,
            backends=backends,
        )
        if call is None or backend_name is None:
            stop_reason = backend_name or "budget_reject"
            break
        total_cost += turn_cost
        backend_picks.append(backend_name)
        assistant_text = call.response_text.strip()
        messages.append({"role": "assistant", "content": assistant_text})

        action, args, parse_err = parse_tool_action(assistant_text)
        if parse_err is not None:
            messages.append({"role": "user", "content": f"Observation: parse error — {parse_err}"})
            continue
        assert action is not None and args is not None

        inferred = classify_stage(action)
        stage = inferred

        if action == "submit_patch":
            tool_result = execute_tool(repo_dir, stage, action, args)
            tool_calls += 1
            if tool_result.ok:
                patch_text = tool_result.output
                stop_reason = "submit_patch"
                if on_submit is not None:
                    ok, detail = on_submit(patch_text)
                    if ok:
                        break
                    messages.append({"role": "user", "content": f"Observation: harness failed — {detail}"})
                    patch_text = None
                    continue
                break
            messages.append({"role": "user", "content": f"Observation: {tool_result.error or tool_result.output}"})
            continue

        tool_result = execute_tool(repo_dir, stage, action, args)
        tool_calls += 1
        obs = tool_result.output if tool_result.ok else (tool_result.error or "tool failed")
        messages.append({"role": "user", "content": f"Observation:\n{obs}"})

    return ReActStageResult(
        stage=Stage.REPAIR,
        summary="",
        patch_text=patch_text,
        total_cost=total_cost,
        backend_picks=backend_picks,
        llm_turns=llm_turns,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        messages=messages,
    )

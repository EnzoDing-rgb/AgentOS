from __future__ import annotations

import sys
import time
import os
from dataclasses import dataclass
from pathlib import Path

from ..runtime import get_trace_dir, resolve_mini_swe_src

# Resolve mini-swe-agent source dir before importing from it.
MINI_SWE_SRC = resolve_mini_swe_src()
if str(MINI_SWE_SRC) not in sys.path:
    sys.path.insert(0, str(MINI_SWE_SRC))

from minisweagent.config import get_config_from_spec  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.exceptions import Submitted  # noqa: E402
from minisweagent.utils.serialize import recursive_merge  # noqa: E402

from ..console_log import tag
from ..governor import BudgetGovernor, GovernorConfig
from ..heartbeat import run_with_heartbeat
from ..ledger import WorkflowLedgerStore
from ..lite_tasks import LiteTaskRecord
from ..local_harness import clone_or_checkout, evaluate_local_harness
from ..harness_contamination import (
    find_runtime_worktree_python_contamination,
    format_runtime_worktree_contamination,
)
from ..observability import parse_harness_evidence
from ..run_trace import (
    RunTraceLogger,
    TracedDefaultAgent,
    TraceConsoleLevel,
    patch_local_swebench_config,
)
from .backends import build_backends_for_strategy
from .errors import BudgetFlowBudgetError, BudgetFlowStagnationError, BudgetFlowUpstreamError
from .mini_swe_proxy import BudgetFlowLitellmModel
from ..adaptive_routing import AdaptiveRoutingState
from ..frozen_router import FrozenRouterPlan
from ..allocation import AllocationContext
from .strategies import build_routing_context
from ..runtime import resolve_runtime_root

# Config paths derived from resolved mini-swe-agent src.
_SWE_AGENT_BASE = MINI_SWE_SRC.parent  # external/mini-swe-agent/
SWEBENCH_CONFIG = MINI_SWE_SRC / "minisweagent" / "config" / "benchmarks" / "swebench.yaml"

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNS_DIR = REPO_ROOT / "paper1" / "data" / "runs"


@dataclass(frozen=True)
class MiniSweRunResult:
    instance_id: str
    strategy: str
    strategy_label: str
    patch_text: str | None
    exit_status: str
    exit_reason: str | None
    agent_exit_status: str
    agent_exit_reason: str | None
    total_cost: float
    budget_cap: float
    budget_snapshot: dict[str, float]
    backend_picks: tuple[str, ...]
    llm_turns: int
    harness_resolved: bool
    harness_detail: str
    agent_gold_edited: bool
    agent_attempted_submit: bool
    agent_submitted: bool
    agent_gold_files: tuple[str, ...]
    violations: tuple[str, ...]
    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    provider_usage_turns: int = 0
    estimated_usage_turns: int = 0
    cost_mode: str = ""
    usage_source: str = ""
    patch_source: str = "submission"
    submitted_patch_path: str | None = None
    turn_trace_count: int = 0
    turn_traces: list[dict] | None = None
    protocol_retry_used: bool = False
    protocol_retry_success: bool = False
    protocol_retry_reason: str = ""
    protocol_retry_attempts: int = 0
    protocol_retry_limit: int = 4
    protocol: str = ""
    parser: str = ""
    provider_error_kind: str = ""
    provider_retryable: bool | None = None


def _row_cost_observability(model: BudgetFlowLitellmModel, total_cost: float) -> tuple[str, str]:
    if model._estimated_usage_turns == 0 and model._provider_usage_turns > 0:
        return "provider", "catalog_provider_usage"
    if model._estimated_usage_turns > 0:
        return "estimated", "catalog_estimated_usage"
    if float(total_cost or 0.0) == 0.0:
        return "none", "no_provider_call"
    return "unknown", "cost_unattributed"


def _harness_exit_label(
    *,
    agent_exit_status: str,
    agent_exit_reason: str | None,
    harness_resolved: bool,
    patch_text: str | None,
    harness_detail: str,
) -> tuple[str, str | None]:
    if harness_resolved:
        return "HarnessResolved", "harness_resolved"
    if patch_text and parse_harness_evidence(harness_detail).evaluated_complete:
        return "HarnessFailed", "harness_failed"
    return agent_exit_status, agent_exit_reason


def _load_agent_config(*, step_limit: int = 250) -> dict:
    # Keep one action contract across all routed tiers. BudgetFlow experiments
    # should isolate model/routing decisions, not switch the mini-SWE protocol
    # when a policy escalates or downgrades between tiers.
    config_path = SWEBENCH_CONFIG
    config = recursive_merge(
        get_config_from_spec(config_path),
        {
            "agent": {
                "cost_limit": 0.0,
                "step_limit": step_limit,
                "confirm_exit": False,
            },
            "environment": {
                "timeout": 120,
            },
        },
    )
    return config


def run_mini_swe_task(
    task: LiteTaskRecord,
    *,
    strategy: str = "all_pro",
    strategy_label: str | None = None,
    budget_per_task: float | None = None,
    budget_pressure: float | None = None,
    pressure_max: float | None = None,
    step_limit: int = 250,
    trace_console: TraceConsoleLevel = "quiet",
    progress_box: dict[str, str] | None = None,
    agent_heartbeat: bool = True,
    governor: BudgetGovernor | None = None,
    ledger: WorkflowLedgerStore | None = None,
    workspace_key: str | None = None,
    adaptive: AdaptiveRoutingState | None = None,
    enable_turn_trace: bool = False,
    task_value: float = 1.0,
    median_task_value: float = 1.0,
    frozen_plan: FrozenRouterPlan | None = None,
    allocation: AllocationContext | None = None,
    run_series: str = "",
) -> MiniSweRunResult:
    label = strategy_label or strategy
    ledger = ledger or WorkflowLedgerStore()
    if governor is None:
        cap = budget_per_task if budget_per_task is not None else 1_000_000.0
        governor = BudgetGovernor(
            GovernorConfig(total_budget=cap, default_max_output_tokens=4096),
            ledger,
        )
    else:
        cap = governor.config.total_budget
    runtime_root, _ = resolve_runtime_root()
    contamination = find_runtime_worktree_python_contamination(runtime_root)
    if contamination:
        detail = (
            "host_dependency_contamination: runtime worktree paths in Python environment: "
            f"{format_runtime_worktree_contamination(contamination)}"
        )
        return MiniSweRunResult(
            instance_id=task.instance_id,
            strategy=strategy,
            strategy_label=label,
            patch_text=None,
            exit_status="infra_error",
            exit_reason="host_dependency_contamination",
            agent_exit_status="infra_error",
            agent_exit_reason="host_dependency_contamination",
            total_cost=0.0,
            budget_cap=cap,
            budget_snapshot=governor.budget_snapshot(),
            backend_picks=(),
            llm_turns=0,
            harness_resolved=False,
            harness_detail=detail,
            agent_gold_edited=False,
            agent_attempted_submit=False,
            agent_submitted=False,
            agent_gold_files=(),
            violations=(),
            cost_mode="no_provider_call",
            usage_source="none",
        )
    repo_dir = clone_or_checkout(task, workspace_key=workspace_key)
    trace_dir = get_trace_dir(task.instance_id, label, run_series=run_series)
    trace = RunTraceLogger(
        instance_id=task.instance_id,
        repo_dir=repo_dir,
        trace_dir=trace_dir,
        target_files=task.gold_files,
        strategy_label=label,
        console_level=trace_console,
        progress_box=progress_box,
    )
    config = patch_local_swebench_config(_load_agent_config(step_limit=step_limit), repo_dir)
    backends = build_backends_for_strategy(strategy)
    routing = build_routing_context(
        strategy,
        backends,
        budget_pressure=budget_pressure,
        pressure_max=pressure_max,
        adaptive=adaptive,
        task_value=task_value,
        median_task_value=median_task_value,
        frozen_plan=frozen_plan,
        allocation=allocation,
    )
    model_cfg = config.get("model", {})
    model = BudgetFlowLitellmModel(
        workflow_id=task.instance_id,
        governor=governor,
        routing=routing,
        observation_template=model_cfg.get("observation_template"),
        format_error_template=model_cfg.get("format_error_template"),
        enable_turn_trace=enable_turn_trace,
    )
    env_cfg = dict(config.get("environment", {}))
    env = LocalEnvironment(
        cwd=str(env_cfg.get("cwd") or repo_dir),
        env=dict(env_cfg.get("env") or {}),
        timeout=env_cfg.get("timeout", 120),
    )
    agent_cfg = dict(config.get("agent", {}))
    agent_cfg["output_path"] = trace_dir / "trajectory.json"
    run_started = time.time()
    agent = TracedDefaultAgent(model, env, trace=trace, run_started=run_started, **agent_cfg)
    if progress_box is not None:

        def _refresh_live_progress() -> None:
            trace.publish_live_progress(agent, elapsed_s=time.time() - run_started)

        model._progress_refresh = _refresh_live_progress

    patch_text: str | None = None
    exit_status = "unknown"
    exit_reason: str | None = None
    try:
        if agent_heartbeat and progress_box is None:
            exit_info = run_with_heartbeat(
                task.instance_id,
                lambda: agent.run(task.problem_statement),
                interval_s=30.0,
                status_fn=lambda: trace.heartbeat_status(agent, elapsed_s=time.time() - run_started),
            )
        else:
            exit_info = agent.run(task.problem_statement)
        exit_status = str(exit_info.get("exit_status", "unknown"))
        patch_text = exit_info.get("submission") or None
        if exit_status.lower() in {"submitted", "complete"}:
            exit_reason = "submitted"
    except Submitted as submitted:
        message = submitted.args[0] if submitted.args else {}
        exit_status = message.get("extra", {}).get("exit_status", "Submitted")
        patch_text = message.get("extra", {}).get("submission") or message.get("content")
        exit_reason = "submitted"
    except BudgetFlowBudgetError as exc:
        exit_status = "BudgetFlowBudgetError"
        exit_reason = exc.exit_reason
        model.last_exit_reason = exc.exit_reason
        model.last_budget_snapshot = exc.budget_snapshot
    except BudgetFlowStagnationError as exc:
        exit_status = "StagnationExit"
        exit_reason = exc.exit_reason
        model.last_exit_reason = exc.exit_reason
    except BudgetFlowUpstreamError as exc:
        exit_status = "UpstreamExit"
        exit_reason = exc.exit_reason
        model.last_exit_reason = exc.exit_reason
        if exit_reason == "infra_error":
            exit_status = "infra_error"
    except Exception as exc:  # noqa: BLE001
        exit_status = type(exc).__name__
        exit_reason = type(exc).__name__

    if exit_reason is None and model.last_exit_reason:
        exit_reason = model.last_exit_reason

    patch_source = "submission" if patch_text else "none"

    trace.finalize_agent(submitted=exit_reason == "submitted", patch_extracted=bool(patch_text))
    if patch_text:
        submitted_patch = trace_dir / "submitted.patch"
        submitted_patch.write_text(patch_text if patch_text.endswith("\n") else patch_text + "\n")
        print(
            f"{tag('eval', bold=False)} {task.instance_id} {label} running harness on extracted patch...",
            flush=True,
        )
    else:
        submitted_patch = None

    harness = evaluate_local_harness(task, patch_text, workspace_key=workspace_key)
    trace.log_harness_result(
        resolved=harness.harness_resolved,
        detail=harness.detail,
        patch_extracted=bool(patch_text),
    )
    agent_summary = trace.agent_summary()
    agent_exit_status = exit_status
    agent_exit_reason = exit_reason
    exit_status, exit_reason = _harness_exit_label(
        agent_exit_status=agent_exit_status,
        agent_exit_reason=agent_exit_reason,
        harness_resolved=harness.harness_resolved,
        patch_text=patch_text,
        harness_detail=harness.detail,
    )
    violations: list[str] = []
    if governor.state.available_budget < 0:
        violations.append("budget_violation")
    snapshot = model.last_budget_snapshot or governor.budget_snapshot()
    task_cost = ledger.get(task.instance_id).actual_cost
    usage_source, cost_mode = _row_cost_observability(model, task_cost)
    trace_rows = list(model.turn_traces)
    first_trace = next((t for t in trace_rows if isinstance(t, dict)), {})
    first_provider_error = next(
        (t for t in trace_rows if isinstance(t, dict) and t.get("provider_error_kind")),
        {},
    )
    return MiniSweRunResult(
        instance_id=task.instance_id,
        strategy=strategy,
        strategy_label=label,
        patch_text=patch_text,
        exit_status=exit_status,
        exit_reason=exit_reason,
        agent_exit_status=agent_exit_status,
        agent_exit_reason=agent_exit_reason,
        total_cost=task_cost,
        budget_cap=cap,
        budget_snapshot=snapshot,
        backend_picks=tuple(model.backend_picks),
        llm_turns=model.step_index,
        harness_resolved=harness.harness_resolved,
        harness_detail=harness.detail,
        agent_gold_edited=bool(agent_summary.get("gold_edited")),
        agent_attempted_submit=bool(agent_summary.get("attempted_submit")),
        agent_submitted=bool(agent_summary.get("submitted")),
        agent_gold_files=tuple(str(f) for f in (agent_summary.get("gold_files") or ())),
        violations=tuple(violations),
        patch_source=patch_source,
        prompt_tokens_total=model._total_prompt_tokens,
        completion_tokens_total=model._total_completion_tokens,
        provider_usage_turns=model._provider_usage_turns,
        estimated_usage_turns=model._estimated_usage_turns,
        cost_mode=cost_mode,
        usage_source=usage_source,
        turn_trace_count=len(model.turn_traces),
        turn_traces=trace_rows if trace_rows else None,
        submitted_patch_path=str(submitted_patch) if submitted_patch is not None else None,
        protocol_retry_used=model._protocol_retry_used,
        protocol_retry_success=model._protocol_retry_success,
        protocol_retry_reason=model._protocol_retry_reason,
        protocol_retry_attempts=model._protocol_retry_attempts,
        protocol_retry_limit=model._protocol_retry_limit,
        protocol=str(first_trace.get("protocol") or ""),
        parser=str(first_trace.get("parser") or ""),
        provider_error_kind=str(first_provider_error.get("provider_error_kind") or ""),
        provider_retryable=first_provider_error.get("provider_retryable"),
    )

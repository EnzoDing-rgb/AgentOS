from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MINI_SWE_SRC = REPO_ROOT / "external" / "mini-swe-agent" / "src"
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
from ..local_harness import clone_or_checkout, evaluate_local_harness, get_last_compat_files
from ..run_trace import RunTraceLogger, TracedDefaultAgent, TraceConsoleLevel, patch_local_swebench_config
from .backends import build_deepseek_backends
from .errors import BudgetFlowBudgetError
from .mini_swe_proxy import BudgetFlowLitellmModel
from .strategies import build_routing_context

SWEBENCH_CONFIG = REPO_ROOT / "external" / "mini-swe-agent" / "src" / "minisweagent" / "config" / "benchmarks" / "swebench.yaml"
RUNS_DIR = REPO_ROOT / "paper1" / "data" / "runs"


@dataclass(frozen=True)
class MiniSweRunResult:
    instance_id: str
    strategy: str
    strategy_label: str
    patch_text: str | None
    exit_status: str
    exit_reason: str | None
    total_cost: float
    budget_cap: float
    budget_snapshot: dict[str, float]
    backend_picks: tuple[str, ...]
    llm_turns: int
    harness_resolved: bool
    harness_detail: str
    agent_gold_edited: bool
    agent_submitted: bool
    agent_gold_files: tuple[str, ...]
    violations: tuple[str, ...]


def _load_agent_config(*, step_limit: int = 250) -> dict:
    config = recursive_merge(
        get_config_from_spec(SWEBENCH_CONFIG),
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
    step_limit: int = 250,
    trace_console: TraceConsoleLevel = "quiet",
    progress_box: dict[str, str] | None = None,
    agent_heartbeat: bool = True,
) -> MiniSweRunResult:
    label = strategy_label or strategy
    repo_dir = clone_or_checkout(task)
    compat_files = get_last_compat_files()
    trace_dir = RUNS_DIR / f"trace_{task.instance_id}_{label}"
    trace = RunTraceLogger(
        instance_id=task.instance_id,
        repo_dir=repo_dir,
        trace_dir=trace_dir,
        target_files=task.gold_files,
        strategy_label=label,
        ignore_changed_files=compat_files,
        console_level=trace_console,
        progress_box=progress_box,
    )
    config = patch_local_swebench_config(_load_agent_config(step_limit=step_limit), repo_dir)
    backends = build_deepseek_backends()
    ledger = WorkflowLedgerStore()
    cap = budget_per_task if budget_per_task is not None else 1_000_000.0
    governor = BudgetGovernor(
        GovernorConfig(total_budget=cap, default_max_output_tokens=4096),
        ledger,
    )
    routing = build_routing_context(strategy, backends, budget_pressure=budget_pressure)
    model_cfg = config.get("model", {})
    model = BudgetFlowLitellmModel(
        workflow_id=task.instance_id,
        governor=governor,
        routing=routing,
        observation_template=model_cfg.get("observation_template"),
        format_error_template=model_cfg.get("format_error_template"),
    )
    env = LocalEnvironment(cwd=str(repo_dir), timeout=config.get("environment", {}).get("timeout", 120))
    agent_cfg = dict(config.get("agent", {}))
    agent_cfg["output_path"] = trace_dir / "trajectory.json"
    run_started = time.time()
    agent = TracedDefaultAgent(model, env, trace=trace, run_started=run_started, **agent_cfg)

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
    except Exception as exc:  # noqa: BLE001
        exit_status = type(exc).__name__
        exit_reason = type(exc).__name__

    if exit_reason is None and model.last_exit_reason:
        exit_reason = model.last_exit_reason

    trace.finalize_agent(submitted=exit_reason == "submitted", patch_extracted=bool(patch_text))
    if patch_text:
        print(
            f"{tag('eval', bold=False)} {task.instance_id} {label} running harness on extracted patch...",
            flush=True,
        )

    harness = evaluate_local_harness(task, patch_text)
    trace.log_harness_result(
        resolved=harness.harness_resolved,
        detail=harness.detail,
        patch_extracted=bool(patch_text),
    )
    agent_summary = trace.agent_summary()
    violations: list[str] = []
    if governor.state.available_budget < 0:
        violations.append("budget_violation")
    snapshot = model.last_budget_snapshot or governor.budget_snapshot()
    return MiniSweRunResult(
        instance_id=task.instance_id,
        strategy=strategy,
        strategy_label=label,
        patch_text=patch_text,
        exit_status=exit_status,
        exit_reason=exit_reason,
        total_cost=governor.state.spent_budget,
        budget_cap=cap,
        budget_snapshot=snapshot,
        backend_picks=tuple(model.backend_picks),
        llm_turns=model.step_index,
        harness_resolved=harness.harness_resolved,
        harness_detail=harness.detail,
        agent_gold_edited=bool(agent_summary.get("gold_edited")),
        agent_submitted=bool(agent_summary.get("submitted")),
        agent_gold_files=tuple(str(f) for f in (agent_summary.get("gold_files") or ())),
        violations=tuple(violations),
    )

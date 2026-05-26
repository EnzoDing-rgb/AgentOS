from __future__ import annotations

import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from budgetflow.deepseek_backend import DeepSeekBackend, load_env_file
from budgetflow.governor import BudgetGovernor
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.lite_tasks import LiteTaskRecord, load_swebench_lite_tasks
from budgetflow.loop import WorkflowResult, build_default_loop
from budgetflow.selector import build_deepseek_progress_table
from budgetflow.types import Backend, GovernorConfig, TurnInfo

# Frozen from mock 2-tier sweep — not tuned on eval tasks 0–19.
FROZEN_BUDGET_PRESSURE = 0.35


def report(message: str) -> None:
    print(message, flush=True)


def build_backends() -> list[Backend]:
    """Mock-scale costs so selector pressure ~0.35 routes Flash/Pro mix."""
    return [
        Backend(
            name="deepseek_flash",
            tier=1,
            cost_per_input_token=0.0010,
            cost_per_output_token=0.0020,
            rpm_limit=20,
            concurrency_limit=1,
            mean_output_tokens=256,
            progress_score=0.11,
            latency_ms=300,
        ),
        Backend(
            name="deepseek_pro",
            tier=2,
            cost_per_input_token=0.0028,
            cost_per_output_token=0.0056,
            rpm_limit=20,
            concurrency_limit=1,
            mean_output_tokens=512,
            progress_score=0.16,
            latency_ms=600,
        ),
    ]


def build_runner(backends: list[Backend], tasks_by_id: dict[str, LiteTaskRecord]):
    def get_task(workflow_id: str) -> LiteTaskRecord | None:
        return tasks_by_id.get(workflow_id)

    clients = {
        "deepseek_flash": DeepSeekBackend(
            backends[0],
            model_name="deepseek-v4-flash",
            enable_thinking=False,
            get_task=get_task,
        ),
        "deepseek_pro": DeepSeekBackend(
            backends[1],
            model_name="deepseek-v4-pro",
            enable_thinking=True,
            reasoning_effort="high",
            get_task=get_task,
        ),
    }

    def runner(backend: Backend, turn, input_tokens: int):
        return clients[backend.name].run(turn, input_tokens)

    return runner


def fixed_backend_picker(name: str):
    def picker(
        turn: TurnInfo,
        backends: list[Backend],
        _selector,
        _pressure: float,
        _expected_costs: dict[str, float],
    ) -> Backend:
        for backend in backends:
            if backend.name == name:
                return backend
        return backends[0]

    return picker


@dataclass(frozen=True)
class StrategyRun:
    strategy: str
    task_id: str
    workflow_steps_ok: bool
    total_cost: float
    backend_picks: tuple[str, ...]
    step_ok: tuple[bool, ...]


@dataclass(frozen=True)
class StrategySummary:
    strategy: str
    workflow_steps_ok: int
    total: int
    total_cost: float
    flash_steps: int
    pro_steps: int


def run_strategy_on_task(
    strategy: str,
    task: LiteTaskRecord,
    backends: list[Backend],
    budget_pressure: float,
) -> StrategyRun:
    tasks_by_id = {task.instance_id: task}
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=20.0, default_max_output_tokens=512), ledger)
    runner = build_runner(backends, tasks_by_id)

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
    step_ok = tuple(trace.progress_made for trace in result.traces)
    return StrategyRun(
        strategy=strategy,
        task_id=task.instance_id,
        workflow_steps_ok=result.resolved,
        total_cost=result.total_cost,
        backend_picks=picks,
        step_ok=step_ok,
    )


def summarize_runs(strategy: str, runs: list[StrategyRun]) -> StrategySummary:
    flash = sum(pick == "deepseek_flash" for run in runs for pick in run.backend_picks)
    pro = sum(pick == "deepseek_pro" for run in runs for pick in run.backend_picks)
    ok = sum(1 for run in runs if run.workflow_steps_ok)
    cost = sum(run.total_cost for run in runs)
    return StrategySummary(strategy=strategy, workflow_steps_ok=ok, total=len(runs), total_cost=cost, flash_steps=flash, pro_steps=pro)


def main() -> None:
    load_env_file()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    strategies = ("all_flash", "all_pro", "budgetflow_full")

    tasks = load_swebench_lite_tasks(limit=limit)
    backends = build_backends()
    report(f"DeepSeek compare: {len(tasks)} Lite tasks, pressure={FROZEN_BUDGET_PRESSURE} (frozen)")
    report("Metrics: workflow_steps_ok = API+rubric only. harness_resolved = N/A (no patch harness).")
    report("Cost = mock-scale governor units (cross-strategy fair), not exact API USD.")
    report("")

    all_runs: dict[str, list[StrategyRun]] = {name: [] for name in strategies}
    started = time.time()

    for index, task in enumerate(tasks, start=1):
        report(f"=== task [{index}/{len(tasks)}] {task.instance_id} ===")
        for strategy in strategies:
            run_started = time.time()
            run = run_strategy_on_task(strategy, task, backends, FROZEN_BUDGET_PRESSURE)
            all_runs[strategy].append(run)
            picks = "/".join(name.replace("deepseek_", "") for name in run.backend_picks)
            steps = "/".join("OK" if ok else "FAIL" for ok in run.step_ok)
            status = "OK" if run.workflow_steps_ok else "FAIL"
            report(
                f"  {strategy:16s} {status} steps=[{steps}] picks={picks} "
                f"cost={run.total_cost:.4f} elapsed={time.time() - run_started:.1f}s"
            )
        report("")

    report("=== SUMMARY ===")
    report(f"{'strategy':16s} {'steps_ok':>10s} {'cost':>10s} {'flash':>6s} {'pro':>6s}")
    for strategy in strategies:
        summary = summarize_runs(strategy, all_runs[strategy])
        report(
            f"{summary.strategy:16s} "
            f"{summary.workflow_steps_ok}/{summary.total:>8d} "
            f"{summary.total_cost:10.4f} "
            f"{summary.flash_steps:6d} {summary.pro_steps:6d}"
        )
    report(f"elapsed={time.time() - started:.1f}s")


if __name__ == "__main__":
    main()

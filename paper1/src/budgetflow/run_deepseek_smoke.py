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
from budgetflow.types import Backend, GovernorConfig


def report(message: str) -> None:
    print(message, flush=True)


def build_backends() -> list[Backend]:
    return [
        Backend(
            name="deepseek_flash",
            tier=1,
            cost_per_input_token=0.00000014,
            cost_per_output_token=0.00000028,
            rpm_limit=20,
            concurrency_limit=1,
            mean_output_tokens=256,
            progress_score=0.11,
            latency_ms=300,
        ),
        Backend(
            name="deepseek_pro",
            tier=2,
            cost_per_input_token=0.00000055,
            cost_per_output_token=0.00000219,
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


@dataclass(frozen=True)
class TaskRunSummary:
    task_id: str
    resolved: bool
    total_cost: float
    backend_picks: tuple[str, ...]


def run_task(
    task: LiteTaskRecord,
    backends: list[Backend],
    budget_pressure: float,
    task_index: int,
    task_total: int,
) -> TaskRunSummary:
    report(f"[{task_index}/{task_total}] START {task.instance_id}")
    tasks_by_id = {task.instance_id: task}
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=512), ledger)
    loop = build_default_loop(
        backends,
        governor,
        ledger,
        budget_pressure=budget_pressure,
        backend_runner=build_runner(backends, tasks_by_id),
    )
    started = time.time()
    result: WorkflowResult = loop.run_workflow(task.workflow)
    elapsed = time.time() - started
    picks = tuple(trace.chosen_backend for trace in result.traces)
    for trace in result.traces:
        backend = trace.chosen_backend.replace("deepseek_", "")
        step_status = "OK" if trace.progress_made else "FAIL"
        report(
            f"[{task_index}/{task_total}]   step={trace.step_index} "
            f"stage={trace.stage.value} backend={backend} {step_status} cost={trace.actual_cost:.6f}"
        )
    summary = TaskRunSummary(task.instance_id, result.resolved, result.total_cost, picks)
    status = "OK" if summary.resolved else "FAIL"
    picks_text = "/".join(name.replace("deepseek_", "") for name in summary.backend_picks)
    report(
        f"[{task_index}/{task_total}] DONE {summary.task_id} {status} "
        f"cost={summary.total_cost:.6f} picks={picks_text} elapsed={elapsed:.1f}s"
    )
    return summary


def main() -> None:
    load_env_file()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    pressure = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3

    tasks = load_swebench_lite_tasks(limit=limit)
    backends = build_backends()
    report(f"DeepSeek Flash+Pro eval: {len(tasks)} Lite tasks, budget_pressure={pressure}")
    report("Rough timing: ~30s per task, 20 tasks ~10 min.")

    summaries: list[TaskRunSummary] = []
    backend_counter: Counter[str] = Counter()
    started = time.time()
    for index, task in enumerate(tasks, start=1):
        summary = run_task(task, backends, budget_pressure=pressure, task_index=index, task_total=len(tasks))
        summaries.append(summary)
        backend_counter.update(summary.backend_picks)

    resolved = sum(1 for item in summaries if item.resolved)
    total_cost = sum(item.total_cost for item in summaries)
    report("")
    report(
        f"FINAL resolved={resolved}/{len(summaries)} total_cost={total_cost:.6f} "
        f"elapsed={time.time() - started:.1f}s"
    )
    report(
        f"FINAL backend_picks flash={backend_counter['deepseek_flash']} pro={backend_counter['deepseek_pro']}"
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from budgetflow.deepseek_backend import DeepSeekBackend
from budgetflow.governor import BudgetGovernor
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.lite_tasks import load_swebench_lite_tasks
from budgetflow.loop import build_default_loop
from budgetflow.types import Backend, GovernorConfig, TurnInfo


def build_backends() -> list[Backend]:
    return [
        Backend(name="deepseek_flash", tier=1, cost_per_input_token=0.0, cost_per_output_token=0.0, rpm_limit=20, concurrency_limit=1, mean_output_tokens=64, progress_score=0.11, latency_ms=300),
        Backend(name="deepseek_pro", tier=2, cost_per_input_token=0.0, cost_per_output_token=0.0, rpm_limit=20, concurrency_limit=1, mean_output_tokens=96, progress_score=0.16, latency_ms=600),
    ]


def build_runner(backends: list[Backend]):
    clients = {
        "deepseek_flash": DeepSeekBackend(backends[0], model_name="deepseek-v4-flash"),
        "deepseek_pro": DeepSeekBackend(backends[1], model_name="deepseek-v4-pro"),
    }

    def runner(backend: Backend, turn: TurnInfo, input_tokens: int):
        return clients[backend.name].run(turn, input_tokens)

    return runner


def main() -> None:
    task = load_swebench_lite_tasks(limit=1)[0]
    backends = build_backends()
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=10.0, default_max_output_tokens=128), ledger)
    loop = build_default_loop(
        backends,
        governor,
        ledger,
        budget_pressure=0.3,
        backend_runner=build_runner(backends),
    )
    result = loop.run_workflow(task.workflow)
    print("task", task.instance_id)
    print("resolved", result.resolved)
    print("total_cost", result.total_cost)
    for trace in result.traces:
        print(trace.step_index, trace.stage.value, trace.chosen_backend, trace.progress_made, trace.actual_cost)


if __name__ == "__main__":
    main()

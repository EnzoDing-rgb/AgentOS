from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from budgetflow.compare import ComparisonRunner
from budgetflow.lite_tasks import load_swebench_lite_tasks
from budgetflow.types import Backend


def build_backends() -> list[Backend]:
    return [
        Backend(name="tier1_cheap", tier=1, cost_per_input_token=0.0010, cost_per_output_token=0.0020, rpm_limit=100, concurrency_limit=2, mean_output_tokens=28, progress_score=0.11, latency_ms=35),
        Backend(name="tier2_balanced", tier=2, cost_per_input_token=0.0018, cost_per_output_token=0.0036, rpm_limit=100, concurrency_limit=2, mean_output_tokens=34, progress_score=0.145, latency_ms=45),
        Backend(name="tier3_strong", tier=3, cost_per_input_token=0.0028, cost_per_output_token=0.0056, rpm_limit=100, concurrency_limit=2, mean_output_tokens=42, progress_score=0.19, latency_ms=58),
        Backend(name="tier4_elite", tier=4, cost_per_input_token=0.0042, cost_per_output_token=0.0084, rpm_limit=100, concurrency_limit=2, mean_output_tokens=50, progress_score=0.235, latency_ms=72),
    ]


def main() -> None:
    tasks = load_swebench_lite_tasks(limit=20)
    workflows = [task.workflow for task in tasks]
    runner = ComparisonRunner(build_backends(), total_budget=240.0, default_max_output_tokens=100)
    for pressure in (0.22, 0.45):
        full = runner.run_budgetflow_full(workflows, pressure)
        workflow = runner.run_workflow_level_router(workflows, pressure)
        budget = runner.run_budget_only_step_router(workflows, pressure)
        print(f"pressure={pressure}")
        print(f"  workflow_level_router {workflow.resolved_count} {workflow.total_cost:.4f}")
        print(f"  budget_only_step_router {budget.resolved_count} {budget.total_cost:.4f}")
        print(f"  budgetflow_full {full.resolved_count} {full.total_cost:.4f}")


if __name__ == "__main__":
    main()

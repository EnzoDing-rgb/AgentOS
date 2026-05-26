from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.compare import ComparisonRunner
from budgetflow.governor import BudgetGovernor
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.lite_tasks import load_swebench_lite_tasks
from budgetflow.loop import WorkflowSpec, WorkflowStep, build_default_loop
from budgetflow.types import Backend, GovernorConfig, Stage


def build_backends() -> list[Backend]:
    return [
        Backend(
            name="tier1_cheap",
            tier=1,
            cost_per_input_token=0.0010,
            cost_per_output_token=0.0020,
            rpm_limit=100,
            concurrency_limit=2,
            mean_output_tokens=28,
            progress_score=0.11,
            latency_ms=35,
        ),
        Backend(
            name="tier2_balanced",
            tier=2,
            cost_per_input_token=0.0018,
            cost_per_output_token=0.0036,
            rpm_limit=100,
            concurrency_limit=2,
            mean_output_tokens=34,
            progress_score=0.145,
            latency_ms=45,
        ),
        Backend(
            name="tier3_strong",
            tier=3,
            cost_per_input_token=0.0028,
            cost_per_output_token=0.0056,
            rpm_limit=100,
            concurrency_limit=2,
            mean_output_tokens=42,
            progress_score=0.19,
            latency_ms=58,
        ),
        Backend(
            name="tier4_elite",
            tier=4,
            cost_per_input_token=0.0042,
            cost_per_output_token=0.0084,
            rpm_limit=100,
            concurrency_limit=2,
            mean_output_tokens=50,
            progress_score=0.235,
            latency_ms=72,
        ),
    ]


def build_workflows() -> list[WorkflowSpec]:
    workflow_specs: list[tuple[str, tuple[int, int, int]]] = [
        ("wf-1", (78, 118, 94)),
        ("wf-2", (84, 124, 102)),
        ("wf-3", (92, 138, 110)),
        ("wf-4", (88, 134, 108)),
        ("wf-5", (96, 146, 116)),
        ("wf-6", (104, 152, 122)),
    ]
    return [
        WorkflowSpec(
            workflow_id=workflow_id,
            steps=(
                WorkflowStep(stage=Stage.LOCALIZATION, input_tokens=localization_tokens, w_i=1.0),
                WorkflowStep(stage=Stage.REPAIR, input_tokens=repair_tokens, w_i=3.0),
                WorkflowStep(stage=Stage.VALIDATION, input_tokens=validation_tokens, w_i=2.5),
            ),
        )
        for workflow_id, (localization_tokens, repair_tokens, validation_tokens) in workflow_specs
    ]


def test_minimal_loop_runs_end_to_end() -> None:
    backends = build_backends()
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=10.0, default_max_output_tokens=100), ledger)
    loop = build_default_loop(backends, governor, ledger, budget_pressure=0.55)

    result = loop.run_workflow(build_workflows()[0])

    assert result.workflow_id == "wf-1"
    assert len(result.traces) == 3
    assert result.total_cost > 0
    assert any(trace.progress_made for trace in result.traces)
    assert len({trace.chosen_backend for trace in result.traces}) >= 2


def test_budget_violation_is_blocked() -> None:
    backends = build_backends()
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=0.05, default_max_output_tokens=100), ledger)
    loop = build_default_loop(backends, governor, ledger, budget_pressure=0.55)

    result = loop.run_workflow(build_workflows()[0])

    assert result.resolved is False
    assert any(trace.status == "failed" for trace in result.traces)
    assert governor.state.spent_budget <= governor.state.total_budget


def test_policy_comparison_runs_small_scale() -> None:
    runner = ComparisonRunner(build_backends(), total_budget=40.0, default_max_output_tokens=100)
    workflows = build_workflows()

    full = runner.run_budgetflow_full(workflows, budget_pressure=0.55)
    workflow_level = runner.run_workflow_level_router(workflows, budget_pressure=0.55)
    budget_only = runner.run_budget_only_step_router(workflows, budget_pressure=0.55)

    assert full.resolved_count >= workflow_level.resolved_count
    assert full.resolved_count >= budget_only.resolved_count
    assert full.total_cost > 0
    assert workflow_level.total_cost > 0
    assert budget_only.total_cost > 0
    assert full.policy_name == "budgetflow_full"


def test_load_swebench_lite_tasks_builds_real_workflows() -> None:
    tasks = load_swebench_lite_tasks(limit=2)

    assert len(tasks) == 2
    assert all(task.instance_id for task in tasks)
    assert all(task.workflow.workflow_id == task.instance_id for task in tasks)
    assert all(len(task.workflow.steps) == 3 for task in tasks)
    assert all(task.workflow.steps[0].stage == Stage.LOCALIZATION for task in tasks)
    assert all(task.workflow.steps[1].stage == Stage.REPAIR for task in tasks)
    assert all(task.workflow.steps[2].stage == Stage.VALIDATION for task in tasks)

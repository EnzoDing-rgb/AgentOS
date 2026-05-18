from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.compare import ComparisonRunner
from budgetflow.governor import BudgetGovernor
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.loop import WorkflowSpec, WorkflowStep, build_default_loop
from budgetflow.types import Backend, GovernorConfig, Stage


def build_backends() -> list[Backend]:
    return [
        Backend(
            name="cheap",
            tier=1,
            cost_per_input_token=0.001,
            cost_per_output_token=0.002,
            rpm_limit=100,
            concurrency_limit=1,
            mean_output_tokens=40,
            progress_score=0.12,
            latency_ms=40,
        ),
        Backend(
            name="strong",
            tier=2,
            cost_per_input_token=0.003,
            cost_per_output_token=0.006,
            rpm_limit=100,
            concurrency_limit=1,
            mean_output_tokens=40,
            progress_score=0.24,
            latency_ms=60,
        ),
    ]


def build_workflows() -> list[WorkflowSpec]:
    return [
        WorkflowSpec(
            workflow_id="wf-1",
            steps=(
                WorkflowStep(stage=Stage.LOCALIZATION, input_tokens=80, w_i=1.0),
                WorkflowStep(stage=Stage.REPAIR, input_tokens=120, w_i=3.0),
                WorkflowStep(stage=Stage.VALIDATION, input_tokens=100, w_i=2.5),
            ),
        ),
        WorkflowSpec(
            workflow_id="wf-2",
            steps=(
                WorkflowStep(stage=Stage.LOCALIZATION, input_tokens=70, w_i=1.0),
                WorkflowStep(stage=Stage.REPAIR, input_tokens=110, w_i=3.0),
                WorkflowStep(stage=Stage.VALIDATION, input_tokens=90, w_i=2.5),
            ),
        ),
    ]


def test_minimal_loop_runs_end_to_end() -> None:
    backends = build_backends()
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=10.0, default_max_output_tokens=100), ledger)
    loop = build_default_loop(backends, governor, ledger, budget_pressure=0.3)

    result = loop.run_workflow(build_workflows()[0])

    assert result.workflow_id == "wf-1"
    assert len(result.traces) == 3
    assert result.total_cost > 0
    assert result.resolved is True
    assert any(trace.chosen_backend == "strong" for trace in result.traces)


def test_budget_violation_is_blocked() -> None:
    backends = build_backends()
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=0.05, default_max_output_tokens=100), ledger)
    loop = build_default_loop(backends, governor, ledger, budget_pressure=0.3)

    result = loop.run_workflow(build_workflows()[0])

    assert result.resolved is False
    assert any(trace.status == "failed" for trace in result.traces)
    assert governor.state.spent_budget <= governor.state.total_budget


def test_policy_comparison_runs_small_scale() -> None:
    runner = ComparisonRunner(build_backends(), total_budget=20.0, default_max_output_tokens=100)
    workflows = build_workflows()

    full = runner.run_budgetflow_full(workflows, budget_pressure=0.3)
    workflow_level = runner.run_workflow_level_router(workflows, budget_pressure=0.3)
    budget_only = runner.run_budget_only_step_router(workflows, budget_pressure=3.0)

    assert full.resolved_count == 2
    assert workflow_level.resolved_count == 0
    assert budget_only.resolved_count == 0
    assert full.total_cost > 0
    assert workflow_level.total_cost > 0
    assert budget_only.total_cost > 0
    assert full.policy_name == "budgetflow_full"

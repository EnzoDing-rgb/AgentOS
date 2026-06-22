import json
import threading
from types import SimpleNamespace

import pytest

from budgetflow.compare_checkpoint import CompareCheckpointStore, GlobalRunProgress, StrategyScoreboard
from budgetflow.experiments.compare_persistence import (
    CompareRunState,
    completed_keys,
    persist_task_record,
    rebuild_state_from_jsonl,
)
from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.experiments.compare_execution import run_strategy_batch, run_task_record
from budgetflow.experiments.compare_execution import _effective_planned_task_cap, _shared_batch_pressure
from budgetflow.experiments.compare_summary import (
    _append_summary,
    _format_live_snapshot,
    _format_strategy_totals,
)
from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.value_efficiency import ValueEfficiencyContext


def _state() -> CompareRunState:
    return CompareRunState(
        summary_lines=[],
        resolved_by_strategy={},
        score_status_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        tier_mix_by_strategy={},
        failure_by_strategy={},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )


def _value_context() -> ValueEfficiencyContext:
    ctx = ValueEfficiencyContext()
    ctx.init(value_profile="equal")
    return ctx


def _record(**overrides) -> dict:
    record = {
        "instance_id": "sympy__sympy-14774",
        "strategy": "budgetflow_segment",
        "routing": "segment_value_aware",
        "harness_resolved": True,
        "score_status": "pass",
        "abort_reason": "",
        "patch_extracted": True,
        "agent_gold_edited": True,
        "agent_gold_files": ["sympy/printing/latex.py"],
        "llm_turns": 2,
        "total_cost": 0.25,
        "batch_spent": 0.25,
        "backend_picks": ["tier2", "tier3"],
        "failure_class": "pass",
        "forensic_summary": {"primary_axis": "pass"},
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
        "task_features": {"patch_lines": 12, "f2p_count": 1, "p2p_count": 114, "problem_length": 500},
        "routing_prior_summary": {
            "learned_action": "early_rescue",
            "policy_memory_source": "data/runs/066_postfix_3x3.jsonl",
        },
        "run_series": "schema_contract",
        "attempt_id": "schema_contract_budgetflow_segment_sympy__sympy-14774",
    }
    record.update(overrides)
    return record


def test_compare_runner_records_turns_value_and_task_features(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    def fake_run_mini_swe_task(*args, **kwargs):
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.01,
            harness_resolved=True,
            patch_text="diff --git a/x b/x\n",
            patch_source="workspace_diff",
            submitted_patch_path="/tmp/submitted.patch",
            workspace_patch_path="/tmp/workspace.patch",
            trace_dir="/tmp/trace",
            trace_steps_path="/tmp/trace/steps.jsonl",
            exit_status="Submitted",
            exit_reason="submitted",
            agent_exit_status="Submitted",
            agent_exit_reason="submitted",
            backend_picks=["tier2", "tier3"],
            llm_turns=2,
            violations=[],
            harness_detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
            agent_gold_edited=True,
            agent_gold_files=["x.py"],
            agent_attempted_submit=True,
            agent_submitted=True,
            prompt_tokens_total=10,
            completion_tokens_total=2,
            provider_usage_turns=2,
            estimated_usage_turns=0,
            usage_source="provider",
            cost_mode="catalog_provider_usage",
            turn_trace_count=2,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
            protocol="tool_call",
            parser="parse_toolcall_actions",
            provider_error_kind="",
            provider_retryable=None,
        )

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), WorkflowLedgerStore())
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    record = run_task_record(
        task,
        cfg=CompareStrategy("budget_only_baseline", "budget_only"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
        value_context=_value_context(),
        task_set="easy",
        task_set_kind="familiar",
    )

    assert record["llm_turns"] == 2
    assert record["harness_resolved"] is True
    assert "yield_per_dollar" not in record
    assert record["task_features"] == {"patch_lines": 1, "f2p_count": 1, "p2p_count": 0, "problem_length": 0}
    assert record["task_set"] == "easy"
    assert record["task_set_kind"] == "familiar"
    assert record["budget_exhausted"] is False


def test_compare_runner_records_workspace_patch_as_scoreable_artifact(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    def fake_run_mini_swe_task(*args, **kwargs):
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.01,
            harness_resolved=False,
            patch_text="diff --git a/x b/x\n",
            patch_source="workspace_diff",
            submitted_patch_path=None,
            workspace_patch_path="/tmp/workspace.patch",
            trace_dir="/tmp/trace",
            trace_steps_path="/tmp/trace/steps.jsonl",
            exit_status="HarnessFailed",
            exit_reason="harness_failed",
            agent_exit_status="BudgetFlowBudgetError",
            agent_exit_reason="budget_exhausted",
            backend_picks=["tier2"],
            llm_turns=2,
            violations=[],
            harness_detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
            agent_gold_edited=True,
            agent_gold_files=["x.py"],
            agent_attempted_submit=False,
            agent_submitted=False,
            prompt_tokens_total=10,
            completion_tokens_total=2,
            provider_usage_turns=2,
            estimated_usage_turns=0,
            usage_source="provider",
            cost_mode="catalog_provider_usage",
            turn_trace_count=2,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
            protocol="tool_call",
            parser="parse_toolcall_actions",
            provider_error_kind="",
            provider_retryable=None,
        )

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), WorkflowLedgerStore())
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    record = run_task_record(
        task,
        cfg=CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
        value_context=_value_context(),
    )

    assert record["patch_extracted"] is True
    assert record["patch_source"] == "workspace_diff"
    assert record["workspace_patch"] == "/tmp/workspace.patch"
    assert record["submitted_patch"] is None
    assert record["harness_trust"] == "trusted"


def test_runner_threads_budget_plan_model_fit_into_allocation_context(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    seen = {}

    def fake_run_mini_swe_task(*args, **kwargs):
        seen["allocation"] = kwargs["allocation"]
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.01,
            harness_resolved=False,
            patch_text="",
            patch_source="none",
            submitted_patch_path="",
            trace_dir="/tmp/trace",
            trace_steps_path="/tmp/trace/steps.jsonl",
            exit_status="Stopped",
            exit_reason="budget_exhausted",
            agent_exit_status="Stopped",
            agent_exit_reason="budget_exhausted",
            backend_picks=["tier3"],
            llm_turns=1,
            violations=[],
            harness_detail="",
            agent_gold_edited=False,
            agent_gold_files=[],
            agent_attempted_submit=False,
            agent_submitted=False,
            prompt_tokens_total=10,
            completion_tokens_total=2,
            provider_usage_turns=1,
            estimated_usage_turns=0,
            usage_source="provider",
            cost_mode="catalog_provider_usage",
            turn_trace_count=1,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
            protocol="tool_call",
            parser="parse_toolcall_actions",
            provider_error_kind="",
            provider_retryable=None,
        )

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), WorkflowLedgerStore())
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    record = run_task_record(
        task,
        cfg=CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
        value_context=_value_context(),
        calibrated_model_fit={"tier2": 0.08, "tier3": 0.65},
        calibrated_model_fit_source="budget_plan:historical_jsonl",
    )

    assert seen["allocation"].model_fit == {"tier2": 0.08, "tier3": 0.65}
    assert seen["allocation"].model_fit_source == "budget_plan:historical_jsonl"
    assert record["model_fit_source"] == "budget_plan:historical_jsonl"
    assert record["exit_owner"] == "budget_exhausted"
    assert record["budget_exhausted"] is True


def test_runner_threads_run_series_to_run_scoped_trace_dir(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    seen = {}

    def fake_run_mini_swe_task(*args, **kwargs):
        seen["run_series"] = kwargs["run_series"]
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.01,
            harness_resolved=True,
            patch_text="diff --git a/x b/x\n",
            patch_source="workspace_diff",
            submitted_patch_path="/tmp/budgetflow-runtime/traces/run-a/trace_sympy__sympy-13480_budgetflow_task_level/submitted.patch",
            workspace_patch_path="/tmp/budgetflow-runtime/traces/run-a/trace_sympy__sympy-13480_budgetflow_task_level/workspace.patch",
            trace_dir="/tmp/budgetflow-runtime/traces/run-a/trace_sympy__sympy-13480_budgetflow_task_level",
            trace_steps_path="/tmp/budgetflow-runtime/traces/run-a/trace_sympy__sympy-13480_budgetflow_task_level/steps.jsonl",
            exit_status="HarnessResolved",
            exit_reason="harness_resolved",
            agent_exit_status="Submitted",
            agent_exit_reason="submitted",
            backend_picks=["tier2"],
            llm_turns=1,
            violations=[],
            harness_detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
            agent_gold_edited=True,
            agent_gold_files=["x.py"],
            agent_attempted_submit=True,
            agent_submitted=True,
            prompt_tokens_total=10,
            completion_tokens_total=2,
            provider_usage_turns=1,
            estimated_usage_turns=0,
            usage_source="provider",
            cost_mode="catalog_provider_usage",
            turn_trace_count=1,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
            protocol="tool_call",
            parser="parse_toolcall_actions",
            provider_error_kind="",
            provider_retryable=None,
        )

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), WorkflowLedgerStore())
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    record = run_task_record(
        task,
        cfg=CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
        value_context=_value_context(),
        run_series="run-a",
    )

    assert seen["run_series"] == "run-a"
    assert "/traces/run-a/" in record["submitted_patch"]
    assert "/traces/run-a/" in record["trace_dir"]
    assert record["trace_steps"].endswith("/steps.jsonl")
    assert record["observability_status"]["trace_steps_path"] == record["trace_steps"]


def test_runner_threads_planned_task_budget_into_allocation_context(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    seen = {}

    def fake_run_mini_swe_task(*args, **kwargs):
        seen["allocation"] = kwargs["allocation"]
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.02,
            harness_resolved=False,
            patch_text="",
            patch_source="none",
            submitted_patch_path="",
            trace_dir="/tmp/trace",
            trace_steps_path="/tmp/trace/steps.jsonl",
            exit_status="Stopped",
            exit_reason="stopped",
            agent_exit_status="Stopped",
            agent_exit_reason="stopped",
            backend_picks=["tier2"],
            llm_turns=1,
            violations=[],
            harness_detail="",
            agent_gold_edited=False,
            agent_gold_files=[],
            agent_attempted_submit=False,
            agent_submitted=False,
            prompt_tokens_total=10,
            completion_tokens_total=2,
            provider_usage_turns=1,
            estimated_usage_turns=0,
            usage_source="provider",
            cost_mode="catalog_provider_usage",
            turn_trace_count=1,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
            protocol="tool_call",
            parser="parse_toolcall_actions",
            provider_error_kind="",
            provider_retryable=None,
        )

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), WorkflowLedgerStore())
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    record = run_task_record(
        task,
        cfg=CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
        value_context=_value_context(),
        budget_mode="budgetflow_planned_task_budget",
        per_task_cap=0.4,
        budget_plan_task_cap=0.8,
        planned_task_budget_source="budget_plan:planned_task_budget_by_strategy",
    )

    assert seen["allocation"].planned_task_budget == 0.8
    assert seen["allocation"].effective_task_budget == 0.4
    assert seen["allocation"].budget_source == "budget_plan:planned_task_budget_by_strategy"
    assert record["budget_mode"] == "budgetflow_planned_task_budget"
    assert record["per_task_cap"] == 0.4
    assert record["budget_plan_task_cap"] == 0.8
    assert record["planned_task_budget_source"] == "budget_plan:planned_task_budget_by_strategy"


def test_run_strategy_batch_planned_caps_prorate_across_remaining_tasks(monkeypatch) -> None:
    import pytest
    from budgetflow.experiments import compare_execution

    seen_caps: list[float] = []
    costs = {"task-a": 0.2, "task-b": 0.8}

    def fake_run_task_record(task, **kwargs):
        task_cap = float(kwargs["per_task_cap"])
        seen_caps.append(task_cap)
        assert kwargs["budget_plan_task_cap"] == 0.8
        return {
            "instance_id": task.instance_id,
            "strategy": kwargs["cfg"].name,
            "routing": kwargs["cfg"].routing,
            "harness_resolved": False,
            "score_status": "true_fail",
            "patch_extracted": False,
            "agent_gold_edited": False,
            "agent_gold_files": [],
            "detail": "",
            "exit_status": "Stopped",
            "exit_reason": "test",
            "elapsed_s": 0.0,
            "backend_picks": ["tier2"],
            "llm_turns": 1,
            "total_cost": costs[task.instance_id],
            "batch_available": None,
        }

    monkeypatch.setattr(compare_execution, "run_task_record", fake_run_task_record)

    records, spent = run_strategy_batch(
        CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        [SimpleNamespace(instance_id="task-a"), SimpleNamespace(instance_id="task-b")],
        batch_budget_cap=1.0,
        value_context=_value_context(),
        planned_task_caps={"task-a": 0.8, "task-b": 0.8},
        budget_mode="budgetflow_planned_task_budget",
        step_limit=1,
        trace_console="quiet",
        heartbeat=0,
        global_progress=SimpleNamespace(
            total=2,
            start_task=lambda: None,
            finish_task=lambda: len(seen_caps),
            format_banner=lambda scoreboard=None: "test",
            format_global=lambda scoreboard=None: "test",
        ),
        scoreboard=None,
        print_lock=None,
    )

    assert seen_caps == pytest.approx([0.5, 0.8])
    assert spent == pytest.approx(1.0)
    assert records[0]["batch_spent"] == pytest.approx(0.2)
    assert records[1]["batch_spent"] == pytest.approx(1.0)
    assert records[1]["batch_available"] == pytest.approx(0.0)


def test_effective_planned_task_cap_protects_remaining_planned_budget() -> None:
    import pytest

    planned = {"task-a": 0.8, "task-b": 0.8, "task-c": 0.8}

    first_cap = _effective_planned_task_cap(
        planned_task_caps=planned,
        remaining_task_ids=["task-a", "task-b", "task-c"],
        task_id="task-a",
        batch_budget_cap=1.2,
        shared_spent=0.0,
    )
    second_cap_after_first_underspends = _effective_planned_task_cap(
        planned_task_caps=planned,
        remaining_task_ids=["task-b", "task-c"],
        task_id="task-b",
        batch_budget_cap=1.2,
        shared_spent=0.1,
    )

    assert first_cap == pytest.approx(0.4)
    assert second_cap_after_first_underspends == pytest.approx(0.55)


def test_planned_task_budget_checkpoint_records_shared_batch_cap(monkeypatch, tmp_path) -> None:
    import pytest
    from budgetflow.experiments import compare_execution

    costs = {"task-a": 0.2, "task-b": 0.3}

    def fake_run_task_record(task, **kwargs):
        return {
            "instance_id": task.instance_id,
            "strategy": kwargs["cfg"].name,
            "routing": kwargs["cfg"].routing,
            "harness_resolved": False,
            "score_status": "true_fail",
            "patch_extracted": False,
            "agent_gold_edited": False,
            "agent_gold_files": [],
            "detail": "",
            "exit_status": "Stopped",
            "exit_reason": "test",
            "elapsed_s": 0.0,
            "backend_picks": ["tier2"],
            "llm_turns": 1,
            "total_cost": costs[task.instance_id],
            "batch_available": None,
        }

    monkeypatch.setattr(compare_execution, "run_task_record", fake_run_task_record)
    checkpoint = CompareCheckpointStore(
        tmp_path / "planned.checkpoint.json",
        stem="planned",
        total_runs=2,
    )

    _records, spent = run_strategy_batch(
        CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        [SimpleNamespace(instance_id="task-a"), SimpleNamespace(instance_id="task-b")],
        batch_budget_cap=1.0,
        value_context=_value_context(),
        planned_task_caps={"task-a": 0.8, "task-b": 0.8},
        budget_mode="budgetflow_planned_task_budget",
        step_limit=1,
        trace_console="quiet",
        heartbeat=0,
        global_progress=SimpleNamespace(
            total=2,
            start_task=lambda: None,
            finish_task=lambda: 1,
            format_banner=lambda scoreboard=None: "test",
            format_global=lambda scoreboard=None: "test",
        ),
        scoreboard=None,
        print_lock=None,
        checkpoint=checkpoint,
    )

    restored = CompareCheckpointStore(
        tmp_path / "planned.checkpoint.json",
        stem="planned",
        total_runs=2,
    )
    strategy_state = restored.strategies["budgetflow_task_level"]
    assert spent == pytest.approx(0.5)
    assert strategy_state.batch_cap == pytest.approx(1.0)
    assert strategy_state.batch_spent == pytest.approx(0.5)
    assert strategy_state.completed_tasks == ["task-a", "task-b"]


def test_checkpoint_does_not_mark_abort_rows_completed(monkeypatch, tmp_path) -> None:
    from budgetflow.experiments import compare_execution

    def fake_run_task_record(task, **kwargs):
        return {
            "instance_id": task.instance_id,
            "strategy": kwargs["cfg"].name,
            "routing": kwargs["cfg"].routing,
            "harness_resolved": False,
            "score_status": "abort",
            "abort_reason": "provider_or_infra_error",
            "patch_extracted": False,
            "agent_gold_edited": False,
            "agent_gold_files": [],
            "detail": "",
            "exit_status": "UpstreamExit",
            "exit_reason": "billing_guard",
            "elapsed_s": 0.0,
            "backend_picks": ["tier2"],
            "llm_turns": 1,
            "total_cost": 0.2,
            "batch_available": None,
        }

    monkeypatch.setattr(compare_execution, "run_task_record", fake_run_task_record)
    checkpoint = CompareCheckpointStore(
        tmp_path / "abort.checkpoint.json",
        stem="abort",
        total_runs=1,
    )

    run_strategy_batch(
        CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        [SimpleNamespace(instance_id="task-a")],
        batch_budget_cap=1.0,
        value_context=_value_context(),
        planned_task_caps={"task-a": 0.8},
        budget_mode="budgetflow_planned_task_budget",
        step_limit=1,
        trace_console="quiet",
        heartbeat=0,
        global_progress=SimpleNamespace(
            total=1,
            start_task=lambda: None,
            finish_task=lambda: 1,
            format_banner=lambda scoreboard=None: "test",
            format_global=lambda scoreboard=None: "test",
        ),
        scoreboard=None,
        print_lock=None,
        checkpoint=checkpoint,
    )

    restored = CompareCheckpointStore(
        tmp_path / "abort.checkpoint.json",
        stem="abort",
        total_runs=1,
    )
    strategy_state = restored.strategies["budgetflow_task_level"]
    assert strategy_state.in_flight_task is None
    assert strategy_state.batch_spent == 0.0
    assert strategy_state.completed_tasks == []


def test_effective_planned_task_cap_rebalances_against_remaining_planned_demand() -> None:
    import pytest

    planned = {"task-a": 0.8, "task-b": 0.8, "task-c": 0.8}

    first_cap = _effective_planned_task_cap(
        planned_task_caps=planned,
        remaining_task_ids=["task-a", "task-b", "task-c"],
        task_id="task-a",
        batch_budget_cap=1.2,
        shared_spent=0.0,
    )
    later_cap = _effective_planned_task_cap(
        planned_task_caps=planned,
        remaining_task_ids=["task-b", "task-c"],
        task_id="task-b",
        batch_budget_cap=1.2,
        shared_spent=0.1,
    )

    final_cap = _effective_planned_task_cap(
        planned_task_caps=planned,
        remaining_task_ids=["task-c"],
        task_id="task-c",
        batch_budget_cap=1.2,
        shared_spent=0.7,
    )

    assert first_cap == pytest.approx(0.4)
    assert later_cap == pytest.approx(0.55)
    assert final_cap == pytest.approx(0.5)


def test_planned_task_budget_uses_shared_batch_pressure() -> None:
    assert _shared_batch_pressure(
        batch_budget_cap=10.0,
        shared_spent=0.0,
        init=0.01,
        pressure_max=1.0,
    ) == pytest.approx(0.01)
    assert _shared_batch_pressure(
        batch_budget_cap=10.0,
        shared_spent=5.0,
        init=0.01,
        pressure_max=1.0,
    ) == pytest.approx(0.505)
    assert _shared_batch_pressure(
        batch_budget_cap=10.0,
        shared_spent=20.0,
        init=0.01,
        pressure_max=1.0,
    ) == pytest.approx(1.0)


def test_run_strategy_batch_planned_caps_require_all_selected_tasks() -> None:
    import pytest

    with pytest.raises(SystemExit, match="missing planned task budgets"):
        run_strategy_batch(
            CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
            [SimpleNamespace(instance_id="task-a"), SimpleNamespace(instance_id="task-b")],
            batch_budget_cap=1.0,
            value_context=_value_context(),
            planned_task_caps={"task-a": 0.8},
            budget_mode="budgetflow_planned_task_budget",
            step_limit=1,
            trace_console="quiet",
            heartbeat=0,
            global_progress=SimpleNamespace(
                total=2,
                start_task=lambda: None,
                finish_task=lambda: 0,
                format_banner=lambda scoreboard=None: "test",
                format_global=lambda scoreboard=None: "test",
            ),
            scoreboard=None,
            print_lock=None,
        )


def test_run_strategy_batch_planned_mode_requires_cap_map() -> None:
    import pytest

    with pytest.raises(SystemExit, match="no planned task budgets"):
        run_strategy_batch(
            CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
            [SimpleNamespace(instance_id="task-a")],
            batch_budget_cap=1.0,
            value_context=_value_context(),
            planned_task_caps={},
            budget_mode="budgetflow_planned_task_budget",
            step_limit=1,
            trace_console="quiet",
            heartbeat=0,
            global_progress=SimpleNamespace(
                total=1,
                start_task=lambda: None,
                finish_task=lambda: 0,
                format_banner=lambda scoreboard=None: "test",
                format_global=lambda scoreboard=None: "test",
            ),
            scoreboard=None,
            print_lock=None,
        )


def test_runner_does_not_use_repo_policy_memory_as_model_fit(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    seen = {}

    def fake_run_mini_swe_task(*args, **kwargs):
        seen["allocation"] = kwargs["allocation"]
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.01,
            harness_resolved=False,
            patch_text="",
            patch_source="none",
            submitted_patch_path="",
            trace_dir="/tmp/trace",
            trace_steps_path="/tmp/trace/steps.jsonl",
            exit_status="Stopped",
            exit_reason="budget_exhausted",
            agent_exit_status="Stopped",
            agent_exit_reason="budget_exhausted",
            backend_picks=["tier2"],
            llm_turns=1,
            violations=[],
            harness_detail="",
            agent_gold_edited=False,
            agent_gold_files=[],
            agent_attempted_submit=False,
            agent_submitted=False,
            prompt_tokens_total=10,
            completion_tokens_total=2,
            provider_usage_turns=1,
            estimated_usage_turns=0,
            usage_source="provider",
            cost_mode="catalog_provider_usage",
            turn_trace_count=1,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
            protocol="tool_call",
            parser="parse_toolcall_actions",
            provider_error_kind="",
            provider_retryable=None,
        )

    class _RepoPrior:
        tier_success_rate = {2: 0.05, 3: 0.90}

    class _PolicyMemory:
        memory_filtering_summary = {}

        def repo_prior(self, instance_id):
            return _RepoPrior()

        def routing_prior_summary(self, instance_id, segment=None):
            return {"policy_memory_source": "memory.jsonl"}

    class _Registry:
        policy_memory = _PolicyMemory()
        memory_mode = "built_in"
        learn_policy_inputs = SimpleNamespace(active_views=[])

        def for_strategy(self, name, routing):
            return None

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), WorkflowLedgerStore())
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    record = run_task_record(
        task,
        cfg=CompareStrategy("budgetflow_task_level", "value_aware_task_level"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
        value_context=_value_context(),
        adaptive_registry=_Registry(),
    )

    assert seen["allocation"].model_fit is None
    assert seen["allocation"].model_fit_source == "catalog_progress_prior"
    assert record["model_fit_source"] == "catalog_progress_prior"


def test_runner_marks_pre_provider_budget_block_cost_source() -> None:
    import budgetflow.adapter.runner as runner

    model = SimpleNamespace(_provider_usage_turns=0, _estimated_usage_turns=0)

    usage_source, cost_mode = runner._row_cost_observability(model, 0.0)

    assert usage_source == "none"
    assert cost_mode == "no_provider_call"


def test_runner_labels_resolved_harness_as_resolved_even_after_submission() -> None:
    import budgetflow.adapter.runner as runner

    status, reason = runner._harness_exit_label(
        agent_exit_status="Submitted",
        agent_exit_reason="submitted",
        harness_resolved=True,
        patch_text="diff --git a/x b/x\n",
        harness_detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
    )

    assert status == "HarnessResolved"
    assert reason == "harness_resolved"


def test_runner_labels_complete_unresolved_patch_as_harness_failed() -> None:
    import budgetflow.adapter.runner as runner

    status, reason = runner._harness_exit_label(
        agent_exit_status="Submitted",
        agent_exit_reason="submitted",
        harness_resolved=False,
        patch_text="diff --git a/x b/x\n",
        harness_detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
    )

    assert status == "HarnessFailed"
    assert reason == "harness_failed"


def test_runner_preserves_agent_exit_when_harness_did_not_complete() -> None:
    import budgetflow.adapter.runner as runner

    status, reason = runner._harness_exit_label(
        agent_exit_status="BudgetFlowBudgetError",
        agent_exit_reason="budget_exhausted",
        harness_resolved=False,
        patch_text=None,
        harness_detail="",
    )

    assert status == "BudgetFlowBudgetError"
    assert reason == "budget_exhausted"


def test_rebuild_state_ignores_current_schema_missing_score_status(tmp_path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(
        json.dumps(_record(score_status="pass", harness_resolved=True)) + "\n"
        + json.dumps(_record(instance_id="sympy__sympy-old", harness_resolved=True, score_status="")) + "\n"
    )

    state = rebuild_state_from_jsonl(
        path,
        [],
        normalize_strategy=lambda name: name,
        enrich_value=lambda record: record,
    )

    assert state.runs_done == 1
    assert state.score_status_by_strategy["budgetflow_segment"] == ["pass"]


def test_completed_keys_excludes_abort_rows(tmp_path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(
        json.dumps(_record(instance_id="task-pass", score_status="pass")) + "\n"
        + json.dumps(_record(instance_id="task-abort", score_status="abort", harness_resolved=False)) + "\n"
    )

    keys = completed_keys(path, normalize_strategy=lambda name: name)

    assert ("budgetflow_segment", "task-pass") in keys
    assert ("budgetflow_segment", "task-abort") not in keys


def test_completed_keys_keeps_success_after_bad_provider_retry(tmp_path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(
        json.dumps(_record(instance_id="task-a", score_status="abort", exit_status="BadRequestError", total_cost=0.0, llm_turns=0))
        + "\n"
        + json.dumps(_record(instance_id="task-a", score_status="pass", exit_status="Submitted", total_cost=0.2, llm_turns=3))
        + "\n"
    )

    keys = completed_keys(path, normalize_strategy=lambda name: name, skip_bad=True)

    assert keys == {("budgetflow_segment", "task-a")}


def test_persisted_jsonl_contains_t1_t2_observability(tmp_path) -> None:
    out_path = tmp_path / "out.jsonl"
    ctx = _value_context()
    record = _record()

    with out_path.open("w") as handle:
        persist_task_record(
            _state(),
            record,
            handle=handle,
            io_lock=threading.Lock(),
            total_runs=1,
            tasks_per_strategy=1,
            global_progress=GlobalRunProgress(1),
            scoreboard=None,
            summary_path=tmp_path / "summary.log",
            strategy_names=["budgetflow_segment"],
            batch_caps={"budgetflow_segment": 0.5},
            budget_modes={"budgetflow_segment": "per_task_cap"},
            started=0.0,
            out_path=out_path,
            value_profile="equal",
            enrich_value=ctx.enrich_record,
        )

    persisted = json.loads(out_path.read_text().splitlines()[0])

    assert persisted["llm_turns"] == 2
    assert persisted["value_objective"] == "t2_value_source_diagnostic"
    assert persisted["task_value_source_class"] == "equal_sanity"
    assert persisted["task_value_primary_t1"] is False
    assert persisted["yield_per_dollar"] == 4.0
    assert persisted["routing_policy_family"] == "bootstrap:value_aware_segment"
    assert persisted["policy_kind"] == "bootstrap"
    assert persisted["routing_learned_action"] == "early_rescue"
    assert persisted["routing_policy_memory_source"].endswith("066_postfix_3x3.jsonl")


def test_budget_summary_reports_planned_cap_not_provider_runtime_balance() -> None:
    lines = _format_strategy_totals(
        strategy_names=["budgetflow_segment"],
        resolved_by_strategy={"budgetflow_segment": [True, False]},
        score_status_by_strategy={"budgetflow_segment": ["pass", "true_fail"]},
        task_cost_by_strategy={"budgetflow_segment": [0.2, 0.3]},
        batch_spent_by_strategy={"budgetflow_segment": 0.5},
        turns_by_strategy={"budgetflow_segment": [3, 7]},
        tier_mix_by_strategy={"budgetflow_segment": [{2: 0.5, 5: 0.5}, {5: 1.0}]},
        failure_by_strategy={"budgetflow_segment": {"pass": 1, "repair_fail": 1}},
        batch_caps={"budgetflow_segment": 1.5},
        budget_modes={"budgetflow_segment": "per_task_cap"},
    )

    text = "\n".join(lines)
    assert "per-task cap" in text
    assert "3.00" in text
    assert "T5=75%" in text
    assert "100.00" not in text


def test_live_snapshot_uses_score_status_for_value_pass_count(tmp_path) -> None:
    lines = _format_live_snapshot(
        strategy_names=["budgetflow_segment"],
        resolved_by_strategy={"budgetflow_segment": [True, True]},
        score_status_by_strategy={"budgetflow_segment": ["pass", "abort"]},
        task_cost_by_strategy={"budgetflow_segment": [0.2, 0.1]},
        turns_by_strategy={"budgetflow_segment": [4, 3]},
        tier_mix_by_strategy={"budgetflow_segment": [{2: 1.0}, {5: 1.0}]},
        batch_spent_by_strategy={"budgetflow_segment": 0.3},
        batch_caps={"budgetflow_segment": 0.5},
        budget_modes={"budgetflow_segment": "per_task_cap"},
        runs_done=2,
        total_runs=2,
        tasks_per_strategy=2,
        started=0.0,
        out_path=tmp_path / "run.jsonl",
        resolved_value_by_strategy={"budgetflow_segment": [0.6, 0.0]},
        task_value_by_strategy={"budgetflow_segment": [0.6, 0.4]},
        value_profile="difficulty",
    )

    text = "\n".join(lines)
    assert "pass=1 true_fail=0 abort=1" in text
    assert any(line.startswith("budgetflow_segment") and " 1 " in line for line in lines)
    assert "planned_cap" in text


def test_scoreboard_records_abort_by_score_status_not_raw_harness_resolved() -> None:
    scoreboard = StrategyScoreboard(["budgetflow_segment"])
    scoreboard.record("budgetflow_segment", resolved=True, score_status="abort")
    scoreboard.record("budgetflow_segment", resolved=True, score_status="pass")

    assert "bf-segment 1/2" in scoreboard.format_line()


def test_scoreboard_resume_seed_uses_score_status() -> None:
    scoreboard = StrategyScoreboard(["budgetflow_segment"])
    scoreboard.seed_from_resolved(
        {"budgetflow_segment": [True, True, False]},
        {"budgetflow_segment": ["pass", "abort", "true_fail"]},
    )

    assert "bf-segment 1/3" in scoreboard.format_line()


def test_value_summary_reports_primary_normalized_value_metric(tmp_path) -> None:
    lines = _format_live_snapshot(
        strategy_names=["budgetflow_segment"],
        resolved_by_strategy={"budgetflow_segment": [True, False]},
        score_status_by_strategy={"budgetflow_segment": ["pass", "abort"]},
        task_cost_by_strategy={"budgetflow_segment": [0.2, 0.1]},
        turns_by_strategy={"budgetflow_segment": [4, 3]},
        tier_mix_by_strategy={"budgetflow_segment": [{2: 1.0}, {5: 1.0}]},
        batch_spent_by_strategy={"budgetflow_segment": 0.3},
        batch_caps={"budgetflow_segment": 0.5},
        budget_modes={"budgetflow_segment": "shared_batch_hard_budget"},
        runs_done=2,
        total_runs=2,
        tasks_per_strategy=2,
        started=0.0,
        out_path=tmp_path / "run.jsonl",
        resolved_value_by_strategy={"budgetflow_segment": [0.6, 0.0]},
        task_value_by_strategy={"budgetflow_segment": [0.6, 0.4]},
        value_profile="difficulty",
    )

    text = "\n".join(lines)
    assert "Yield" in text
    assert "Yield/$" in text
    assert "0.60" in text
    assert "3.00" in text
    assert "abort=1" in text


def test_live_snapshot_warns_when_task_level_underuses_t3_against_strong_baseline(tmp_path) -> None:
    lines = _format_live_snapshot(
        strategy_names=["bare_t2_baseline", "bare_t3_baseline", "budgetflow_task_level"],
        resolved_by_strategy={
            "bare_t2_baseline": [True, False, False, False],
            "bare_t3_baseline": [True, True, True, True],
            "budgetflow_task_level": [True, False, False, False],
        },
        score_status_by_strategy={
            "bare_t2_baseline": ["pass", "true_fail", "true_fail", "true_fail"],
            "bare_t3_baseline": ["pass", "pass", "pass", "pass"],
            "budgetflow_task_level": ["pass", "true_fail", "true_fail", "true_fail"],
        },
        task_cost_by_strategy={
            "bare_t2_baseline": [0.1, 0.1, 0.1, 0.1],
            "bare_t3_baseline": [0.2, 0.2, 0.2, 0.2],
            "budgetflow_task_level": [0.1, 0.1, 0.1, 0.1],
        },
        turns_by_strategy={
            "bare_t2_baseline": [10, 10, 10, 10],
            "bare_t3_baseline": [5, 5, 5, 5],
            "budgetflow_task_level": [10, 10, 10, 10],
        },
        tier_mix_by_strategy={
            "bare_t2_baseline": [{2: 1.0}] * 4,
            "bare_t3_baseline": [{3: 1.0}] * 4,
            "budgetflow_task_level": [{2: 1.0}] * 4,
        },
        batch_spent_by_strategy={
            "bare_t2_baseline": 0.4,
            "bare_t3_baseline": 0.8,
            "budgetflow_task_level": 0.4,
        },
        batch_caps={
            "bare_t2_baseline": 1.0,
            "bare_t3_baseline": 1.0,
            "budgetflow_task_level": 1.0,
        },
        budget_modes={
            "bare_t2_baseline": "shared_batch_hard_budget",
            "bare_t3_baseline": "shared_batch_hard_budget",
            "budgetflow_task_level": "budgetflow_planned_task_budget",
        },
        runs_done=12,
        total_runs=12,
        tasks_per_strategy=4,
        started=0.0,
        out_path=tmp_path / "run.jsonl",
    )

    text = "\n".join(lines)
    assert "CALIBRATION WARNING" in text
    assert "BudgetFlow task-level used T3 on 0%" in text
    assert "bare_t3_baseline pass rate 100%" in text


def test_append_summary_omits_heavy_runtime_payloads() -> None:
    lines: list[str] = []
    record = _record(
        turn_traces=[{"step": 1, "assistant_content_head": "large"}],
        turn_trace_count=1,
        budget_plan={"projected_task_cost_by_strategy": {"s": {"task": 1.0}}},
        detail="x" * 1000,
    )

    _append_summary(lines, record, index=1, total=1)

    payload = json.loads(lines[-2])
    assert "turn_traces" not in payload
    assert "budget_plan" not in payload
    assert "detail" not in payload
    assert payload["turn_trace_count"] == record.get("turn_trace_count", 0)
    assert payload["strategy"] == "budgetflow_segment"

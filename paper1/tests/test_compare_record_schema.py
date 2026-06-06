import threading
from types import SimpleNamespace

from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.run_mini_swe_compare import (
    CompareStrategy,
    GlobalRunProgress,
    _CompareState,
    _format_strategy_totals,
    _ingest_batch_footer,
    _run_one,
)


def test_run_one_records_turns_alias(monkeypatch):
    import budgetflow.adapter.runner as runner

    def fake_run_mini_swe_task(*args, **kwargs):
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.01,
            harness_resolved=True,
            patch_text="diff --git a/x b/x\n",
            patch_source="submission",
            submitted_patch_path="/tmp/submitted.patch",
            exit_status="Submitted",
            exit_reason="submitted",
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
            turn_trace_count=2,
            turn_traces=[],
        )

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    task = SimpleNamespace(instance_id="sympy__sympy-13480")
    governor = BudgetGovernor(
        GovernorConfig(total_budget=1.0, default_max_output_tokens=4096),
        WorkflowLedgerStore(),
    )

    record = _run_one(
        task,
        cfg=CompareStrategy("budget_only_tight", "budget_only", "tight"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
    )

    assert record["llm_turns"] == 2
    assert record["turns"] == 2


def test_per_task_cap_summary_uses_total_planned_cap():
    lines = _format_strategy_totals(
        strategy_names=["budgetflow_value_aware_tight"],
        resolved_by_strategy={"budgetflow_value_aware_tight": [True, True, True]},
        task_cost_by_strategy={"budgetflow_value_aware_tight": [0.2, 0.2, 0.2]},
        batch_spent_by_strategy={"budgetflow_value_aware_tight": 0.6},
        turns_by_strategy={"budgetflow_value_aware_tight": [3, 4, 5]},
        spark_by_strategy={"budgetflow_value_aware_tight": [0.0, 0.0, 0.0]},
        flash_by_strategy={"budgetflow_value_aware_tight": [0.7, 0.7, 0.7]},
        pro_by_strategy={"budgetflow_value_aware_tight": [0.3, 0.3, 0.3]},
        failure_by_strategy={"budgetflow_value_aware_tight": {"pass": 3}},
        batch_caps={"budgetflow_value_aware_tight": 0.5},
        budget_modes={"budgetflow_value_aware_tight": "per_task_cap"},
    )

    text = "\n".join(lines)
    assert "per-task cap" in text
    assert "1.50" in text
    assert "OVER_CAP" not in text


def test_per_task_cap_batch_footer_uses_per_task_cap_not_shared_cap(tmp_path):
    state = _CompareState(
        summary_lines=[],
        resolved_by_strategy={"budgetflow_value_aware_tight": [True]},
        task_cost_by_strategy={"budgetflow_value_aware_tight": [0.2]},
        batch_spent_by_strategy={"budgetflow_value_aware_tight": 0.2},
        turns_by_strategy={"budgetflow_value_aware_tight": [3]},
        spark_by_strategy={"budgetflow_value_aware_tight": [0.0]},
        flash_by_strategy={"budgetflow_value_aware_tight": [1.0]},
        pro_by_strategy={"budgetflow_value_aware_tight": [0.0]},
        failure_by_strategy={"budgetflow_value_aware_tight": {"pass": 1}},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )
    summary_path = tmp_path / "summary.log"

    _ingest_batch_footer(
        state,
        CompareStrategy("budgetflow_value_aware_tight", "budgetflow_value_aware", "tight"),
        [{"harness_resolved": True}],
        batch_spent=0.2,
        batch_cap=100.0,
        strategy_names=["budgetflow_value_aware_tight"],
        batch_caps={"budgetflow_value_aware_tight": 0.5},
        budget_modes={"budgetflow_value_aware_tight": "per_task_cap"},
        summary_path=summary_path,
        started=0.0,
        out_path=tmp_path / "out.jsonl",
        total_runs=1,
        tasks_per_strategy=1,
        io_lock=threading.Lock(),
        global_progress=GlobalRunProgress(1),
    )

    text = summary_path.read_text()
    assert "per_task_cap=0.5000" in text
    assert "per_task_cap=100.00" not in text

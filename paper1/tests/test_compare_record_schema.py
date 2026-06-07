import json
import threading
from types import SimpleNamespace

from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.run_mini_swe_compare import (
    GlobalRunProgress,
    _enrich_record_with_value,
    _run_one,
)
from budgetflow.experiments.compare_artifacts import (
    CompareRunState,
    ingest_batch_footer,
    persist_task_record,
)
from budgetflow.experiments.compare_summary import _format_strategy_totals
from budgetflow.auto_budget import AutoBudgetMemory


def _persist_kwargs() -> dict:
    return {"value_profile": "equal", "enrich_value": _enrich_record_with_value}


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
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=(),
        pass_to_pass=(),
    )
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
    assert record["harness_resolved"] is True
    assert record["resolved"] is True
    assert record["task_features"]["patch_lines"] == 1
    assert record["task_features"]["f2p_count"] == 0
    assert record["task_features"]["p2p_count"] == 0


def test_persist_task_record_writes_learning_memory_for_normal_run(tmp_path):
    state = CompareRunState(
        summary_lines=[],
        resolved_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        spark_by_strategy={},
        flash_by_strategy={},
        pro_by_strategy={},
        failure_by_strategy={},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )
    record = {
        "instance_id": "sympy__sympy-14774",
        "strategy": "budget_only_tight",
        "routing": "budget_only",
        "harness_resolved": True,
        "patch_extracted": True,
        "agent_gold_edited": True,
        "agent_gold_files": ["sympy/printing/latex.py"],
        "llm_turns": 2,
        "turns": 2,
        "task_cost": 0.01,
        "total_cost": 0.01,
        "batch_spent": 0.01,
        "backend_picks": ["tier2"],
        "failure_class": "pass",
        "forensic_summary": {"primary_axis": "pass"},
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
        "task_features": {"patch_lines": 12, "f2p_count": 1, "p2p_count": 114, "problem_length": 500},
        "run_series": "061_schema_test",
        "attempt_id": "061_schema_test_budget_only_tight_sympy__sympy-14774",
    }
    memory_path = tmp_path / "learning.jsonl"
    memory = AutoBudgetMemory(memory_path)

    with (tmp_path / "out.jsonl").open("w") as handle:
        persist_task_record(
            state,
            record,
            handle=handle,
            io_lock=threading.Lock(),
            total_runs=1,
            tasks_per_strategy=1,
            global_progress=GlobalRunProgress(1),
            scoreboard=None,
            summary_path=tmp_path / "summary.log",
            strategy_names=["budget_only_tight"],
            batch_caps={"budget_only_tight": 0.5},
            budget_modes={"budget_only_tight": "per_task_cap"},
            started=0.0,
            out_path=tmp_path / "out.jsonl",
            **_persist_kwargs(),
            auto_budget_memory=memory,
            no_auto_budget_learn=False,
        )

    assert record["budget_learning_update_written"] is True
    assert record["budget_learning_applied_to_cap"] is False
    learned = AutoBudgetMemory(memory_path).records
    assert len(learned) == 1
    assert learned[0]["patch_lines"] == 12
    assert learned[0]["f2p_count"] == 1
    assert learned[0]["run_series"] == "061_schema_test"
    assert learned[0]["run_id"] == "061_schema_test_budget_only_tight_sympy__sympy-14774"


def test_persist_task_record_writes_value_and_routing_schema(tmp_path):
    state = CompareRunState(
        summary_lines=[],
        resolved_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        spark_by_strategy={},
        flash_by_strategy={},
        pro_by_strategy={},
        failure_by_strategy={},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )
    record = {
        "instance_id": "sympy__sympy-14774",
        "strategy": "budgetflow_value_aware_tight",
        "routing": "budgetflow_value_aware",
        "harness_resolved": True,
        "patch_extracted": True,
        "agent_gold_edited": True,
        "agent_gold_files": ["sympy/printing/latex.py"],
        "llm_turns": 2,
        "turns": 2,
        "task_cost": 0.25,
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
        "run_series": "067_schema_test",
        "attempt_id": "067_schema_test_budgetflow_value_aware_tight_sympy__sympy-14774",
    }
    out_path = tmp_path / "out.jsonl"
    with out_path.open("w") as handle:
        persist_task_record(
            state,
            record,
            handle=handle,
            io_lock=threading.Lock(),
            total_runs=1,
            tasks_per_strategy=1,
            global_progress=GlobalRunProgress(1),
            scoreboard=None,
            summary_path=tmp_path / "summary.log",
            strategy_names=["budgetflow_value_aware_tight"],
            batch_caps={"budgetflow_value_aware_tight": 0.5},
            budget_modes={"budgetflow_value_aware_tight": "per_task_cap"},
            started=0.0,
            out_path=out_path,
            **_persist_kwargs(),
        )

    persisted = json.loads(out_path.read_text().splitlines()[0])
    assert persisted["value_objective"] == "t2_equal_value_ablation"
    assert persisted["task_value"] == 1.0
    assert persisted["resolved_value_per_dollar"] == 4.0
    assert persisted["routing_objective"] == "t2_equal_value_ablation"
    assert persisted["routing_policy_family"] == "bfv_equal_value_ablation"
    assert persisted["routing_learned_action"] == "early_rescue"
    assert persisted["routing_policy_memory_source"].endswith("066_postfix_3x3.jsonl")
    assert persisted["routing_decision_schema"] == "v1"


def test_persist_task_record_accumulates_strategy_spend_for_live_summary(tmp_path):
    state = CompareRunState(
        summary_lines=[],
        resolved_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        spark_by_strategy={},
        flash_by_strategy={},
        pro_by_strategy={},
        failure_by_strategy={},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )
    base_record = {
        "strategy": "budgetflow_value_aware_tight",
        "routing": "budgetflow_value_aware",
        "harness_resolved": True,
        "patch_extracted": True,
        "agent_gold_edited": True,
        "agent_gold_files": ["x.py"],
        "llm_turns": 2,
        "turns": 2,
        "backend_picks": ["tier2"],
        "failure_class": "pass",
        "forensic_summary": {"primary_axis": "pass"},
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
        "task_features": {"patch_lines": 12, "f2p_count": 1, "p2p_count": 1, "problem_length": 500},
        "run_series": "summary_accumulation",
    }
    records = [
        {
            **base_record,
            "instance_id": "sympy__sympy-14774",
            "task_cost": 0.10,
            "total_cost": 0.10,
            "batch_spent": 0.10,
            "attempt_id": "summary_accumulation_budgetflow_value_aware_tight_sympy__sympy-14774",
        },
        {
            **base_record,
            "instance_id": "sympy__sympy-16988",
            "task_cost": 0.25,
            "total_cost": 0.25,
            "batch_spent": 0.25,
            "attempt_id": "summary_accumulation_budgetflow_value_aware_tight_sympy__sympy-16988",
        },
    ]

    progress = GlobalRunProgress(2)
    progress.start_task()
    progress.finish_task()
    progress.start_task()
    progress.finish_task()
    with (tmp_path / "out.jsonl").open("w") as handle:
        for record in records:
            persist_task_record(
                state,
                record,
                handle=handle,
                io_lock=threading.Lock(),
                total_runs=2,
                tasks_per_strategy=2,
                global_progress=progress,
                scoreboard=None,
                summary_path=tmp_path / "summary.log",
                strategy_names=["budgetflow_value_aware_tight"],
                batch_caps={"budgetflow_value_aware_tight": 1.0},
                budget_modes={"budgetflow_value_aware_tight": "per_task_cap"},
                started=0.0,
                out_path=tmp_path / "out.jsonl",
                **_persist_kwargs(),
            )

    assert state.task_cost_by_strategy["budgetflow_value_aware_tight"] == [0.10, 0.25]
    assert state.batch_spent_by_strategy["budgetflow_value_aware_tight"] == 0.35
    text = (tmp_path / "summary.log").read_text()
    assert "budgetflow_value_aware_tight" in text
    assert text.count("0.3500") >= 2


def test_persist_task_record_can_disable_learning_write(tmp_path):
    state = CompareRunState(
        summary_lines=[],
        resolved_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        spark_by_strategy={},
        flash_by_strategy={},
        pro_by_strategy={},
        failure_by_strategy={},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )
    record = {
        "instance_id": "sympy__sympy-14774",
        "strategy": "budget_only_tight",
        "routing": "budget_only",
        "harness_resolved": True,
        "patch_extracted": True,
        "agent_gold_edited": True,
        "agent_gold_files": [],
        "llm_turns": 1,
        "turns": 1,
        "task_cost": 0.01,
        "total_cost": 0.01,
        "batch_spent": 0.01,
        "backend_picks": ["tier2"],
        "failure_class": "pass",
        "forensic_summary": {"primary_axis": "pass"},
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
        "task_features": {"patch_lines": 1, "f2p_count": 1, "p2p_count": 1, "problem_length": 1},
    }
    memory_path = tmp_path / "learning.jsonl"
    memory = AutoBudgetMemory(memory_path)

    with (tmp_path / "out.jsonl").open("w") as handle:
        persist_task_record(
            state,
            record,
            handle=handle,
            io_lock=threading.Lock(),
            total_runs=1,
            tasks_per_strategy=1,
            global_progress=GlobalRunProgress(1),
            scoreboard=None,
            summary_path=tmp_path / "summary.log",
            strategy_names=["budget_only_tight"],
            batch_caps={"budget_only_tight": 0.5},
            budget_modes={"budget_only_tight": "per_task_cap"},
            started=0.0,
            out_path=tmp_path / "out.jsonl",
            **_persist_kwargs(),
            auto_budget_memory=memory,
            no_auto_budget_learn=True,
        )

    assert record["budget_learning_update_written"] is False
    assert record["budget_learning_memory_path"] == str(memory_path)
    assert record["budget_learning_applied_to_cap"] is False
    assert not memory_path.exists()


def test_persist_task_record_marks_learning_unavailable_without_memory(tmp_path):
    state = CompareRunState(
        summary_lines=[],
        resolved_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        spark_by_strategy={},
        flash_by_strategy={},
        pro_by_strategy={},
        failure_by_strategy={},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )
    record = {
        "instance_id": "sympy__sympy-14774",
        "strategy": "budget_only_tight",
        "routing": "budget_only",
        "harness_resolved": True,
        "patch_extracted": True,
        "agent_gold_edited": True,
        "agent_gold_files": [],
        "llm_turns": 1,
        "turns": 1,
        "task_cost": 0.01,
        "total_cost": 0.01,
        "batch_spent": 0.01,
        "backend_picks": ["tier2"],
        "failure_class": "pass",
        "forensic_summary": {"primary_axis": "pass"},
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
        "task_features": {"patch_lines": 1, "f2p_count": 1, "p2p_count": 1, "problem_length": 1},
    }

    with (tmp_path / "out.jsonl").open("w") as handle:
        persist_task_record(
            state,
            record,
            handle=handle,
            io_lock=threading.Lock(),
            total_runs=1,
            tasks_per_strategy=1,
            global_progress=GlobalRunProgress(1),
            scoreboard=None,
            summary_path=tmp_path / "summary.log",
            strategy_names=["budget_only_tight"],
            batch_caps={"budget_only_tight": 0.5},
            budget_modes={"budget_only_tight": "per_task_cap"},
            started=0.0,
            out_path=tmp_path / "out.jsonl",
            **_persist_kwargs(),
            auto_budget_memory=None,
            no_auto_budget_learn=True,
        )

    assert record["budget_learning_update_written"] is False
    assert record["budget_learning_memory_path"] == ""
    assert record["budget_learning_applied_to_cap"] is False


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


def test_auto_budget_summary_uses_dynamic_task_caps():
    lines = _format_strategy_totals(
        strategy_names=["budgetflow_value_aware_tight"],
        resolved_by_strategy={"budgetflow_value_aware_tight": [True, True, False]},
        task_cost_by_strategy={"budgetflow_value_aware_tight": [0.05, 0.20, 0.10]},
        batch_spent_by_strategy={"budgetflow_value_aware_tight": 0.35},
        turns_by_strategy={"budgetflow_value_aware_tight": [3, 10, 5]},
        spark_by_strategy={"budgetflow_value_aware_tight": [0.0, 0.0, 0.0]},
        flash_by_strategy={"budgetflow_value_aware_tight": [0.7, 0.7, 0.7]},
        pro_by_strategy={"budgetflow_value_aware_tight": [0.3, 0.3, 0.3]},
        failure_by_strategy={"budgetflow_value_aware_tight": {"pass": 2, "repair_fail": 1}},
        batch_caps={"budgetflow_value_aware_tight": 1.507436646551724},
        budget_modes={"budgetflow_value_aware_tight": "dynamic_task_caps"},
    )

    text = "\n".join(lines)
    assert "per-task cap" in text
    assert "1.51" in text
    assert "100.00" not in text


def test_per_task_cap_batch_footer_uses_per_task_cap_not_shared_cap(tmp_path):
    state = CompareRunState(
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

    ingest_batch_footer(
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
        value_profile="equal",
    )

    text = summary_path.read_text()
    assert "per_task_cap=0.5000" in text
    assert "per_task_cap=100.00" not in text


def test_dynamic_task_caps_batch_footer_uses_planned_remaining(tmp_path):
    state = CompareRunState(
        summary_lines=[],
        resolved_by_strategy={"budgetflow_value_aware_tight": [True, False]},
        task_cost_by_strategy={"budgetflow_value_aware_tight": [0.2, 0.3]},
        batch_spent_by_strategy={"budgetflow_value_aware_tight": 0.5},
        turns_by_strategy={"budgetflow_value_aware_tight": [3, 7]},
        spark_by_strategy={"budgetflow_value_aware_tight": [0.0, 0.0]},
        flash_by_strategy={"budgetflow_value_aware_tight": [1.0, 1.0]},
        pro_by_strategy={"budgetflow_value_aware_tight": [0.0, 0.0]},
        failure_by_strategy={"budgetflow_value_aware_tight": {"pass": 1, "repair_fail": 1}},
        resolved_value_by_strategy={},
        task_value_by_strategy={},
    )
    summary_path = tmp_path / "summary.log"

    ingest_batch_footer(
        state,
        CompareStrategy("budgetflow_value_aware_tight", "budgetflow_value_aware", "tight"),
        [
            {"harness_resolved": True, "batch_available": 0.3},
            {"harness_resolved": False, "batch_available": 0.7},
        ],
        batch_spent=0.5,
        batch_cap=100.0,
        strategy_names=["budgetflow_value_aware_tight"],
        batch_caps={"budgetflow_value_aware_tight": 1.5},
        budget_modes={"budgetflow_value_aware_tight": "dynamic_task_caps"},
        summary_path=summary_path,
        started=0.0,
        out_path=tmp_path / "out.jsonl",
        total_runs=2,
        tasks_per_strategy=2,
        io_lock=threading.Lock(),
        global_progress=GlobalRunProgress(2),
        value_profile="equal",
    )

    text = summary_path.read_text()
    assert "planned_cap=1.50" in text
    assert "batch_spent=0.5000 batch_avail=1.00" in text
    assert "batch_avail=0.7000" not in text

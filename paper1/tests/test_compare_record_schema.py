import json
import threading
from types import SimpleNamespace

from budgetflow.auto_budget import AutoBudgetMemory
from budgetflow.compare_checkpoint import GlobalRunProgress, StrategyScoreboard
from budgetflow.experiments.compare_persistence import (
    CompareRunState,
    completed_keys,
    persist_task_record,
    rebuild_state_from_jsonl,
)
from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.experiments.compare_execution import run_strategy_batch, run_task_record
from budgetflow.experiments.compare_summary import _format_live_snapshot, _format_strategy_totals
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
            patch_source="submission",
            submitted_patch_path="/tmp/submitted.patch",
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
            turn_trace_count=2,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
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


def test_auto_budget_records_dynamic_task_cap_mode(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    def fake_run_mini_swe_task(*args, **kwargs):
        return SimpleNamespace(
            instance_id="sympy__sympy-13480",
            total_cost=0.01,
            harness_resolved=False,
            patch_text="",
            patch_source="none",
            submitted_patch_path="",
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
            turn_trace_count=1,
            turn_traces=[],
            protocol_retry_used=False,
            protocol_retry_success=False,
            protocol_retry_reason="",
            protocol_retry_attempts=0,
            protocol_retry_limit=4,
        )

    monkeypatch.setattr(runner, "run_mini_swe_task", fake_run_mini_swe_task)
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=(),
        pass_to_pass=(),
    )
    estimate = SimpleNamespace(
        cap=0.12,
        estimated_cost=0.08,
        source="memory_exact",
        confidence="high",
        memory_neighbors=3,
        features={"repo": "sympy"},
    )

    records, _ = run_strategy_batch(
        CompareStrategy("budgetflow_segment", "segment_value_aware"),
        [task],
        batch_budget_cap=0.12,
        value_context=_value_context(),
        step_limit=1,
        trace_console="quiet",
        heartbeat=0,
        global_progress=GlobalRunProgress(1),
        scoreboard=None,
        print_lock=None,
        task_caps={"sympy__sympy-13480": 0.12},
        budget_estimates={"sympy__sympy-13480": estimate},
        run_series="schema_contract",
    )

    record = records[0]
    assert record["budget_mode"] == "dynamic_task_caps"
    assert record["per_task_cap"] == 0.12
    assert record["auto_budget_enabled"] is True
    assert record["estimated_task_cap"] == 0.12
    assert record["budget_prior_source"] == "memory_exact"


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


def test_persisted_jsonl_contains_t1_t2_observability_and_learning_memory(tmp_path) -> None:
    out_path = tmp_path / "out.jsonl"
    memory_path = tmp_path / "learning.jsonl"
    memory = AutoBudgetMemory(memory_path)
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
            auto_budget_memory=memory,
            no_auto_budget_learn=False,
        )

    persisted = json.loads(out_path.read_text().splitlines()[0])
    learned = AutoBudgetMemory(memory_path).records

    assert persisted["llm_turns"] == 2
    assert persisted["value_objective"] == "t2_value_source_diagnostic"
    assert persisted["task_value_source_class"] == "equal_sanity"
    assert persisted["task_value_primary_t1"] is False
    assert persisted["yield_per_dollar"] == 4.0
    assert persisted["routing_policy_family"] == "bootstrap:value_aware_segment"
    assert persisted["policy_kind"] == "bootstrap"
    assert persisted["routing_learned_action"] == "early_rescue"
    assert persisted["routing_policy_memory_source"].endswith("066_postfix_3x3.jsonl")
    assert record["budget_learning_update_written"] is True
    assert learned[0]["run_id"] == "schema_contract_budgetflow_segment_sympy__sympy-14774"


def test_abort_records_skip_auto_budget_memory(tmp_path) -> None:
    out_path = tmp_path / "out.jsonl"
    memory_path = tmp_path / "learning.jsonl"
    memory = AutoBudgetMemory(memory_path)
    ctx = _value_context()
    record = _record(score_status="abort", abort_reason="provider_or_infra_error", harness_resolved=False)

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
            auto_budget_memory=memory,
            no_auto_budget_learn=False,
        )

    persisted = json.loads(out_path.read_text().splitlines()[0])
    assert persisted["score_status"] == "abort"
    assert persisted["abort_reason"] == "provider_or_infra_error"
    assert persisted["budget_learning_update_written"] is False
    assert persisted["budget_learning_skipped_due_to_abort"] is True
    assert AutoBudgetMemory(memory_path).records == []


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
        budget_modes={"budgetflow_segment": "dynamic_task_caps"},
    )

    text = "\n".join(lines)
    assert "per-task cap" in text
    assert "1.50" in text
    assert "T5=75%" in text
    assert "100.00" not in text


def test_budget_summary_treats_frozen_router_caps_as_planned_cap() -> None:
    lines = _format_strategy_totals(
        strategy_names=["budgetflow_same_enterprise_router"],
        resolved_by_strategy={"budgetflow_same_enterprise_router": [True, False]},
        score_status_by_strategy={"budgetflow_same_enterprise_router": ["pass", "true_fail"]},
        task_cost_by_strategy={"budgetflow_same_enterprise_router": [0.2, 0.3]},
        batch_spent_by_strategy={"budgetflow_same_enterprise_router": 0.5},
        turns_by_strategy={"budgetflow_same_enterprise_router": [3, 7]},
        tier_mix_by_strategy={"budgetflow_same_enterprise_router": [{2: 1.0}, {3: 1.0}]},
        failure_by_strategy={"budgetflow_same_enterprise_router": {"pass": 1, "budget_fail": 1}},
        batch_caps={"budgetflow_same_enterprise_router": 0.75},
        budget_modes={"budgetflow_same_enterprise_router": "frozen_router_caps"},
    )

    text = "\n".join(lines)
    assert "per-task cap" in text
    assert "planned_cap" in text
    assert "0.7500" in text


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
        budget_modes={"budgetflow_segment": "frozen_router_caps"},
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
        budget_modes={"budgetflow_segment": "dynamic_task_caps"},
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

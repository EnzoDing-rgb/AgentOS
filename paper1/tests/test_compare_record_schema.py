import json
import threading
from types import SimpleNamespace

from budgetflow.auto_budget import AutoBudgetMemory
from budgetflow.compare_checkpoint import GlobalRunProgress
from budgetflow.experiments.compare_persistence import CompareRunState, persist_task_record
from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.experiments.compare_execution import run_task_record
from budgetflow.experiments.compare_summary import _format_live_snapshot, _format_strategy_totals
from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.value_efficiency import ValueEfficiencyContext


def _state() -> CompareRunState:
    return CompareRunState(
        summary_lines=[],
        resolved_by_strategy={},
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
        "run_series": "schema_contract",
        "attempt_id": "schema_contract_budgetflow_value_aware_tight_sympy__sympy-14774",
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
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), WorkflowLedgerStore())
    task = SimpleNamespace(
        instance_id="sympy__sympy-13480",
        patch="diff --git a/x b/x\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    record = run_task_record(
        task,
        cfg=CompareStrategy("budget_only_tight", "budget_only", "tight"),
        batch_budget_cap=1.0,
        governor=governor,
        ledger=WorkflowLedgerStore(),
        task_index=1,
        step_limit=1,
        value_context=_value_context(),
    )

    assert record["turns"] == record["llm_turns"] == 2
    assert record["resolved"] is True
    assert "resolved_value_per_dollar" not in record
    assert record["task_features"] == {"patch_lines": 1, "f2p_count": 1, "p2p_count": 0, "problem_length": 0}


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
            strategy_names=["budgetflow_value_aware_tight"],
            batch_caps={"budgetflow_value_aware_tight": 0.5},
            budget_modes={"budgetflow_value_aware_tight": "per_task_cap"},
            started=0.0,
            out_path=out_path,
            value_profile="equal",
            enrich_value=ctx.enrich_record,
            auto_budget_memory=memory,
            no_auto_budget_learn=False,
        )

    persisted = json.loads(out_path.read_text().splitlines()[0])
    learned = AutoBudgetMemory(memory_path).records

    assert persisted["turns"] == 2
    assert persisted["value_objective"] == "t2_equal_value_ablation"
    assert persisted["resolved_value_per_dollar"] == 4.0
    assert persisted["routing_policy_family"] == "bfv_equal_value_ablation"
    assert persisted["routing_learned_action"] == "early_rescue"
    assert persisted["routing_policy_memory_source"].endswith("066_postfix_3x3.jsonl")
    assert record["budget_learning_update_written"] is True
    assert learned[0]["run_id"] == "schema_contract_budgetflow_value_aware_tight_sympy__sympy-14774"


def test_budget_summary_reports_planned_cap_not_provider_runtime_balance() -> None:
    lines = _format_strategy_totals(
        strategy_names=["budgetflow_value_aware_tight"],
        resolved_by_strategy={"budgetflow_value_aware_tight": [True, False]},
        task_cost_by_strategy={"budgetflow_value_aware_tight": [0.2, 0.3]},
        batch_spent_by_strategy={"budgetflow_value_aware_tight": 0.5},
        turns_by_strategy={"budgetflow_value_aware_tight": [3, 7]},
        tier_mix_by_strategy={"budgetflow_value_aware_tight": [{2: 0.5, 5: 0.5}, {5: 1.0}]},
        failure_by_strategy={"budgetflow_value_aware_tight": {"pass": 1, "repair_fail": 1}},
        batch_caps={"budgetflow_value_aware_tight": 1.5},
        budget_modes={"budgetflow_value_aware_tight": "dynamic_task_caps"},
    )

    text = "\n".join(lines)
    assert "per-task cap" in text
    assert "1.50" in text
    assert "T5=75%" in text
    assert "100.00" not in text


def test_value_summary_reports_primary_normalized_value_metric(tmp_path) -> None:
    lines = _format_live_snapshot(
        strategy_names=["budgetflow_value_aware_tight"],
        resolved_by_strategy={"budgetflow_value_aware_tight": [True, False]},
        task_cost_by_strategy={"budgetflow_value_aware_tight": [0.2, 0.1]},
        turns_by_strategy={"budgetflow_value_aware_tight": [4, 3]},
        tier_mix_by_strategy={"budgetflow_value_aware_tight": [{2: 1.0}, {5: 1.0}]},
        batch_spent_by_strategy={"budgetflow_value_aware_tight": 0.3},
        batch_caps={"budgetflow_value_aware_tight": 0.5},
        budget_modes={"budgetflow_value_aware_tight": "dynamic_task_caps"},
        runs_done=2,
        total_runs=2,
        tasks_per_strategy=2,
        started=0.0,
        out_path=tmp_path / "run.jsonl",
        resolved_value_by_strategy={"budgetflow_value_aware_tight": [0.6, 0.0]},
        task_value_by_strategy={"budgetflow_value_aware_tight": [0.6, 0.4]},
        value_profile="difficulty",
    )

    text = "\n".join(lines)
    assert "nvrv" in text
    assert "rv_per_$" in text
    assert "0.60" in text
    assert "2.00" in text

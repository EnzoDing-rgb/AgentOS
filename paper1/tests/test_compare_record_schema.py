from types import SimpleNamespace

from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.run_mini_swe_compare import CompareStrategy, _run_one


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

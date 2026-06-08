from budgetflow.experiments.compare_config import effective_policy_jobs


def test_multi_policy_jobs_auto_upgrade_from_serial_request():
    assert effective_policy_jobs(requested_jobs=1, strategy_count=3) == 3


def test_default_jobs_matches_strategy_count():
    assert effective_policy_jobs(requested_jobs=None, strategy_count=3) == 3


def test_single_policy_can_stay_serial():
    assert effective_policy_jobs(requested_jobs=1, strategy_count=1) == 1


def test_requested_jobs_above_strategy_count_is_preserved():
    assert effective_policy_jobs(requested_jobs=5, strategy_count=3) == 5


def test_run_strategy_batch_executes_tasks_serially_within_one_policy(monkeypatch):
    from types import SimpleNamespace

    from budgetflow.experiments.compare_config import CompareStrategy
    from budgetflow.experiments.compare_execution import run_strategy_batch
    from budgetflow.experiments import compare_execution
    from budgetflow.value_efficiency import ValueEfficiencyContext

    order: list[str] = []

    def fake_run_task_record(task, **kwargs):
        order.append(task.instance_id)
        return {
            "instance_id": task.instance_id,
            "strategy": kwargs["cfg"].name,
            "routing": kwargs["cfg"].routing,
            "harness_resolved": True,
            "total_cost": 0.01,
            "task_cost": 0.01,
            "row_started_at": len(order),
            "row_finished_at": len(order),
        }

    monkeypatch.setattr(compare_execution, "run_task_record", fake_run_task_record)
    value_context = ValueEfficiencyContext()
    value_context.init(value_profile="equal")

    records, _spent = run_strategy_batch(
        CompareStrategy("policy-a", "budgetflow_value_aware", "tight"),
        [
            SimpleNamespace(instance_id="task-1"),
            SimpleNamespace(instance_id="task-2"),
            SimpleNamespace(instance_id="task-3"),
        ],
        batch_budget_cap=1.0,
        value_context=value_context,
        step_limit=1,
        trace_console="quiet",
        heartbeat=0,
        global_progress=SimpleNamespace(
            total=3,
            start_task=lambda: None,
            finish_task=lambda: len(order),
            format_banner=lambda scoreboard=None: "test",
            format_global=lambda scoreboard=None: "test",
        ),
        scoreboard=None,
        print_lock=None,
    )

    assert order == ["task-1", "task-2", "task-3"]
    assert [record["instance_id"] for record in records] == order

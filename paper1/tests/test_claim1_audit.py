from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from budgetflow.experiments.claim1_audit import build_report, load_latest_rows
from budgetflow.experiments.claim1_value_sensitivity import compute_observed_tier_oracle


def test_claim1_audit_dedupes_latest_scoreable_row(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"true_fail","task_value":2.5,"resolved_value":0.0,'
                '"total_cost":0.4,"batch_budget_cap":1.0}',
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"pass","task_value":2.5,"resolved_value":2.5,'
                '"total_cost":0.5,"batch_budget_cap":1.0}',
                '{"instance_id":"task-a","strategy":"bare_t3_baseline","task_index_in_batch":1,'
                '"score_status":"true_fail","task_value":2.5,"resolved_value":0.0,'
                '"total_cost":0.7,"batch_budget_cap":1.0}',
                '{"instance_id":"task-b","strategy":"bare_t3_baseline","task_index_in_batch":2,'
                '"score_status":"abort","task_value":1.0,"resolved_value":0.0,'
                '"total_cost":0.2,"batch_budget_cap":1.0}',
            ]
        )
        + "\n"
    )

    rows = load_latest_rows(jsonl)
    report = build_report(rows, title="Unit Audit")

    assert "BudgetFlow-only pass: 1 tasks, value 2.50" in report
    assert "| budgetflow_task_level | partial_incomplete | 1/2 | 1/2 | 0 | 1/2 | 50.0%" in report
    assert "| bare_t3_baseline | complete_with_aborts | 2/2 | 1/2 | 1 | 0/2 | 0.0%" in report
    assert "$0.90" in report


def test_claim1_audit_marks_budget_exhausted_and_partial_lanes(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"instance_id":"task-a","strategy":"bare_t2_baseline","task_index_in_batch":1,'
                '"score_status":"pass","task_value":1.0,"resolved_value":1.0,'
                '"total_cost":0.6,"batch_budget_cap":1.0}',
                '{"instance_id":"task-b","strategy":"bare_t2_baseline","task_index_in_batch":2,'
                '"score_status":"true_fail","task_value":1.0,"resolved_value":0.0,'
                '"total_cost":0.4,"batch_budget_cap":1.0}',
                '{"instance_id":"task-a","strategy":"bare_t3_baseline","task_index_in_batch":1,'
                '"score_status":"pass","task_value":1.0,"resolved_value":1.0,'
                '"total_cost":0.2,"batch_budget_cap":1.0}',
            ]
        )
        + "\n"
    )

    rows = load_latest_rows(jsonl)
    report = build_report(
        rows,
        title="Unit Audit",
        task_order_override=["task-a", "task-b", "task-c"],
    )

    assert "| bare_t2_baseline | budget_exhausted | 2/3 | 2/3 | 0 | 1/3 | 33.3%" in report
    assert "| bare_t3_baseline | partial_incomplete | 1/3 | 1/3 | 0 | 1/3 | 33.3%" in report


def test_claim1_audit_reports_routing_and_spin_diagnostics(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"instance_id":"task-a","strategy":"bare_t3_baseline","task_index_in_batch":1,'
                '"score_status":"pass","task_value":1.0,"resolved_value":1.0,'
                '"total_cost":0.2,"batch_budget_cap":1.0,"backend_picks":["tier3","tier3"],"llm_turns":2}',
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"true_fail","task_value":1.0,"resolved_value":0.0,'
                '"total_cost":0.4,"batch_budget_cap":1.0,"backend_picks":["tier3","tier3"],"llm_turns":2}',
                '{"instance_id":"task-b","strategy":"bare_t3_baseline","task_index_in_batch":2,'
                '"score_status":"true_fail","task_value":1.0,"resolved_value":0.0,'
                '"total_cost":0.2,"batch_budget_cap":1.0,"backend_picks":["tier3"],"llm_turns":1}',
                '{"instance_id":"task-b","strategy":"budgetflow_task_level","task_index_in_batch":2,'
                '"score_status":"true_fail","task_value":1.0,"resolved_value":0.0,'
                '"total_cost":0.5,"batch_budget_cap":1.0,'
                '"backend_picks":["tier2","tier2","tier2","tier2","tier2"],"llm_turns":5}',
            ]
        )
        + "\n"
    )

    report = build_report(
        load_latest_rows(jsonl),
        title="Unit Audit",
        task_order_override=["task-a", "task-b"],
    )

    assert "## Routing And Spin Diagnostics" in report
    assert "| budgetflow_task_level | 2 | 1 | 0 | 1 | 0 | 0 | 1 | 5 | 4.0 |" in report
    assert "- BudgetFlow T3-start rows: 1; resolved 0; true-fail 1; abort 0." in report
    assert "- BudgetFlow all-T2 rows on tasks with pure T3 rows: 1; turns 5 vs pure T3 1." in report


def test_claim1_audit_keeps_paid_retry_spend_when_latest_row_passes(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"abort","task_value":1.0,"resolved_value":0.0,'
                '"total_cost":0.2,"batch_budget_cap":1.0}',
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"pass","harness_resolved":true,"harness_trust":"trusted",'
                '"task_value":1.0,"resolved_value":1.0,"total_cost":0.5,"batch_budget_cap":1.0}',
            ]
        )
        + "\n"
    )

    report = build_report(load_latest_rows(jsonl), title="Unit Audit")

    assert "| budgetflow_task_level | complete | 1/1 | 1/1 | 0 | 1/1 | 100.0%" in report
    assert "$0.70" in report
    assert "| budgetflow_task_level | 1 | 0 | 0 | 0 | 0 |" in report
    assert "| KV0 | budgetflow_task_level | 1/1 | $0.70 | 1.00 | 1.43 |" in report


def test_claim1_audit_rescores_value_profiles_and_observed_tier_oracle(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"instance_id":"task-a","strategy":"bare_t2_baseline","task_index_in_batch":1,'
                '"score_status":"pass","task_value":2.5,"resolved_value":2.5,'
                '"total_cost":0.3,"batch_budget_cap":1.0,'
                '"backend_picks":["tier2"],"llm_turns":1,"prompt_tokens_total":1000,"completion_tokens_total":100}',
                '{"instance_id":"task-b","strategy":"bare_t2_baseline","task_index_in_batch":2,'
                '"score_status":"true_fail","task_value":1.0,"resolved_value":0.0,'
                '"total_cost":0.3,"batch_budget_cap":1.0,'
                '"backend_picks":["tier2"],"llm_turns":1,"prompt_tokens_total":1000,"completion_tokens_total":100}',
                '{"instance_id":"task-a","strategy":"bare_t3_baseline","task_index_in_batch":1,'
                '"score_status":"true_fail","task_value":2.5,"resolved_value":0.0,'
                '"total_cost":0.6,"batch_budget_cap":1.0,'
                '"backend_picks":["tier3"],"llm_turns":1,"prompt_tokens_total":1000,"completion_tokens_total":100}',
                '{"instance_id":"task-b","strategy":"bare_t3_baseline","task_index_in_batch":2,'
                '"score_status":"pass","task_value":1.0,"resolved_value":1.0,'
                '"total_cost":0.6,"batch_budget_cap":1.0,'
                '"backend_picks":["tier3"],"llm_turns":1,"prompt_tokens_total":1000,"completion_tokens_total":100}',
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"pass","task_value":2.5,"resolved_value":2.5,'
                '"total_cost":0.3,"batch_budget_cap":1.0,'
                '"backend_picks":["tier2"],"llm_turns":1,"prompt_tokens_total":1000,"completion_tokens_total":100}',
                '{"instance_id":"task-b","strategy":"budgetflow_task_level","task_index_in_batch":2,'
                '"score_status":"pass","task_value":1.0,"resolved_value":1.0,'
                '"total_cost":0.6,"batch_budget_cap":1.0,'
                '"backend_picks":["tier3"],"llm_turns":1,"prompt_tokens_total":1000,"completion_tokens_total":100}',
            ]
        )
        + "\n"
    )
    value_matrix = tmp_path / "value_matrix.json"
    value_matrix.write_text(
        """
{
  "tasks": {
    "task-a": {
      "task_value": {"equal": 1.0, "criticality_value": 2.5},
      "criticality_level": "critical"
    },
    "task-b": {
      "task_value": {"equal": 1.0, "criticality_value": 1.0},
      "criticality_level": "normal"
    }
  }
}
""".strip()
    )

    report = build_report(
        load_latest_rows(jsonl),
        title="Unit Audit",
        task_order_override=["task-a", "task-b"],
        value_matrix_path=value_matrix,
        budget_cap=1.0,
    )

    assert "## Value Sensitivity" in report
    assert "| equal | budgetflow_task_level | 2/2 | $0.90 | 2.00 | 2.22 |" in report
    assert "| criticality_value | budgetflow_task_level | 2/2 | $0.90 | 3.50 | 3.89 |" in report
    assert "## Static Observed-Tier Oracle" in report
    assert "| criticality_value | 2/2 | $0.90 | 3.50 | 3.89 | 1 | 1 | 0 |" in report
    assert "## KV Cache Sensitivity" in report
    assert "| KV0 | budgetflow_task_level |" in report
    assert "## Budget Cap Sensitivity" in report
    assert "| $0.50 | budgetflow_task_level | 1/2 | $0.30 | 2.50 | 8.33 |" in report


def test_claim1_audit_uses_value_matrix_for_missing_task_display(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        '{"instance_id":"task-a","strategy":"bare_t3_baseline","task_index_in_batch":1,'
        '"score_status":"pass","task_value":1.0,"resolved_value":1.0,'
        '"total_cost":0.2,"batch_budget_cap":1.0}\n'
    )
    value_matrix = tmp_path / "value_matrix.json"
    value_matrix.write_text(
        """
{
  "tasks": {
    "task-a": {
      "task_value": {"equal": 1.0, "criticality_value": 1.0},
      "criticality_level": "normal"
    },
    "task-b": {
      "task_value": {"equal": 1.0, "criticality_value": 2.5},
      "criticality_level": "critical"
    }
  }
}
""".strip()
    )

    report = build_report(
        load_latest_rows(jsonl),
        title="Unit Audit",
        task_order_override=["task-a", "task-b"],
        value_matrix_path=value_matrix,
    )

    assert "| 2 | `task-b` | 2.50 | - |" in report


def test_observed_tier_oracle_chooses_global_budget_combination() -> None:
    def task(strategy: str, instance_id: str, status: str, cost: float) -> SimpleNamespace:
        return SimpleNamespace(
            strategy=strategy,
            instance_id=instance_id,
            score_status=status,
            task_value=0.0,
            total_cost=cost,
            batch_budget_cap=1.0,
        )

    by_key = {
        ("bare_t2_baseline", "task-a"): task("bare_t2_baseline", "task-a", "pass", 0.6),
        ("bare_t3_baseline", "task-a"): task("bare_t3_baseline", "task-a", "true_fail", 0.2),
        ("bare_t2_baseline", "task-b"): task("bare_t2_baseline", "task-b", "pass", 0.5),
        ("bare_t3_baseline", "task-b"): task("bare_t3_baseline", "task-b", "true_fail", 0.2),
        ("bare_t2_baseline", "task-c"): task("bare_t2_baseline", "task-c", "true_fail", 0.2),
        ("bare_t3_baseline", "task-c"): task("bare_t3_baseline", "task-c", "pass", 0.5),
    }

    result = compute_observed_tier_oracle(
        ["task-a", "task-b", "task-c"],
        by_key,
        {"task-a": 6.0, "task-b": 5.0, "task-c": 5.0},
        budget_cap=1.0,
    )

    assert result.resolved == 2
    assert result.spend == 1.0
    assert result.total_resolved_value == 10.0
    assert [(action.task_id, action.tier) for action in result.actions] == [
        ("task-b", "T2"),
        ("task-c", "T3"),
    ]

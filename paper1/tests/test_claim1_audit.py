from __future__ import annotations

from pathlib import Path

from budgetflow.experiments.claim1_audit import build_report, load_latest_rows


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

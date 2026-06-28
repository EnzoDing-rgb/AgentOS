from __future__ import annotations

from pathlib import Path

from budgetflow.experiments.claim1_audit import build_report, load_latest_rows


def test_claim1_audit_dedupes_latest_scoreable_row(tmp_path: Path) -> None:
    jsonl = tmp_path / "run.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"true_fail","task_value":2.5,"resolved_value":0.0,"total_cost":0.4}',
                '{"instance_id":"task-a","strategy":"budgetflow_task_level","task_index_in_batch":1,'
                '"score_status":"pass","task_value":2.5,"resolved_value":2.5,"total_cost":0.5}',
                '{"instance_id":"task-a","strategy":"bare_t3_baseline","task_index_in_batch":1,'
                '"score_status":"true_fail","task_value":2.5,"resolved_value":0.0,"total_cost":0.7}',
                '{"instance_id":"task-b","strategy":"bare_t3_baseline","task_index_in_batch":2,'
                '"score_status":"abort","task_value":1.0,"resolved_value":0.0,"total_cost":0.2}',
            ]
        )
        + "\n"
    )

    rows = load_latest_rows(jsonl)
    report = build_report(rows, title="Unit Audit")

    assert "BudgetFlow-only pass: 1 tasks, value 2.50" in report
    assert "| budgetflow_task_level | 1/2 | 50.0% | $0.50" in report
    assert "| bare_t3_baseline | 0/2 | 0.0% | $0.90" in report

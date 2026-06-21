"""Build an official SWE-bench cross-check command from BudgetFlow rows."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from .console_log import dim, tag
from .export_official_predictions import export_predictions


def select_crosscheck_rows(
    input_path: Path,
    output_path: Path,
    *,
    limit: int,
    include_passes: int,
) -> int:
    """Write a small JSONL subset for official evaluator cross-checking."""
    pass_rows: list[dict] = []
    fail_rows: list[dict] = []
    for line in input_path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not _has_workspace_patch(record):
            continue
        if _is_pass(record):
            pass_rows.append(record)
        elif record.get("score_status") == "true_fail" or record.get("failure_class"):
            fail_rows.append(record)

    selected = fail_rows[: max(0, limit - include_passes)] + pass_rows[:include_passes]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        for record in selected[:limit]:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return min(len(selected), limit)


def official_eval_command(
    predictions_path: Path,
    *,
    dataset_name: str,
    run_id: str,
    swebench_venv: Path,
    max_workers: int,
) -> str:
    python_bin = swebench_venv / "bin" / "python"
    parts = [
        str(python_bin),
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--predictions_path",
        str(predictions_path.resolve()),
        "--max_workers",
        str(max_workers),
        "--run_id",
        run_id,
        "--namespace",
        "",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _has_workspace_patch(record: dict) -> bool:
    if record.get("workspace_patch") or record.get("workspace_patch_path"):
        return True
    trace_dir = record.get("trace_dir")
    return bool(trace_dir and (Path(trace_dir) / "workspace.patch").is_file())


def _is_pass(record: dict) -> bool:
    return record.get("score_status") == "pass" or record.get("failure_class") == "pass"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a small official SWE-bench evaluator cross-check from BudgetFlow JSONL"
    )
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--include-passes", type=int, default=3)
    parser.add_argument("--model-name", default="budgetflow-crosscheck")
    parser.add_argument("--dataset-name", default="princeton-nlp/SWE-bench_Lite")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--swebench-venv", type=Path, default=Path("/data/swe-bench-env"))
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args()

    out_dir = args.out_dir or args.input_jsonl.with_suffix("").parent
    stem = args.input_jsonl.with_suffix("").name
    subset_path = out_dir / f"{stem}.official_crosscheck.rows.jsonl"
    predictions_path = out_dir / f"{stem}.official_crosscheck.predictions.jsonl"
    run_id = args.run_id or f"{stem}-official-crosscheck"

    selected = select_crosscheck_rows(
        args.input_jsonl,
        subset_path,
        limit=max(1, args.limit),
        include_passes=max(0, args.include_passes),
    )
    exported = export_predictions(subset_path, predictions_path, model_name=args.model_name)
    print(f"{tag('official')} selected {selected} rows; exported {exported} predictions")
    print(f"{dim('rows=')}{subset_path}")
    print(f"{dim('predictions=')}{predictions_path}")
    print(f"{dim('command=')}{official_eval_command(predictions_path, dataset_name=args.dataset_name, run_id=run_id, swebench_venv=args.swebench_venv, max_workers=args.max_workers)}")


if __name__ == "__main__":
    main()

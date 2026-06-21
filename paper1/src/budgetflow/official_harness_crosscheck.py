"""Build an official SWE-bench cross-check command from BudgetFlow rows."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
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

    selected: list[dict] = []
    seen_instances: set[str] = set()
    fail_target = max(0, limit - include_passes)
    _append_unique(selected, seen_instances, fail_rows, max_new=fail_target)
    _append_unique(selected, seen_instances, pass_rows, max_new=include_passes)
    if len(selected) < limit:
        _append_unique(selected, seen_instances, fail_rows + pass_rows, max_new=limit - len(selected))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(selected)


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


def official_eval_preflight(*, swebench_venv: Path) -> list[str]:
    """Return local environment warnings for running the official evaluator."""
    warnings: list[str] = []
    python_bin = swebench_venv / "bin" / "python"
    if not python_bin.exists():
        warnings.append(f"missing_swebench_python:{python_bin}")
    if shutil.which("docker") is None:
        warnings.append("missing_docker")
    return warnings


def build_crosscheck_artifacts(
    input_path: Path,
    *,
    out_dir: Path | None = None,
    limit: int = 12,
    include_passes: int = 3,
    model_name: str = "budgetflow-crosscheck",
    dataset_name: str = "princeton-nlp/SWE-bench_Lite",
    run_id: str | None = None,
    swebench_venv: Path = Path("/data/swe-bench-env"),
    max_workers: int = 1,
) -> dict:
    """Create official-evaluator dry-run artifacts for local-harness audit.

    This function does not invoke Docker or SWE-bench. It writes the selected
    rows, predictions JSONL, a command text file, and a manifest so paid-run
    summaries can point to a reproducible local-vs-official cross-check path.
    """
    output_dir = out_dir or input_path.with_suffix("").parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.with_suffix("").name
    subset_path = output_dir / f"{stem}.official_crosscheck.rows.jsonl"
    predictions_path = output_dir / f"{stem}.official_crosscheck.predictions.jsonl"
    command_path = output_dir / f"{stem}.official_crosscheck.command.txt"
    manifest_path = output_dir / f"{stem}.official_crosscheck.manifest.json"
    effective_run_id = run_id or f"{stem}-official-crosscheck"

    selected = select_crosscheck_rows(
        input_path,
        subset_path,
        limit=max(1, int(limit)),
        include_passes=max(0, int(include_passes)),
    )
    exported = export_predictions(subset_path, predictions_path, model_name=model_name)
    command = official_eval_command(
        predictions_path,
        dataset_name=dataset_name,
        run_id=effective_run_id,
        swebench_venv=swebench_venv,
        max_workers=max_workers,
    )
    warnings = official_eval_preflight(swebench_venv=swebench_venv)
    command_path.write_text(command + "\n")
    manifest = {
        "mode": "dry_run_artifact_only",
        "input_jsonl": str(input_path),
        "rows_path": str(subset_path),
        "predictions_path": str(predictions_path),
        "command_path": str(command_path),
        "selected_rows": selected,
        "exported_predictions": exported,
        "dataset_name": dataset_name,
        "run_id": effective_run_id,
        "swebench_venv": str(swebench_venv),
        "max_workers": max_workers,
        "preflight_warnings": warnings,
        "note": "Artifact only: compare runs do not execute the official evaluator automatically.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _has_workspace_patch(record: dict) -> bool:
    if record.get("workspace_patch") or record.get("workspace_patch_path"):
        return True
    trace_dir = record.get("trace_dir")
    return bool(trace_dir and (Path(trace_dir) / "workspace.patch").is_file())


def _is_pass(record: dict) -> bool:
    return record.get("score_status") == "pass" or record.get("failure_class") == "pass"


def _append_unique(
    selected: list[dict],
    seen_instances: set[str],
    candidates: list[dict],
    *,
    max_new: int,
) -> None:
    added = 0
    for record in candidates:
        if added >= max_new:
            return
        instance_id = str(record.get("instance_id") or "")
        if not instance_id or instance_id in seen_instances:
            continue
        selected.append(record)
        seen_instances.add(instance_id)
        added += 1


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
    manifest = build_crosscheck_artifacts(
        args.input_jsonl,
        out_dir=out_dir,
        limit=max(1, args.limit),
        include_passes=max(0, args.include_passes),
        model_name=args.model_name,
        dataset_name=args.dataset_name,
        run_id=args.run_id,
        swebench_venv=args.swebench_venv,
        max_workers=args.max_workers,
    )
    print(
        f"{tag('official')} selected {manifest['selected_rows']} rows; "
        f"exported {manifest['exported_predictions']} predictions"
    )
    print(f"{dim('rows=')}{manifest['rows_path']}")
    print(f"{dim('predictions=')}{manifest['predictions_path']}")
    print(f"{dim('manifest=')}{manifest['manifest_path']}")
    if manifest["preflight_warnings"]:
        print(f"{tag('official', bold=False)} preflight_warnings={','.join(manifest['preflight_warnings'])}")
    print(f"{dim('command=')}{Path(manifest['command_path']).read_text().strip()}")


if __name__ == "__main__":
    main()

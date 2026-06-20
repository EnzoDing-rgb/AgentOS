"""Export SWE-bench official prediction JSONL from raw/compare run records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .console_log import dim, tag
from .official_predictions import prediction_record, write_predictions_jsonl


def _patch_from_record(record: dict) -> str | None:
    path = record.get("workspace_patch")
    if path and Path(path).is_file():
        return Path(path).read_text()
    path = record.get("workspace_patch_path")
    if path and Path(path).is_file():
        return Path(path).read_text()
    trace_dir = record.get("trace_dir")
    if trace_dir:
        path = Path(trace_dir) / "workspace.patch"
        if path.is_file():
            return path.read_text()
    return None


def _model_name(record: dict, fallback: str) -> str:
    return str(record.get("model") or record.get("model_name_or_path") or record.get("strategy") or fallback)


def export_predictions(input_path: Path, output_path: Path, *, model_name: str) -> int:
    records: list[dict[str, str]] = []
    for line in input_path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        records.append(
            prediction_record(
                instance_id=str(record["instance_id"]),
                model_name=_model_name(record, model_name),
                model_patch=_patch_from_record(record),
            )
        )
    write_predictions_jsonl(output_path, records)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SWE-bench official predictions.jsonl")
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--model-name", default="budgetflow")
    args = parser.parse_args()

    out = args.out or args.input_jsonl.with_suffix(".official_predictions.jsonl")
    count = export_predictions(args.input_jsonl, out, model_name=args.model_name)
    print(f"{tag('official')} exported {count} predictions")
    print(f"{dim('predictions=')}{out}")


if __name__ == "__main__":
    main()

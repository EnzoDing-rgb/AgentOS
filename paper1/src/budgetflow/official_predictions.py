from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def prediction_record(*, instance_id: str, model_name: str, model_patch: str | None) -> dict[str, str]:
    return {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "model_patch": model_patch or "",
    }


def write_predictions_jsonl(path: Path, records: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

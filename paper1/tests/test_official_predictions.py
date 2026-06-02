from __future__ import annotations

import json

from budgetflow.official_predictions import prediction_record


def test_prediction_record_matches_swebench_schema() -> None:
    record = prediction_record(
        instance_id="psf__requests-863",
        model_name="openai/gpt-5.3-codex",
        model_patch="diff --git a/x.py b/x.py\n",
    )

    assert set(record) == {"instance_id", "model_name_or_path", "model_patch"}
    assert record["instance_id"] == "psf__requests-863"
    assert record["model_name_or_path"] == "openai/gpt-5.3-codex"
    assert record["model_patch"].startswith("diff --git")


def test_prediction_record_is_jsonl_serializable() -> None:
    record = prediction_record(
        instance_id="x",
        model_name="m",
        model_patch=None,
    )

    encoded = json.dumps(record)
    decoded = json.loads(encoded)

    assert decoded == {"instance_id": "x", "model_name_or_path": "m", "model_patch": ""}

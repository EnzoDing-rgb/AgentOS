from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from datasets import load_dataset

from .loop import WorkflowSpec, WorkflowStep
from .types import Stage

LOCAL_EXPORT_DIR = Path("/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/data/swebench_lite_export")


@dataclass(frozen=True)
class LiteTaskRecord:
    instance_id: str
    repo: str
    problem_statement: str
    patch: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    gold_files: tuple[str, ...]
    workflow: WorkflowSpec


def load_swebench_lite_tasks(limit: int = 8, offset: int = 0) -> list[LiteTaskRecord]:
    items = load_local_swebench_lite_export()
    if items is None:
        dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        selected = dataset.select(range(offset, min(offset + limit, len(dataset))))
        items = list(selected)
    selected_items = items[offset : offset + limit]
    return [build_lite_task_record(item) for item in selected_items]


def load_local_swebench_lite_export() -> list[dict] | None:
    test_jsonl = LOCAL_EXPORT_DIR / "test.jsonl"
    if not test_jsonl.exists():
        return None
    return [json.loads(line) for line in test_jsonl.read_text().splitlines() if line.strip()]


def build_lite_task_record(item: dict) -> LiteTaskRecord:
    instance_id = item["instance_id"]
    problem_statement = item.get("problem_statement", "")
    patch = item.get("patch", "")
    fail_to_pass = tuple(item.get("FAIL_TO_PASS", []) or [])
    pass_to_pass = tuple(item.get("PASS_TO_PASS", []) or [])
    gold_files = extract_gold_files(patch)
    workflow = WorkflowSpec(
        workflow_id=instance_id,
        steps=(
            WorkflowStep(
                stage=Stage.LOCALIZATION,
                input_tokens=estimate_localization_tokens(problem_statement, gold_files),
                w_i=1.0,
            ),
            WorkflowStep(
                stage=Stage.REPAIR,
                input_tokens=estimate_repair_tokens(problem_statement, patch),
                w_i=3.0,
            ),
            WorkflowStep(
                stage=Stage.VALIDATION,
                input_tokens=estimate_validation_tokens(problem_statement, fail_to_pass, pass_to_pass),
                w_i=2.5,
            ),
        ),
    )
    return LiteTaskRecord(
        instance_id=instance_id,
        repo=item.get("repo", ""),
        problem_statement=problem_statement,
        patch=patch,
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
        gold_files=gold_files,
        workflow=workflow,
    )


def extract_gold_files(patch: str) -> tuple[str, ...]:
    if not patch:
        return ()
    files: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            path = line[6:].strip()
            if path != "/dev/null":
                files.append(path)
    return tuple(dict.fromkeys(files))


def estimate_localization_tokens(problem_statement: str, gold_files: Iterable[str]) -> int:
    return clamp_tokens(80 + len(problem_statement.split()) + 18 * len(tuple(gold_files)))


def estimate_repair_tokens(problem_statement: str, patch: str) -> int:
    patch_lines = len(patch.splitlines())
    return clamp_tokens(120 + len(problem_statement.split()) + 6 * patch_lines)


def estimate_validation_tokens(problem_statement: str, fail_to_pass: tuple[str, ...], pass_to_pass: tuple[str, ...]) -> int:
    return clamp_tokens(100 + len(problem_statement.split()) // 2 + 20 * len(fail_to_pass) + 8 * len(pass_to_pass))


def clamp_tokens(value: int) -> int:
    return max(60, min(value, 220))

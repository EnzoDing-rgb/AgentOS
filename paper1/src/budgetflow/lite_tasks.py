from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from datasets import load_dataset
import pandas as pd

from .loop import WorkflowSpec, WorkflowStep
from .types import Stage

LOCAL_EXPORT_DIR = Path("/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/data/swebench_lite_export")


@dataclass(frozen=True)
class LiteTaskRecord:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    patch: str
    test_patch: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    gold_files: tuple[str, ...]
    workflow: WorkflowSpec


def load_swebench_lite_tasks(
    limit: int = 8,
    offset: int = 0,
    instance_ids: tuple[str, ...] | None = None,
) -> list[LiteTaskRecord]:
    items = load_local_swebench_lite_export()
    if items is None:
        items = load_local_swebench_lite_parquet()
    if items is None:
        dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        items = list(dataset)
    if instance_ids:
        lookup = {item["instance_id"]: item for item in items}
        selected_items = [lookup[instance_id] for instance_id in instance_ids]
    else:
        selected_items = items[offset : offset + limit]
    return [build_lite_task_record(item) for item in selected_items]


def load_local_swebench_lite_export() -> list[dict] | None:
    test_jsonl = LOCAL_EXPORT_DIR / "test.jsonl"
    if not test_jsonl.exists():
        return None
    return [json.loads(line) for line in test_jsonl.read_text().splitlines() if line.strip()]


def load_local_swebench_lite_parquet() -> list[dict] | None:
    test_parquet = LOCAL_EXPORT_DIR / "test.parquet"
    if not test_parquet.exists():
        return None
    frame = pd.read_parquet(test_parquet)
    return frame.to_dict(orient="records")


def parse_test_list(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return ()
        if value.startswith("["):
            parsed = json.loads(value)
            return tuple(parsed)
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def build_lite_task_record(item: dict) -> LiteTaskRecord:
    instance_id = item["instance_id"]
    problem_statement = item.get("problem_statement", "")
    patch = item.get("patch", "")
    fail_to_pass = parse_test_list(item.get("FAIL_TO_PASS"))
    pass_to_pass = parse_test_list(item.get("PASS_TO_PASS"))
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
        base_commit=item.get("base_commit", ""),
        problem_statement=problem_statement,
        patch=patch,
        test_patch=item.get("test_patch", "") or "",
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


def build_lite_stage_prompt(task: LiteTaskRecord, stage: Stage) -> str:
    issue = task.problem_statement.strip()
    if len(issue) > 1200:
        issue = issue[:1200] + "\n...[truncated]"

    if stage is Stage.LOCALIZATION:
        return (
            f"Repository: {task.repo}\n"
            f"Instance: {task.instance_id}\n\n"
            f"Bug report:\n{issue}\n\n"
            "Localization step: identify the most likely source files to inspect first. "
            "Return concrete repo-relative .py file paths."
        )

    if stage is Stage.REPAIR:
        return (
            f"Repository: {task.repo}\n"
            f"Instance: {task.instance_id}\n\n"
            f"Bug report:\n{issue}\n\n"
            "Repair step: propose the minimal code change needed to fix the bug. "
            "Return a short explanation of the root cause and the fix."
        )

    tests = ", ".join(task.fail_to_pass[:5]) if task.fail_to_pass else "relevant regression tests"
    return (
        f"Repository: {task.repo}\n"
        f"Instance: {task.instance_id}\n\n"
        f"Bug report:\n{issue}\n\n"
        f"Validation step: explain how to verify the fix using tests such as: {tests}. "
        "Return a short validation plan."
    )


def build_repair_patch_prompt(task: LiteTaskRecord, localization_text: str, file_context: str = "") -> str:
    issue = task.problem_statement.strip()
    if len(issue) > 1200:
        issue = issue[:1200] + "\n...[truncated]"
    loc = localization_text.strip() or "No localization notes."
    if len(loc) > 800:
        loc = loc[:800] + "\n...[truncated]"
    context_block = file_context.strip() or "No source files loaded."
    if len(context_block) > 8000:
        context_block = context_block[:8000] + "\n...[truncated]"
    return (
        f"Repository: {task.repo}\n"
        f"Instance: {task.instance_id}\n"
        f"Base commit: {task.base_commit}\n\n"
        f"Bug report:\n{issue}\n\n"
        f"Localization notes:\n{loc}\n\n"
        f"Source files:\n{context_block}\n\n"
        "Repair step: propose concrete source edits that fix the bug.\n"
        "Output ONLY one ```json ... ``` block with this schema:\n"
        "{\n"
        '  "edits": [\n'
        '    {"file": "path.py", "old": "exact old text", "new": "replacement text"}\n'
        "  ]\n"
        "}\n"
        "Requirements:\n"
        "- Use repo-relative file paths\n"
        "- `old` must match exact file text from the source files above\n"
        "- `new` is the replacement text for that exact block\n"
        "- Modify source files only (no test files)\n"
        "- Keep edits minimal\n"
        "- No prose outside JSON\n"
    )


def build_repair_retry_prompt(
    task: LiteTaskRecord,
    localization_text: str,
    file_context: str,
    previous_patch: str,
    error_message: str,
    attempt: int,
) -> str:
    base = build_repair_patch_prompt(task, localization_text, file_context)
    prev = previous_patch.strip() or "<empty>"
    if len(prev) > 1500:
        prev = prev[:1500] + "\n...[truncated]"
    err = error_message.strip() or "unknown error"
    if len(err) > 1200:
        err = err[:1200] + "\n...[truncated]"
    return (
        f"{base}\n\n"
        f"Previous attempt #{attempt - 1} failed.\n"
        f"Edit/apply/test error:\n{err}\n\n"
        f"Previous output:\n```json\n{prev}\n```\n\n"
        "Regenerate the ENTIRE edits JSON from scratch.\n"
        "Do not describe the fix. Do not emit partial JSON.\n"
        "Correct file paths and ensure each `old` block matches exact file text from the provided source files."
    )

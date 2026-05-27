from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from datasets import load_dataset
import pandas as pd

from .loop import WorkflowSpec, WorkflowStep
from .types import Stage

PAPER1_ROOT = Path(__file__).resolve().parents[2]
LOCAL_EXPORT_DIR = PAPER1_ROOT / "data" / "swebench_lite_export"


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


# Pipeline smoke: 1 fail_to_pass test, tiny gold patch (not sympy-11400 ccode/sinc).
SMOKE_INSTANCE_IDS: tuple[str, ...] = (
    "sympy__sympy-20212",  # 0**-oo -> ComplexInfinity; ~4 lines in sympy/core/power.py
    "sympy__sympy-12171",  # mathematica Derivative printer; problem states fix
    "sympy__sympy-21614",  # Derivative.kind delegates to expr.kind
)


def load_smoke_tasks(limit: int = 1) -> list[LiteTaskRecord]:
    """Load easiest lite sympy tasks for mini-SWE / Step A smoke."""
    return load_swebench_lite_tasks(instance_ids=SMOKE_INSTANCE_IDS[:limit])


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
        '    {"op": "replace", "file": "path.py", "old": "exact old text", "new": "replacement text"},\n'
        '    {"op": "anchor_replace", "file": "path.py", "anchor": "nearby exact text", "old": "target text", "new": "replacement text"},\n'
        '    {"op": "insert_after", "file": "path.py", "anchor": "exact existing text", "new": "text to insert after anchor"},\n'
        '    {"op": "line_replace", "file": "path.py", "anchor": "exact single source line", "new": "full replacement line"}\n'
        "  ]\n"
        "}\n"
        "Requirements:\n"
        "- Use repo-relative file paths\n"
        "- Modify source files only (no test files)\n"
        "- Prefer `line_replace` for single-line fixes\n"
        "- Prefer `replace` when exact multi-line old text is visible in source files\n"
        "- Use `anchor_replace` when exact full block may drift but nearby anchor is stable\n"
        "- For `line_replace`, copy the anchor line exactly from numbered source; `new` is replacement code (indent is applied automatically)\n"
        "- Keep edits minimal\n"
        "- No prose outside JSON\n"
    )


def summarize_repair_error(error_message: str, max_len: int = 600) -> str:
    err = error_message.strip()
    if "IndentationError" in err or "SyntaxError" in err or "parse_error:syntax" in err:
        for line in err.splitlines():
            if "Error" in line or "syntax" in line.lower():
                return line[:max_len]
    if "fail_after=fail" in err:
        tail = err.split("fail_after=fail", 1)[-1]
        return ("harness_fail:" + tail.strip())[:max_len]
    return err[:max_len]


def build_react_system_prompt(stage: Stage, tool_schema_text: str) -> str:
    if stage is Stage.LOCALIZATION:
        return (
            "You are a software repair agent in the LOCALIZATION stage.\n"
            "Explore the repository with read-only tools to find likely bug locations.\n"
            "Respond with ONE JSON object per turn:\n"
            '{"action": "<tool_name>", "args": {...}}\n'
            "When done exploring, use:\n"
            '{"action": "finish_localization", "args": {"summary": "files and symbols to fix"}}\n'
            "Do not emit line numbers from memory; read files first.\n"
            "Available tools:\n"
            f"{tool_schema_text}"
        )
    return (
        "You are a software repair agent in the REPAIR stage.\n"
        "Read source files, then apply minimal structured edits.\n"
        "Respond with ONE JSON object per turn:\n"
        '{"action": "<tool_name>", "args": {...}}\n'
        "For edits use apply_edits with an edits array (replace, line_replace, anchor_replace).\n"
        "When ready, use submit_patch with empty args to export the fix.\n"
        "Copy exact anchor/old text from read_file output; do not guess.\n"
        "Available tools:\n"
        f"{tool_schema_text}"
    )


def build_react_monolithic_system_prompt(tool_schema_text: str) -> str:
    return (
        "You are a software repair agent fixing a real bug.\n"
        "Explore with read-only tools, then apply minimal edits and submit_patch.\n"
        "Respond with ONE JSON object per turn:\n"
        '{"action": "<tool_name>", "args": {...}}\n'
        "Available tools:\n"
        f"{tool_schema_text}"
    )


def build_react_issue_prompt(task: LiteTaskRecord, extra: str = "") -> str:
    issue = task.problem_statement.strip()
    if len(issue) > 1500:
        issue = issue[:1500] + "\n...[truncated]"
    block = (
        f"Repository: {task.repo}\n"
        f"Instance: {task.instance_id}\n"
        f"Base commit: {task.base_commit}\n\n"
        f"Bug report:\n{issue}\n"
    )
    if extra.strip():
        block += f"\n{extra.strip()}\n"
    return block


def format_tool_schema(tools: list[dict]) -> str:
    lines: list[str] = []
    for tool in tools:
        args = ", ".join(f"{key}: {typ}" for key, typ in tool.get("args", {}).items())
        lines.append(f"- {tool['name']}({args}): {tool['description']}")
    return "\n".join(lines)


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
    err = summarize_repair_error(error_message)
    return (
        f"{base}\n\n"
        f"Previous attempt #{attempt - 1} failed.\n"
        f"Edit/apply/test error:\n{err}\n\n"
        f"Previous output:\n```json\n{prev}\n```\n\n"
        "Regenerate the ENTIRE edits JSON from scratch.\n"
        "Do not describe the fix. Do not emit partial JSON.\n"
        "If error starts with `target_not_found`, try `line_replace` with one exact source line.\n"
        "If error starts with `parse_error:syntax`, fix indentation and use `line_replace` with exact anchor line.\n"
        "If error starts with `harness_fail`, the edit applied but tests failed — try a different minimal fix.\n"
        "Correct file paths and ensure anchors/old blocks match provided source files."
    )

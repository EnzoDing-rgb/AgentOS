from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepairEdit:
    op: str
    file: str
    old: str | None
    new: str
    anchor: str | None = None


@dataclass(frozen=True)
class RepairWorkspaceResult:
    patch_text: str | None
    error: str | None


PROMPT_INSTRUCTIONS = (
    "Repair step: output ONLY one ```json ... ``` block with this schema:\n"
    "{\n"
    '  "edits": [\n'
    '    {"op": "replace", "file": "path.py", "old": "exact old text", "new": "replacement text"},\n'
    '    {"op": "anchor_replace", "file": "path.py", "anchor": "nearby exact text", "old": "target text", "new": "replacement text"},\n'
    '    {"op": "insert_after", "file": "path.py", "anchor": "exact existing text", "new": "text to insert after anchor"},\n'
    '    {"op": "line_replace", "file": "path.py", "anchor": "exact single source line", "new": "full replacement line"}\n'
    "  ]\n"
    "}\n"
    "Rules:\n"
    "- Use repo-relative file paths\n"
    "- Modify source files only\n"
    "- Prefer `line_replace` for single-line fixes\n"
    "- Prefer `replace` when exact multi-line old text is visible\n"
    "- Keep edits minimal\n"
    "- No prose outside JSON"
)


def extract_json_block(text: str) -> str | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        parts = stripped.split("```")
        for block in parts:
            block = block.strip()
            if block.startswith("json"):
                return block[4:].strip()
            if block.startswith("{"):
                return block
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return stripped[start : end + 1]


def parse_repair_edits(text: str) -> tuple[list[RepairEdit] | None, str | None]:
    payload = extract_json_block(text)
    if payload is None:
        return None, "parse_error:no_json_block"
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, f"parse_error:invalid_json:{exc}"
    raw_edits = data.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        return None, "parse_error:missing_edits"
    edits: list[RepairEdit] = []
    for item in raw_edits:
        if not isinstance(item, dict):
            return None, "parse_error:edit_not_object"
        op = item.get("op", "replace")
        file = item.get("file")
        old = item.get("old")
        new = item.get("new")
        anchor = item.get("anchor")
        if not isinstance(op, str) or not isinstance(file, str) or not isinstance(new, str):
            return None, "parse_error:bad_edit_fields"
        if op in {"replace", "anchor_replace"} and not isinstance(old, str):
            return None, f"parse_error:missing_old:{op}"
        if op in {"anchor_replace", "insert_after", "insert_before", "line_replace"} and not isinstance(anchor, str):
            return None, f"parse_error:missing_anchor:{op}"
        edits.append(
            RepairEdit(
                op=op.strip(),
                file=file.strip(),
                old=old if isinstance(old, str) else None,
                new=new,
                anchor=anchor if isinstance(anchor, str) else None,
            )
        )
    return edits, None


def failure_class(error: str | None) -> str:
    if not error:
        return "unknown"
    if error.startswith("parse_error"):
        return "parse_error"
    if error.startswith("target_not_found"):
        return "target_not_found"
    if error.startswith("ambiguous_anchor"):
        return "ambiguous_anchor"
    if error.startswith("empty_diff"):
        return "empty_diff"
    if error.startswith("target_not_allowed"):
        return "target_not_allowed"
    if error.startswith("export_error"):
        return "export_error"
    if "IndentationError" in error or "SyntaxError" in error or error.startswith("parse_error:syntax"):
        return "syntax_error"
    if "fail_after=fail" in error or "fail_before=pass" in error:
        return "harness_fail"
    return "other"


def _validate_edit_target(edit: RepairEdit) -> str | None:
    if not edit.file.endswith(".py"):
        return f"target_not_allowed:non_python:{edit.file}"
    if "/tests/" in edit.file or edit.file.startswith("tests/"):
        return f"target_not_allowed:test_file:{edit.file}"
    return None


def _anchor_index(original: str, anchor: str) -> tuple[int | None, str | None]:
    count = original.count(anchor)
    if count == 0:
        return None, "target_not_found:anchor"
    if count > 1:
        return None, "ambiguous_anchor"
    return original.find(anchor), None


def _apply_exact_replace(original: str, edit: RepairEdit) -> tuple[str | None, str | None]:
    assert edit.old is not None
    count = original.count(edit.old)
    if count == 0:
        return None, "target_not_found:old_text"
    if count > 1:
        return None, "ambiguous_anchor:old_text"
    updated = original.replace(edit.old, edit.new, 1)
    if updated == original:
        return None, "empty_diff:replace"
    return updated, None


def _apply_anchor_replace(original: str, edit: RepairEdit) -> tuple[str | None, str | None]:
    assert edit.old is not None and edit.anchor is not None
    anchor_index, error = _anchor_index(original, edit.anchor)
    if error is not None:
        return None, error
    assert anchor_index is not None
    window_start = max(0, anchor_index - 1200)
    window_end = min(len(original), anchor_index + len(edit.anchor) + 1200)
    window = original[window_start:window_end]
    if edit.old not in window:
        if edit.old in original and original.count(edit.old) == 1:
            updated = original.replace(edit.old, edit.new, 1)
            return updated, None
        return None, "target_not_found:anchored_old"
    replaced_window = window.replace(edit.old, edit.new, 1)
    updated = original[:window_start] + replaced_window + original[window_end:]
    if updated == original:
        return None, "empty_diff:anchor_replace"
    return updated, None


def _apply_insert_after(original: str, edit: RepairEdit) -> tuple[str | None, str | None]:
    assert edit.anchor is not None
    anchor_index, error = _anchor_index(original, edit.anchor)
    if error is not None:
        return None, error
    assert anchor_index is not None
    insert_at = anchor_index + len(edit.anchor)
    updated = original[:insert_at] + edit.new + original[insert_at:]
    if updated == original:
        return None, "empty_diff:insert_after"
    return updated, None


def _apply_insert_before(original: str, edit: RepairEdit) -> tuple[str | None, str | None]:
    assert edit.anchor is not None
    anchor_index, error = _anchor_index(original, edit.anchor)
    if error is not None:
        return None, error
    assert anchor_index is not None
    updated = original[:anchor_index] + edit.new + original[anchor_index:]
    if updated == original:
        return None, "empty_diff:insert_before"
    return updated, None


def _apply_line_replace(original: str, edit: RepairEdit) -> tuple[str | None, str | None]:
    assert edit.anchor is not None
    lines = original.splitlines(keepends=True)
    anchor = edit.anchor.rstrip("\n")
    anchor_stripped = anchor.strip()
    match_indexes = [index for index, line in enumerate(lines) if line.rstrip("\n") == anchor]
    if not match_indexes:
        match_indexes = [index for index, line in enumerate(lines) if line.rstrip("\n").strip() == anchor_stripped]
    if not match_indexes:
        match_indexes = [index for index, line in enumerate(lines) if anchor_stripped in line]
    if not match_indexes:
        return None, "target_not_found:line"
    if len(match_indexes) > 1:
        return None, "ambiguous_anchor:line"
    index = match_indexes[0]
    suffix = "\n" if lines[index].endswith("\n") else ""
    current_line = lines[index].rstrip("\n")
    indent = current_line[: len(current_line) - len(current_line.lstrip())]
    replacement = indent + edit.new.rstrip("\n").lstrip()
    new_line = replacement + suffix
    lines[index] = new_line
    updated = "".join(lines)
    if updated == original:
        return None, "empty_diff:line_replace"
    return updated, None


def _validate_python_syntax(repo_dir: Path, rel_path: str) -> str | None:
    file_path = repo_dir / rel_path
    try:
        ast.parse(file_path.read_text())
    except SyntaxError as exc:
        return f"parse_error:syntax:{rel_path}:{exc.msg}"
    return None


def _restore_files(repo_dir: Path, originals: dict[str, str]) -> None:
    for rel_path, content in originals.items():
        (repo_dir / rel_path).write_text(content)


def apply_repair_edits(repo_dir: Path, edits: list[RepairEdit]) -> tuple[bool, str | None]:
    originals: dict[str, str] = {}
    touched = False
    for edit in edits:
        target_error = _validate_edit_target(edit)
        if target_error is not None:
            _restore_files(repo_dir, originals)
            return False, target_error
        file_path = repo_dir / edit.file
        if not file_path.is_file():
            _restore_files(repo_dir, originals)
            return False, f"target_not_found:file:{edit.file}"
        if edit.file not in originals:
            originals[edit.file] = file_path.read_text()
        original = file_path.read_text()
        if edit.op == "replace":
            updated, error = _apply_exact_replace(original, edit)
        elif edit.op == "anchor_replace":
            updated, error = _apply_anchor_replace(original, edit)
        elif edit.op == "insert_after":
            updated, error = _apply_insert_after(original, edit)
        elif edit.op == "insert_before":
            updated, error = _apply_insert_before(original, edit)
        elif edit.op == "line_replace":
            updated, error = _apply_line_replace(original, edit)
        else:
            _restore_files(repo_dir, originals)
            return False, f"parse_error:unknown_op:{edit.op}"
        if error is not None or updated is None:
            _restore_files(repo_dir, originals)
            return False, error or "edit_apply_failed"
        file_path.write_text(updated)
        syntax_error = _validate_python_syntax(repo_dir, edit.file)
        if syntax_error is not None:
            _restore_files(repo_dir, originals)
            return False, syntax_error
        touched = True
    if not touched:
        return False, "empty_diff:no_edits_applied"
    return True, None


def export_workspace_patch(repo_dir: Path) -> RepairWorkspaceResult:
    result = subprocess.run(["git", "diff", "--no-ext-diff"], cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        return RepairWorkspaceResult(None, f"export_error:git_diff:{detail}")
    patch_text = result.stdout.strip()
    if not patch_text:
        return RepairWorkspaceResult(None, "empty_diff:git_diff")
    return RepairWorkspaceResult(patch_text=patch_text, error=None)


def realize_repair_edits(repo_dir: Path, repair_text: str) -> tuple[str | None, str | None]:
    edits, edit_error = parse_repair_edits(repair_text)
    if edits is None:
        return None, edit_error
    ok, apply_error = apply_repair_edits(repo_dir, edits)
    if not ok:
        return None, apply_error
    exported = export_workspace_patch(repo_dir)
    if exported.patch_text is None:
        return None, exported.error
    return exported.patch_text, None

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepairEdit:
    file: str
    old: str
    new: str


@dataclass(frozen=True)
class RepairWorkspaceResult:
    patch_text: str | None
    error: str | None


PROMPT_INSTRUCTIONS = (
    "Repair step: output ONLY one ```json ... ``` block with this schema:\n"
    "{\n"
    '  "edits": [\n'
    "    {\"file\": \"path.py\", \"old\": \"exact old text\", \"new\": \"replacement text\"}\n"
    "  ]\n"
    "}\n"
    "Rules:\n"
    "- Use repo-relative file paths\n"
    "- `old` must match exact file text\n"
    "- Keep edits minimal\n"
    "- Modify source files only\n"
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
        return None, "no json block found in repair response"
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, f"invalid json edit payload: {exc}"
    raw_edits = data.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        return None, "missing edits list"
    edits: list[RepairEdit] = []
    for item in raw_edits:
        if not isinstance(item, dict):
            return None, "edit item is not an object"
        file = item.get("file")
        old = item.get("old")
        new = item.get("new")
        if not isinstance(file, str) or not isinstance(old, str) or not isinstance(new, str):
            return None, "edit fields must be strings"
        edits.append(RepairEdit(file=file.strip(), old=old, new=new))
    return edits, None


def apply_repair_edits(repo_dir: Path, edits: list[RepairEdit]) -> tuple[bool, str | None]:
    touched = False
    for edit in edits:
        if not edit.file.endswith(".py"):
            return False, f"non-python edit target: {edit.file}"
        if "/tests/" in edit.file or edit.file.startswith("tests/"):
            return False, f"test file edit forbidden: {edit.file}"
        file_path = repo_dir / edit.file
        if not file_path.is_file():
            return False, f"missing target file: {edit.file}"
        original = file_path.read_text()
        if edit.old not in original:
            return False, f"old text not found in {edit.file}"
        updated = original.replace(edit.old, edit.new, 1)
        if updated == original:
            return False, f"edit made no change in {edit.file}"
        file_path.write_text(updated)
        touched = True
    if not touched:
        return False, "no edits applied"
    return True, None


def export_workspace_patch(repo_dir: Path) -> RepairWorkspaceResult:
    result = subprocess.run(["git", "diff", "--no-ext-diff"], cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        return RepairWorkspaceResult(None, f"git diff failed: {detail}")
    patch_text = result.stdout.strip()
    if not patch_text:
        return RepairWorkspaceResult(None, "git diff produced empty patch")
    return RepairWorkspaceResult(patch_text=patch_text, error=None)

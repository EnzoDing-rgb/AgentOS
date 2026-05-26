from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .repair_workspace import apply_repair_edits, export_workspace_patch, parse_repair_edits
from .types import Stage


MAX_OUTPUT_CHARS = 8000
MAX_READ_LINES = 200
MAX_GREP_MATCHES = 40


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str
    error: str | None = None


READONLY_TOOLS = frozenset({"read_file", "grep", "glob", "search_defs"})
WRITE_TOOLS = frozenset({"apply_edits", "submit_patch"})


def tools_for_stage(stage: Stage) -> frozenset[str]:
    if stage is Stage.LOCALIZATION:
        return READONLY_TOOLS
    if stage is Stage.REPAIR:
        return READONLY_TOOLS | WRITE_TOOLS
    return READONLY_TOOLS


def tool_schemas(stage: Stage) -> list[dict]:
    allowed = tools_for_stage(stage)
    schemas: list[dict] = []
    if "read_file" in allowed:
        schemas.append(
            {
                "name": "read_file",
                "description": "Read a repo-relative file; optional 1-based line window.",
                "args": {"path": "str", "start": "int optional", "end": "int optional"},
            }
        )
    if "grep" in allowed:
        schemas.append(
            {
                "name": "grep",
                "description": "Search pattern in repo (rg/grep). Returns matching lines with paths.",
                "args": {"pattern": "str", "path": "str optional"},
            }
        )
    if "glob" in allowed:
        schemas.append(
            {
                "name": "glob",
                "description": "Find files by glob under repo root.",
                "args": {"pattern": "str"},
            }
        )
    if "search_defs" in allowed:
        schemas.append(
            {
                "name": "search_defs",
                "description": "Find Python def/class lines matching a symbol substring.",
                "args": {"symbol": "str"},
            }
        )
    if "apply_edits" in allowed:
        schemas.append(
            {
                "name": "apply_edits",
                "description": "Apply structured source edits (replace/line_replace/etc.).",
                "args": {"edits": "list of edit objects"},
            }
        )
    if "submit_patch" in allowed:
        schemas.append(
            {
                "name": "submit_patch",
                "description": "Export current workspace git diff and finish repair.",
                "args": {},
            }
        )
    return schemas


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n...[truncated]"


def _resolve_path(repo_dir: Path, rel_path: str) -> Path | None:
    clean = rel_path.strip().lstrip("./")
    if not clean or clean.startswith(".."):
        return None
    full = (repo_dir / clean).resolve()
    try:
        full.relative_to(repo_dir.resolve())
    except ValueError:
        return None
    return full


def _read_file(repo_dir: Path, args: dict) -> ToolResult:
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        return ToolResult(False, "", "missing path")
    full = _resolve_path(repo_dir, path)
    if full is None or not full.is_file():
        return ToolResult(False, "", f"file not found: {path}")
    if "/tests/" in full.as_posix().replace(str(repo_dir), "") and full.name.endswith(".py"):
        pass
    lines = full.read_text(errors="replace").splitlines()
    start = args.get("start")
    end = args.get("end")
    if isinstance(start, int) or isinstance(end, int):
        s = max(1, int(start)) if isinstance(start, int) else 1
        e = min(len(lines), int(end)) if isinstance(end, int) else min(len(lines), s + MAX_READ_LINES - 1)
        if e < s:
            e = s
        window = lines[s - 1 : e]
        body = "\n".join(window)
        header = f"File: {path} (lines {s}-{e} of {len(lines)})\n"
    else:
        if len(lines) > MAX_READ_LINES:
            window = lines[:MAX_READ_LINES]
            body = "\n".join(window)
            header = f"File: {path} (first {MAX_READ_LINES} of {len(lines)} lines)\n"
        else:
            body = "\n".join(lines)
            header = f"File: {path} ({len(lines)} lines)\n"
    return ToolResult(True, _truncate(header + body))


def _grep(repo_dir: Path, args: dict) -> ToolResult:
    pattern = args.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        return ToolResult(False, "", "missing pattern")
    search_path = args.get("path")
    cmd = ["rg", "-n", "--no-heading", "--color=never", pattern, "."]
    if isinstance(search_path, str) and search_path.strip():
        rel = _resolve_path(repo_dir, search_path)
        if rel is None:
            return ToolResult(False, "", f"path not found: {search_path}")
        cmd = ["rg", "-n", "--no-heading", "--color=never", pattern, str(rel.relative_to(repo_dir))]
    try:
        result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        cmd = ["grep", "-RIn", pattern, "."]
        if isinstance(search_path, str) and search_path.strip():
            rel = _resolve_path(repo_dir, search_path)
            cmd = ["grep", "-RIn", pattern, str(rel.relative_to(repo_dir)) if rel else search_path]
        result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, timeout=30)
    lines = (result.stdout or "").splitlines()
    if not lines and result.returncode not in (0, 1):
        err = (result.stderr or result.stdout or "grep failed").strip()
        return ToolResult(False, "", err)
    if not lines:
        return ToolResult(True, "no matches")
    trimmed = lines[:MAX_GREP_MATCHES]
    body = "\n".join(trimmed)
    if len(lines) > MAX_GREP_MATCHES:
        body += f"\n...[truncated {len(lines) - MAX_GREP_MATCHES} more matches]"
    return ToolResult(True, body)


def _glob(repo_dir: Path, args: dict) -> ToolResult:
    pattern = args.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        return ToolResult(False, "", "missing pattern")
    matches = sorted(p.relative_to(repo_dir).as_posix() for p in repo_dir.glob(pattern))
    if not matches:
        return ToolResult(True, "no matches")
    body = "\n".join(matches[:80])
    if len(matches) > 80:
        body += f"\n...[truncated {len(matches) - 80} more]"
    return ToolResult(True, body)


def _search_defs(repo_dir: Path, args: dict) -> ToolResult:
    symbol = args.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        return ToolResult(False, "", "missing symbol")
    pattern = rf"^\s*(def|class)\s+{re.escape(symbol)}"
    return _grep(repo_dir, {"pattern": pattern, "path": "."})


def _apply_edits(repo_dir: Path, args: dict) -> ToolResult:
    raw_edits = args.get("edits")
    if not isinstance(raw_edits, list):
        return ToolResult(False, "", "edits must be a list")
    payload = json.dumps({"edits": raw_edits})
    edits, err = parse_repair_edits(payload)
    if edits is None:
        return ToolResult(False, "", err or "parse_error")
    ok, apply_err = apply_repair_edits(repo_dir, edits)
    if not ok:
        return ToolResult(False, "", apply_err or "apply_failed")
    exported = export_workspace_patch(repo_dir)
    if exported.patch_text:
        preview = exported.patch_text.splitlines()[:30]
        return ToolResult(True, "edits applied\n" + _truncate("\n".join(preview)))
    return ToolResult(True, "edits applied (no diff yet)")


def _submit_patch(repo_dir: Path) -> ToolResult:
    exported = export_workspace_patch(repo_dir)
    if exported.error:
        return ToolResult(False, "", exported.error)
    if not exported.patch_text:
        return ToolResult(False, "", "empty_diff:git_diff")
    return ToolResult(True, exported.patch_text)


def parse_tool_action(text: str) -> tuple[str | None, dict | None, str | None]:
    stripped = text.strip()
    payload = stripped
    if "```" in stripped:
        for block in stripped.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                payload = block
                break
    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end <= start:
        return None, None, "parse_error:no_json_action"
    try:
        data = json.loads(payload[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, None, f"parse_error:invalid_json:{exc}"
    action = data.get("action") or data.get("tool")
    if not isinstance(action, str) or not action.strip():
        return None, None, "parse_error:missing_action"
    args = data.get("args") or data.get("arguments") or {}
    if not isinstance(args, dict):
        return None, None, "parse_error:bad_args"
    return action.strip(), args, None


def execute_tool(repo_dir: Path, stage: Stage, action: str, args: dict) -> ToolResult:
    allowed = tools_for_stage(stage)
    if action not in allowed:
        return ToolResult(False, "", f"tool_not_allowed:{action}:{stage.value}")
    if action == "read_file":
        return _read_file(repo_dir, args)
    if action == "grep":
        return _grep(repo_dir, args)
    if action == "glob":
        return _glob(repo_dir, args)
    if action == "search_defs":
        return _search_defs(repo_dir, args)
    if action == "apply_edits":
        return _apply_edits(repo_dir, args)
    if action == "submit_patch":
        return _submit_patch(repo_dir)
    return ToolResult(False, "", f"unknown_tool:{action}")

from __future__ import annotations

import re
from pathlib import Path

from .lite_tasks import LiteTaskRecord
from .local_harness import clone_or_checkout


def parse_candidate_paths(text: str) -> list[str]:
    paths: list[str] = []
    patterns = [
        r"`([A-Za-z0-9_./-]+\.py)`",
        r"\b([A-Za-z0-9_./-]+\.py)\b",
        r"\b([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)\b",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            candidate = match.replace(".", "/") + ("" if match.endswith(".py") else ".py")
            if candidate.endswith(".py.py"):
                candidate = candidate.removesuffix(".py")
            if "/" in candidate and candidate not in paths:
                paths.append(candidate)
    return paths


def module_guess_paths(task: LiteTaskRecord) -> list[str]:
    guesses: list[str] = []
    for token in re.findall(r"`?([A-Za-z][A-Za-z0-9_.]+)`?", task.problem_statement):
        if token.count(".") >= 2:
            guesses.append(token.replace(".", "/") + ".py")
    return guesses


def resolve_repo_paths(repo_dir: Path, candidates: list[str]) -> list[str]:
    resolved: list[str] = []
    for candidate in candidates:
        path = candidate.lstrip("./")
        full = repo_dir / path
        if full.is_file():
            resolved.append(path)
            continue
        name = Path(path).name
        for match in repo_dir.rglob(name):
            rel = match.relative_to(repo_dir).as_posix()
            if rel.endswith(".py") and rel not in resolved:
                resolved.append(rel)
                break
    return resolved


def _anchor_line(lines: list[str], task: LiteTaskRecord) -> int:
    statement = task.problem_statement.lower()
    candidates: list[int] = []
    for index, line in enumerate(lines, start=1):
        lower = line.lower()
        if "tensorproduct" in statement and "tensorproduct" in lower:
            candidates.append(index)
        if "expand" in statement and "expand" in lower:
            candidates.append(index)
        if "trace" in statement and "trace" in lower:
            candidates.append(index)
    if candidates:
        return candidates[0]
    return 1


def read_file_snippets(repo_dir: Path, task: LiteTaskRecord, paths: list[str], max_lines: int = 120) -> str:
    blocks: list[str] = []
    for path in paths[:3]:
        full = repo_dir / path
        if not full.is_file():
            continue
        lines = full.read_text(errors="replace").splitlines()
        anchor = _anchor_line(lines, task)
        start = max(1, anchor - 40)
        end = min(len(lines), start + max_lines - 1)
        if end - start + 1 < max_lines and len(lines) > max_lines:
            start = max(1, end - max_lines + 1)
        window = lines[start - 1 : end]
        body = "\n".join(f"{start + index:4d}| {line}" for index, line in enumerate(window))
        if start > 1:
            body = "...[truncated]\n" + body
        if end < len(lines):
            body += "\n...[truncated]"
        blocks.append(f"### {path}\n```python\n{body}\n```")
    return "\n\n".join(blocks)


def build_repair_file_context(task: LiteTaskRecord, localization_text: str) -> tuple[str, list[str]]:
    repo_dir = clone_or_checkout(task)
    candidates = parse_candidate_paths(localization_text)
    if not candidates:
        candidates = module_guess_paths(task)
    paths = resolve_repo_paths(repo_dir, candidates)
    snippets = read_file_snippets(repo_dir, task, paths)
    return snippets, paths

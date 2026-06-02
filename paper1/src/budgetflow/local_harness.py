from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .lite_tasks import LiteTaskRecord
from .console_log import (
    _BOLD,
    _BRIGHT_BLUE,
    _BRIGHT_CYAN,
    _BRIGHT_GREEN,
    _BRIGHT_YELLOW,
    dim,
    paint,
    tag,
)

PAPER1_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PAPER1_ROOT / "data" / "repo_cache"
WORKTREE_ROOT = CACHE_DIR / "worktrees"
LEGACY_CACHE_DIR = PAPER1_ROOT / "src" / "data" / "repo_cache"

_COLLECTIONS_ABC = frozenset(
    {
        "Mapping",
        "MutableMapping",
        "MutableSet",
        "Iterable",
        "Hashable",
        "Callable",
        "Sequence",
        "Container",
        "Iterator",
        "Generator",
    }
)


class RepoHarnessAdapter:
    """Per-repo harness compatibility seam.

    Each subclass handles repo-specific quirks:
    - compat patches that must run during harness eval but not leak into model patch
    - test name mapping from SWE-bench format to pytest node ids
    """

    repo_slug: str

    def apply_compat(self, repo_dir: Path) -> list[str]:
        """Apply repo-specific compat fixes. Returns list of changed file paths."""
        return []

    def map_test_name(self, raw_name: str) -> str | None:
        """Map SWE-bench test name to pytest node id. Returns None if no mapping needed."""
        return None

    def pytest_env(self) -> dict[str, str]:
        """Extra env vars to set when running pytest for this repo."""
        return {}

    @staticmethod
    def for_task(task) -> "RepoHarnessAdapter":
        repo = getattr(task, "repo", "")
        slug = repo.replace("/", "__") if repo else ""
        if slug == "sympy__sympy":
            return SymPyHAdapter()
        if slug == "django__django":
            return DjangoHAdapter()
        if slug == "psf__requests":
            return RequestsHAdapter()
        return DefaultHAdapter()


class SymPyHAdapter(RepoHarnessAdapter):
    repo_slug = "sympy__sympy"

    def apply_compat(self, repo_dir: Path) -> list[str]:
        latex_py = repo_dir / "sympy" / "printing" / "latex.py"
        if not latex_py.is_file():
            return []
        original = latex_py.read_text(encoding="utf-8", errors="ignore")
        # mpmath 1.4.1 returns 'inf' without '+', old sympy expects '+inf'
        patched = original.replace(
            'elif str_real == "+inf":\n            return r"\\infty"',
            'elif str_real in ("+inf", "inf"):\n            return r"\\infty"',
        )
        if patched != original:
            latex_py.write_text(patched)
            return ["sympy/printing/latex.py"]
        return []


_DJANGO_TEST_NAME_RE = re.compile(r"^(\w+)\s+\((.+)\.(\w+)\)$")


class DjangoHAdapter(RepoHarnessAdapter):
    repo_slug = "django__django"

    def pytest_env(self) -> dict[str, str]:
        return {"DJANGO_SETTINGS_MODULE": "tests.test_sqlite"}

    def map_test_name(self, raw_name: str) -> str | None:
        # Format: "test_name (dotted.module.ClassName)"
        m = _DJANGO_TEST_NAME_RE.match(raw_name)
        if m:
            test_name, module_path, class_name = m.group(1), m.group(2), m.group(3)
            file_path = f"tests/{module_path.replace('.', '/')}.py"
            return f"{file_path}::{class_name}::{test_name}"
        # Also handle: "path.py::test_name (module.ClassName)"
        m2 = re.match(r"^(.+\.py)::(\w+)\s+\(.*?\.(\w+)\)$", raw_name)
        if m2:
            return f"{m2.group(1)}::{m2.group(3)}::{m2.group(2)}"
        return None


class RequestsHAdapter(RepoHarnessAdapter):
    repo_slug = "psf__requests"


class DefaultHAdapter(RepoHarnessAdapter):
    repo_slug = ""


def harness_python() -> str:
    return os.environ.get("BUDGETFLOW_HARNESS_PYTHON", sys.executable)


def _split_collections_import_line(line: str) -> list[str] | None:
    match = re.match(r"^(\s*)from collections import (.+)$", line)
    if not match:
        return None
    indent, tail = match.group(1), match.group(2).strip()
    if tail.startswith("("):
        return None
    names = [part.strip() for part in tail.split(",") if part.strip()]
    abc = [name for name in names if name in _COLLECTIONS_ABC]
    std = [name for name in names if name not in _COLLECTIONS_ABC]
    if not abc:
        return None
    out: list[str] = []
    if std:
        out.append(f"{indent}from collections import {', '.join(std)}")
    out.append(f"{indent}from collections.abc import {', '.join(abc)}")
    return out


def _split_collections_import_block(block_lines: list[str]) -> list[str] | None:
    indent = re.match(r"^(\s*)", block_lines[0]).group(1)
    joined = " ".join(line.strip() for line in block_lines)
    inner = re.search(r"from collections import \((.+)\)", joined, re.DOTALL)
    if not inner:
        return None
    names = [part.strip() for part in inner.group(1).replace("\n", " ").split(",") if part.strip()]
    abc = [name for name in names if name in _COLLECTIONS_ABC]
    std = [name for name in names if name not in _COLLECTIONS_ABC]
    if not abc:
        return None
    out: list[str] = []
    if std:
        out.append(f"{indent}from collections import {', '.join(std)}")
    out.append(f"{indent}from collections.abc import {', '.join(abc)}")
    return out


def _patch_collections_import_block(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*from collections import \(", line):
            block = [line]
            i += 1
            while i < len(lines) and ")" not in block[-1]:
                block.append(lines[i])
                i += 1
            split = _split_collections_import_block(block)
            if split:
                out.extend(split)
                continue
            out.extend(block)
            continue
        split = _split_collections_import_line(line)
        if split:
            out.extend(split)
        else:
            out.append(line)
        i += 1
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _patch_collections_attr_usage(text: str) -> str:
    """Rewrite `collections.Mapping` style attribute refs for Python 3.10+."""
    names = "|".join(sorted(_COLLECTIONS_ABC, key=len, reverse=True))
    pattern = rf"\bcollections\.(?!abc\.)({names})\b"
    return re.sub(pattern, r"collections.abc.\1", text)


def _patch_python_compat_text(text: str) -> str:
    return _patch_collections_attr_usage(_patch_collections_import_block(text))


def apply_python_compat(repo_dir: Path) -> tuple[str, ...]:
    """Patch legacy collections ABC usage for Python 3.10+."""
    if sys.version_info < (3, 10):
        return ()
    changed_paths: list[str] = []
    for path in repo_dir.rglob("*.py"):
        original = path.read_text(encoding="utf-8", errors="ignore")
        patched = _patch_python_compat_text(original)
        if patched != original:
            path.write_text(patched)
            changed_paths.append(str(path.relative_to(repo_dir)))
    if changed_paths:
        print(
            f"{tag('prep')} py{sys.version_info.major}.{sys.version_info.minor} "
            f"collections compat {paint(str(len(changed_paths)), _BRIGHT_GREEN)} files",
            flush=True,
        )
    return tuple(changed_paths)


_LAST_COMPAT_FILES: tuple[str, ...] = ()
_MAIN_REPO_LOCKS: dict[str, threading.Lock] = {}
_MAIN_REPO_LOCKS_GUARD = threading.Lock()


def _main_repo_lock(slug: str) -> threading.Lock:
    with _MAIN_REPO_LOCKS_GUARD:
        lock = _MAIN_REPO_LOCKS.get(slug)
        if lock is None:
            lock = threading.Lock()
            _MAIN_REPO_LOCKS[slug] = lock
        return lock


def get_last_compat_files() -> tuple[str, ...]:
    return _LAST_COMPAT_FILES


@dataclass(frozen=True)
class HarnessResult:
    instance_id: str
    patch_applied: bool
    harness_resolved: bool
    fail_to_pass_passed: bool
    pass_to_pass_passed: bool
    detail: str
    repo_dir: str
    test_patch_ok: bool | None = None
    fail_before: bool | None = None
    model_patch_ok: bool | None = None
    fail_after: bool | None = None
    fail_to_pass: tuple[str, ...] = ()
    pass_to_pass: tuple[str, ...] = ()


def repo_slug(repo: str) -> str:
    return repo.replace("/", "__")


def repo_dir_for(task: LiteTaskRecord) -> Path:
    slug = repo_slug(task.repo)
    primary = CACHE_DIR / slug
    legacy = LEGACY_CACHE_DIR / slug
    if primary.exists():
        return primary
    if legacy.exists():
        return legacy
    return primary


def _pip_marker_path(repo_dir: Path) -> Path:
    return repo_dir.parent / f"{repo_dir.name}.pip_ok"


def _ensure_commit_available(repo_dir: Path, commit: str) -> None:
    """Fetch commit into the bare/main clone if missing. Does not checkout main HEAD."""
    has_commit = subprocess.run(
        ["git", "cat-file", "-e", commit],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    ).returncode == 0
    if has_commit:
        return
    fetch_attempts = (
        ["git", "fetch", "--depth", "1", "origin", commit],
        ["git", "fetch", "origin", commit],
        ["git", "fetch", "origin"],
    )
    last_error = ""
    for cmd in fetch_attempts:
        result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
        if result.returncode == 0:
            return
        last_error = (result.stderr or result.stdout or "").strip()
    raise subprocess.CalledProcessError(1, fetch_attempts[-1], last_error)


def _pip_install_editable(repo_dir: Path, *, task: LiteTaskRecord) -> subprocess.CompletedProcess:
    cmd = [harness_python(), "-m", "pip", "install", "-e", "."]
    print(f"{tag('prep')} pip install -e . {dim('(sympy ~3-8 min, streaming below)')}", flush=True)
    started = time.time()
    last_pulse = started
    proc = subprocess.Popen(
        cmd,
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        if not line:
            continue
        # pip progress: "Collecting...", "Installing...", "Building wheel..."
        if any(token in line for token in ("Collecting", "Installing", "Building", "Preparing", "Successfully")):
            print(f"  {tag('pip', color=_BRIGHT_BLUE)} {line[:140]}", flush=True)
        now = time.time()
        if now - last_pulse >= 20:
            elapsed = paint(f"{now - started:.0f}s", _BRIGHT_YELLOW, _BOLD)
            print(f"{tag('prep')} pip running elapsed={elapsed} ...", flush=True)
            last_pulse = now
    proc.wait()
    elapsed = time.time() - started
    rc = proc.returncode if proc.returncode is not None else 1
    print(f"{tag('prep')} pip finished rc={rc} elapsed={elapsed:.0f}s", flush=True)
    return subprocess.CompletedProcess(cmd, rc, "", "")


def _ensure_main_repo(task: LiteTaskRecord) -> Path:
    repo_dir = repo_dir_for(task)
    repo_url = f"https://github.com/{task.repo}.git"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        print(f"{tag('prep')} git clone {paint(task.repo, _BRIGHT_CYAN)} ...", flush=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", repo_url, str(repo_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    return repo_dir


def _remove_worktree(main_repo: Path, worktree_path: Path) -> None:
    if worktree_path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=main_repo,
            capture_output=True,
            text=True,
        )
    if worktree_path.exists():
        import shutil

        shutil.rmtree(worktree_path, ignore_errors=True)
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=main_repo,
        capture_output=True,
        text=True,
    )


def _prepare_worktree(task: LiteTaskRecord, workspace_key: str) -> Path:
    slug = repo_slug(task.repo)
    with _main_repo_lock(slug):
        main_repo = _ensure_main_repo(task)
        worktree_path = WORKTREE_ROOT / slug / workspace_key
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        _remove_worktree(main_repo, worktree_path)
        _ensure_commit_available(main_repo, task.base_commit)
        inst = paint(task.instance_id, _BOLD, _BRIGHT_CYAN)
        print(
            f"{tag('prep')} worktree {inst} key={workspace_key} @ {task.base_commit[:8]} ...",
            flush=True,
        )
        subprocess.run(
            ["git", "worktree", "add", "--force", str(worktree_path), task.base_commit],
            cwd=main_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "reset", "--hard", task.base_commit],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["git", "clean", "-fdx"], cwd=worktree_path, check=True, capture_output=True, text=True)
    return worktree_path


def _finalize_repo_workspace(repo_dir: Path, task: LiteTaskRecord) -> Path:
    global _LAST_COMPAT_FILES
    _LAST_COMPAT_FILES = apply_python_compat(repo_dir)

    marker = _pip_marker_path(repo_dir)
    if marker.exists() and marker.read_text().strip() == task.base_commit:
        print(f"{tag('prep')} pip skip {dim('(cached)')}", flush=True)
        return repo_dir

    install = _pip_install_editable(repo_dir, task=task)
    if install.returncode == 0:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(task.base_commit)
        print(f"{tag('prep')} pip {paint('done', _BRIGHT_GREEN)}", flush=True)
    else:
        print(f"{tag('prep')} pip failed (rc={install.returncode}), continuing anyway", flush=True)
    return repo_dir


def clone_or_checkout(task: LiteTaskRecord, *, workspace_key: str | None = None) -> Path:
    if workspace_key:
        repo_dir = _prepare_worktree(task, workspace_key)
        return _finalize_repo_workspace(repo_dir, task)

    slug = repo_slug(task.repo)
    with _main_repo_lock(slug):
        global _LAST_COMPAT_FILES
        repo_dir = _ensure_main_repo(task)
        inst = paint(task.instance_id, _BOLD, _BRIGHT_CYAN)
        print(f"{tag('prep')} checkout {inst} @ {task.base_commit[:8]} ...", flush=True)
        subprocess.run(["git", "reset", "--hard", task.base_commit], cwd=repo_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "clean", "-fdx"], cwd=repo_dir, check=True, capture_output=True, text=True)
        return _finalize_repo_workspace(repo_dir, task)


def apply_patch(repo_dir: Path, patch_text: str, label: str) -> tuple[bool, str]:
    if not patch_text.strip():
        return False, f"{label}: empty patch"
    if not patch_text.lstrip().startswith("diff --git"):
        first_file = None
        for line in patch_text.splitlines():
            if line.startswith("--- a/"):
                first_file = line[6:].strip()
                break
        if first_file:
            patch_text = f"diff --git a/{first_file} b/{first_file}\n{patch_text}"
    patch_file = repo_dir / f".budgetflow_{label}.patch"
    patch_file.write_text(patch_text)
    result = subprocess.run(
        ["git", "apply", "--verbose", str(patch_file)],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    patch_file.unlink(missing_ok=True)
    if result.returncode != 0:
        return False, result.stderr.strip() or result.stdout.strip()
    return True, "ok"


def test_paths_for(task: LiteTaskRecord) -> list[str]:
    paths: list[str] = []
    for patch_text in (task.test_patch, task.patch):
        for line in patch_text.splitlines():
            if line.startswith("+++ b/") and "/tests/" in line:
                path = line[6:].strip()
                if path.endswith(".py"):
                    paths.append(path)
    return list(dict.fromkeys(paths))


def _node_path(node_id: str) -> str:
    return node_id.split("::", 1)[0]


def build_pytest_node_ids(
    repo_dir: Path,
    test_names: tuple[str, ...],
    test_paths: list[str],
    adapter: RepoHarnessAdapter | None = None,
) -> tuple[list[str], list[str]]:
    node_ids: list[str] = []
    missing: list[str] = []
    test_path_set = set(test_paths)
    resolved: set[int] = set()
    for idx, name in enumerate(test_names):
        if adapter:
            mapped = adapter.map_test_name(name)
            if mapped:
                name = mapped
                resolved.add(idx)
        if "::" not in name:
            continue
        path = _node_path(name)
        if not test_path_set or path in test_path_set or (repo_dir / path).exists():
            node_ids.append(name)
        else:
            missing.append(name)
    for path in test_paths:
        full = repo_dir / path
        text = full.read_text() if full.is_file() else ""
        for idx, name in enumerate(test_names):
            if idx in resolved:
                continue
            if "::" in name:
                continue
            if f"def {name}(" in text:
                node_ids.append(f"{path}::{name}")
            else:
                missing.append(f"{path}::{name}")
    return list(dict.fromkeys(node_ids)), missing


def run_pytest(
    repo_dir: Path,
    test_names: tuple[str, ...],
    test_paths: list[str],
    adapter: RepoHarnessAdapter | None = None,
) -> tuple[bool, str]:
    if not test_names:
        return False, "no test names"
    node_ids, missing = build_pytest_node_ids(repo_dir, test_names, test_paths, adapter=adapter)
    if not node_ids:
        detail = ", ".join(missing[:6]) if missing else "none"
        return False, f"no pytest node ids: {detail}"
    cmd = [harness_python(), "-m", "pytest", "-x", *node_ids]
    env = None
    if adapter:
        extra_env = adapter.pytest_env()
        if extra_env:
            env = {**os.environ, **extra_env}
    result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, env=env)
    output = (result.stdout + "\n" + result.stderr).strip()
    tail = output[-2000:] if len(output) > 2000 else output
    return result.returncode == 0, tail


def evaluate_local_harness(
    task: LiteTaskRecord,
    model_patch: str | None,
    *,
    workspace_key: str | None = None,
) -> HarnessResult:
    repo_dir = repo_dir_for(task)
    detail_parts: list[str] = []
    if model_patch is None:
        return HarnessResult(
            instance_id=task.instance_id,
            patch_applied=False,
            harness_resolved=False,
            fail_to_pass_passed=False,
            pass_to_pass_passed=False,
            detail="no model patch extracted",
            repo_dir=str(repo_dir),
            fail_to_pass=task.fail_to_pass,
            pass_to_pass=task.pass_to_pass,
        )

    try:
        repo_dir = clone_or_checkout(task, workspace_key=workspace_key)
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or str(exc)).strip()
        return HarnessResult(
            instance_id=task.instance_id,
            patch_applied=False,
            harness_resolved=False,
            fail_to_pass_passed=False,
            pass_to_pass_passed=False,
            detail=f"repo checkout failed: {output[-1000:]}",
            repo_dir=str(repo_dir),
        )

    adapter = RepoHarnessAdapter.for_task(task)
    compat_files = adapter.apply_compat(repo_dir)
    if compat_files:
        detail_parts.append(f"compat={','.join(compat_files)}")

    test_paths = test_paths_for(task)
    test_patch_ok: bool | None = None
    if task.test_patch:
        test_patch_ok, msg = apply_patch(repo_dir, task.test_patch, "test_patch")
        detail_parts.append(f"test_patch={'ok' if test_patch_ok else msg}")
        if not test_patch_ok:
            return HarnessResult(
                task.instance_id,
                False,
                False,
                False,
                False,
                "; ".join(detail_parts),
                str(repo_dir),
                test_patch_ok=False,
                fail_to_pass=task.fail_to_pass,
                pass_to_pass=task.pass_to_pass,
            )

    fail_before, fail_before_log = run_pytest(repo_dir, task.fail_to_pass, test_paths, adapter=adapter)
    detail_parts.append(f"fail_before={'pass' if fail_before else 'fail'}")

    ok, msg = apply_patch(repo_dir, model_patch, "model_patch")
    detail_parts.append(f"model_patch={'ok' if ok else msg}")
    if not ok:
        return HarnessResult(
            task.instance_id,
            False,
            False,
            False,
            False,
            "; ".join(detail_parts),
            str(repo_dir),
            test_patch_ok=test_patch_ok,
            fail_before=fail_before,
            model_patch_ok=False,
            fail_to_pass=task.fail_to_pass,
            pass_to_pass=task.pass_to_pass,
        )

    fail_after, fail_after_log = run_pytest(repo_dir, task.fail_to_pass, test_paths, adapter=adapter)
    detail_parts.append(f"fail_after={'pass' if fail_after else 'fail'}")
    if not fail_after:
        detail_parts.append(fail_after_log)

    pass_ok, pass_log = run_pytest(repo_dir, task.pass_to_pass, test_paths, adapter=adapter) if task.pass_to_pass else (True, "skipped")
    detail_parts.append(f"pass_to_pass={'pass' if pass_ok else 'fail'}")
    if not pass_ok:
        detail_parts.append(pass_log)

    resolved = (not fail_before) and fail_after and pass_ok
    return HarnessResult(
        instance_id=task.instance_id,
        patch_applied=True,
        harness_resolved=resolved,
        fail_to_pass_passed=fail_after,
        pass_to_pass_passed=pass_ok,
        detail="; ".join(detail_parts),
        repo_dir=str(repo_dir),
        test_patch_ok=test_patch_ok,
        fail_before=fail_before,
        model_patch_ok=True,
        fail_after=fail_after,
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=task.pass_to_pass,
    )


def write_predictions(path: Path, instance_id: str, model_patch: str | None, model_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "model_patch": model_patch or "",
    }
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
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
from .runtime import (
    get_locks_dir,
    get_repo_cache_dir,
    get_runtime_root,
    get_worktree_root as _runtime_worktree_root,
    resolve_runtime_root,
)
from .local_harness_adapters import (
    DefaultHAdapter,
    DjangoHAdapter,
    RepoHarnessAdapter,
    RequestsHAdapter,
    SymPyHAdapter,
    apply_python_compat,
    build_pytest_node_ids,
    harness_python,
    run_pytest,
)

PAPER1_ROOT = Path(__file__).resolve().parents[2]

# Legacy repo cache locations (read-only fallback for existing clones).
_LEGACY_REPO_CACHE = PAPER1_ROOT / "data" / "repo_cache"
_LEGACY_REPO_CACHE_ALT = PAPER1_ROOT / "src" / "data" / "repo_cache"

# ── Configurable worktree root ──────────────────────────────────────────────
# --worktree-root overrides the runtime-derived worktree root.
# Prefer --runtime-root for new code; --worktree-root is a deprecated escape hatch.

_worktree_root_override: Path | None = None
_worktree_root_source = "default"


def set_worktree_root(path: Path | str | None) -> None:
    """Override worktree root (deprecated — prefer --runtime-root)."""
    global _worktree_root_override, _worktree_root_source
    if path is None:
        _worktree_root_override = None
        _worktree_root_source = "default"
        return
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    _worktree_root_override = p
    _worktree_root_source = "cli"


def get_worktree_root() -> Path:
    """Current worktree root: explicit override > runtime-derived."""
    if _worktree_root_override is not None:
        return _worktree_root_override
    return _runtime_worktree_root()


def get_worktree_root_source() -> str:
    if _worktree_root_override is not None:
        return _worktree_root_source
    return f"runtime:{resolve_runtime_root()[1]}"


# ── Repo cache (mirror clones) ──────────────────────────────────────────────

def _active_repo_cache_dir() -> Path:
    """Active repo cache: runtime root (preferred) with legacy fallback for reads."""
    return get_repo_cache_dir()


# ── Cross-process file lock for git metadata ────────────────────────────────

def _locks_dir() -> Path:
    return get_locks_dir()


@contextmanager
def _repo_git_lock(slug: str):
    """Cross-process file lock scoped to a single repo's git metadata operations.

    Uses fcntl.flock so multiple processes (and threads within them) serialize
    git worktree add/remove/prune without blocking agent execution or API calls.
    """
    lock_path = _locks_dir() / f"{slug}.lock"
    t0 = time.time()
    try:
        with open(lock_path, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            waited = time.time() - t0
            if waited > 5.0:
                print(
                    f"{tag('lock')} {slug} waited={waited:.1f}s pid={os.getpid()}",
                    flush=True,
                )
            yield
    finally:
        pass  # flock released on close

_LAST_COMPAT_FILES: tuple[str, ...] = ()
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
    primary = get_repo_cache_dir() / slug
    # Legacy fallback only when explicitly enabled via env var.
    # Default: always use runtime repo cache, even if a legacy clone exists.
    if os.environ.get("BUDGETFLOW_USE_LEGACY_REPO_CACHE") == "1":
        for legacy in (_LEGACY_REPO_CACHE / slug, _LEGACY_REPO_CACHE_ALT / slug):
            if legacy.exists():
                return legacy
    return primary


def _pip_marker_path(repo_dir: Path) -> Path:
    return repo_dir / ".budgetflow_pip_ok"


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
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        print(f"{tag('prep')} git clone {paint(task.repo, _BRIGHT_CYAN)} ...", flush=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", repo_url, str(repo_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    return repo_dir


def _timed_step(
    step_name: str, fn, *,
    warn_s: float = 120, stuck_s: float = 300,
    repo_slug: str = "", workspace_key: str = "", root: str = "",
) -> object:
    """Run *fn* and log one structured line; warn if >warn_s, flag STUCK if >stuck_s."""
    t0 = time.time()
    try:
        result = fn()
    except Exception:
        elapsed = time.time() - t0
        _emit_step_log(step_name, elapsed, repo_slug, workspace_key, root, "error")
        raise
    elapsed = time.time() - t0
    if elapsed > stuck_s:
        status = "stuck"
    elif elapsed > warn_s:
        status = "warn"
    else:
        status = "ok"
    _emit_step_log(step_name, elapsed, repo_slug, workspace_key, root, status)
    return result, elapsed


def _emit_step_log(
    step_name: str, elapsed: float,
    repo_slug: str, workspace_key: str, root: str, status: str,
) -> None:
    parts = [
        f"prep_step={step_name}",
        f"elapsed_s={elapsed:.1f}",
        f"pid={os.getpid()}",
        f"status={status}",
    ]
    if repo_slug:
        parts.append(f"repo={repo_slug}")
    if workspace_key:
        parts.append(f"key={workspace_key}")
    if root:
        parts.append(f"root={root}")
    print(f"{tag('prep_step')} {' '.join(parts)}", flush=True)


def _remove_worktree(main_repo: Path, worktree_path: Path) -> None:
    import shutil

    worktree_name = worktree_path.name
    meta_dir = main_repo / ".git" / "worktrees" / worktree_name

    def _do():
        # 1. Always unlock first — a stale lock prevents prune and re-add.
        subprocess.run(
            ["git", "worktree", "unlock", str(worktree_path)],
            cwd=main_repo,
            capture_output=True,
            text=True,
        )
        # 2. Remove git worktree registration.
        if worktree_path.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=main_repo,
                capture_output=True,
                text=True,
            )
        # 3. Nuke the git metadata dir so "missing but locked" worktrees
        #    (directory gone, .git/worktrees/<name> still present) are cleaned.
        if meta_dir.exists():
            shutil.rmtree(meta_dir, ignore_errors=True)
        # 4. Filesystem cleanup: nuke the directory regardless of git state.
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)
        # 5. Prune stale metadata.
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=main_repo,
            capture_output=True,
            text=True,
        )

    _timed_step(f"worktree_remove {worktree_name}", _do)


def _worktree_add(main_repo: Path, worktree_path: Path, commit: str) -> None:
    """``git worktree add`` with timeout + one retry for transient git issues."""
    import shutil

    worktree_name = worktree_path.name

    def _try_add() -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "worktree", "add", "--force", str(worktree_path), commit],
            cwd=main_repo,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def _do():
        try:
            result = _try_add()
        except subprocess.TimeoutExpired:
            print(
                f"{tag('prep_step')} worktree_add {worktree_name} TIMEOUT — "
                f"checking git worktree list, cleaning stale metadata, retrying",
                flush=True,
            )
            subprocess.run(
                ["git", "worktree", "list"],
                cwd=main_repo, capture_output=True, text=True,
            )
            # Clean stale metadata.
            meta_dir = main_repo / ".git" / "worktrees" / worktree_name
            subprocess.run(
                ["git", "worktree", "unlock", str(worktree_path)],
                cwd=main_repo, capture_output=True, text=True,
            )
            if meta_dir.exists():
                shutil.rmtree(meta_dir, ignore_errors=True)
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=main_repo, capture_output=True, text=True,
            )
            # Retry once.
            result = subprocess.run(
                ["git", "worktree", "add", "--force", str(worktree_path), commit],
                cwd=main_repo,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return

        if result.returncode == 0:
            return
        stderr = (result.stderr or "").strip()
        # Commit may be missing from a shallow/blobless clone even after
        # _ensure_commit_available succeeded — re-fetch deeply and retry once.
        if "invalid reference" in stderr:
            subprocess.run(
                ["git", "fetch", "origin", commit],
                cwd=main_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "worktree", "add", "--force", str(worktree_path), commit],
                cwd=main_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            return
        # "missing but locked" worktree: stale metadata from a previous crash.
        # unlock + prune + nuke metadata, then retry.
        if "missing but locked" in stderr or "locked worktree" in stderr:
            wname = worktree_path.name
            meta_dir = main_repo / ".git" / "worktrees" / wname
            subprocess.run(
                ["git", "worktree", "unlock", str(worktree_path)],
                cwd=main_repo, capture_output=True, text=True,
            )
            if meta_dir.exists():
                shutil.rmtree(meta_dir, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=main_repo, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "worktree", "add", "--force", str(worktree_path), commit],
                cwd=main_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            return
        result.check_returncode()

    _timed_step(f"worktree_add {worktree_name}", _do)


def _prepare_worktree(task: LiteTaskRecord, workspace_key: str) -> Path:
    slug = repo_slug(task.repo)
    main_repo = _ensure_main_repo(task)
    wt_root = get_worktree_root()
    worktree_path = wt_root / slug / workspace_key
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    with _repo_git_lock(slug):
        _remove_worktree(main_repo, worktree_path)
        _ensure_commit_available(main_repo, task.base_commit)
        inst = paint(task.instance_id, _BOLD, _BRIGHT_CYAN)
        root_tag = get_worktree_root_source()
        print(
            f"{tag('prep')} worktree {inst} key={workspace_key} "
            f"root={root_tag} @ {task.base_commit[:8]} ...",
            flush=True,
        )
        _worktree_add(main_repo, worktree_path, task.base_commit)
        _timed_step(
            f"git_reset {workspace_key}", lambda: subprocess.run(
                ["git", "reset", "--hard", task.base_commit],
                cwd=worktree_path, check=True, capture_output=True, text=True,
            ),
            repo_slug=slug, workspace_key=workspace_key, root=root_tag,
        )
        _timed_step(
            f"git_clean {workspace_key}", lambda: subprocess.run(
                ["git", "clean", "-fdx"], cwd=worktree_path,
                check=True, capture_output=True, text=True,
            ),
            repo_slug=slug, workspace_key=workspace_key, root=root_tag,
        )
    return worktree_path


def _finalize_repo_workspace(repo_dir: Path, task: LiteTaskRecord) -> Path:
    global _LAST_COMPAT_FILES

    def _do_compat():
        return apply_python_compat(repo_dir)

    _LAST_COMPAT_FILES, _elapsed = _timed_step(f"compat_patch {task.instance_id}", _do_compat)
    n = len(_LAST_COMPAT_FILES)
    print(
        f"{tag('prep')} py3.11 collections compat {paint(str(n), _BRIGHT_GREEN)} files",
        flush=True,
    )

    marker = _pip_marker_path(repo_dir)
    if marker.exists() and marker.read_text().strip() == task.base_commit:
        print(f"{tag('prep')} pip skip {dim('(cached)')}", flush=True)
        return repo_dir

    install_result: subprocess.CompletedProcess | None = None

    def _pip():
        nonlocal install_result
        install_result = _pip_install_editable(repo_dir, task=task)

    _timed_step(f"pip_install {task.instance_id}", _pip)

    if install_result is not None and install_result.returncode == 0:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(task.base_commit)
        print(f"{tag('prep')} pip {paint('done', _BRIGHT_GREEN)}", flush=True)
    else:
        rc = install_result.returncode if install_result else -1
        print(f"{tag('prep')} pip failed (rc={rc}), continuing anyway", flush=True)
    return repo_dir


def clone_or_checkout(task: LiteTaskRecord, *, workspace_key: str | None = None) -> Path:
    if workspace_key:
        repo_dir = _prepare_worktree(task, workspace_key)
        return _finalize_repo_workspace(repo_dir, task)

    slug = repo_slug(task.repo)
    with _repo_git_lock(slug):
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

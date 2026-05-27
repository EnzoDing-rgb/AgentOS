from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .lite_tasks import LiteTaskRecord

REPO_ROOT = Path("/Lishun/_archive/.local_env_bak/research/AgentOS/paper1")
CACHE_DIR = REPO_ROOT / "data" / "repo_cache"


@dataclass(frozen=True)
class HarnessResult:
    instance_id: str
    patch_applied: bool
    harness_resolved: bool
    fail_to_pass_passed: bool
    pass_to_pass_passed: bool
    detail: str
    repo_dir: str


def repo_slug(repo: str) -> str:
    return repo.replace("/", "__")


def repo_dir_for(task: LiteTaskRecord) -> Path:
    return CACHE_DIR / repo_slug(task.repo)


def _pip_marker_path(task: LiteTaskRecord) -> Path:
    return CACHE_DIR / f"{repo_slug(task.repo)}.pip_ok"


def clone_or_checkout(task: LiteTaskRecord) -> Path:
    repo_dir = repo_dir_for(task)
    repo_url = f"https://github.com/{task.repo}.git"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        print(f"[prep] git clone {task.repo} ...", flush=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", repo_url, str(repo_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    print(f"[prep] checkout {task.instance_id} @ {task.base_commit[:8]} ...", flush=True)
    subprocess.run(["git", "fetch", "origin", task.base_commit], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "--force", task.base_commit], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "clean", "-fdx"], cwd=repo_dir, check=True, capture_output=True, text=True)

    marker = _pip_marker_path(task)
    if marker.exists() and marker.read_text().strip() == task.base_commit:
        print(f"[prep] pip skip (cached for {task.base_commit[:8]})", flush=True)
        return repo_dir

    print(f"[prep] pip install -e . (first time at this commit, sympy can take several min) ...", flush=True)
    install = subprocess.run(
        ["pip", "install", "-e", ".", "-q"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if install.returncode != 0 and "sympy" not in task.repo:
        install.check_returncode()
    if install.returncode == 0:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(task.base_commit)
        print("[prep] pip done", flush=True)
    else:
        print("[prep] pip failed (non-fatal for sympy)", flush=True)
    return repo_dir


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


def run_pytest(repo_dir: Path, test_names: tuple[str, ...], test_paths: list[str]) -> tuple[bool, str]:
    if not test_names:
        return False, "no test names"
    node_ids: list[str] = []
    missing: list[str] = []
    for path in test_paths:
        full = repo_dir / path
        text = full.read_text() if full.is_file() else ""
        for name in test_names:
            if f"def {name}(" in text:
                node_ids.append(f"{path}::{name}")
            else:
                missing.append(f"{path}::{name}")
    if not node_ids:
        detail = ", ".join(missing[:6]) if missing else "none"
        return False, f"no pytest node ids: {detail}"
    cmd = ["python", "-m", "pytest", "-x", *node_ids]
    result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
    output = (result.stdout + "\n" + result.stderr).strip()
    tail = output[-2000:] if len(output) > 2000 else output
    return result.returncode == 0, tail


def evaluate_local_harness(task: LiteTaskRecord, model_patch: str | None) -> HarnessResult:
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
        )

    try:
        repo_dir = clone_or_checkout(task)
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

    test_paths = test_paths_for(task)
    if task.test_patch:
        ok, msg = apply_patch(repo_dir, task.test_patch, "test_patch")
        detail_parts.append(f"test_patch={'ok' if ok else msg}")
        if not ok:
            return HarnessResult(task.instance_id, False, False, False, False, "; ".join(detail_parts), str(repo_dir))

    fail_before, fail_before_log = run_pytest(repo_dir, task.fail_to_pass, test_paths)
    detail_parts.append(f"fail_before={'pass' if fail_before else 'fail'}")

    ok, msg = apply_patch(repo_dir, model_patch, "model_patch")
    detail_parts.append(f"model_patch={'ok' if ok else msg}")
    if not ok:
        return HarnessResult(task.instance_id, False, False, False, False, "; ".join(detail_parts), str(repo_dir))

    fail_after, fail_after_log = run_pytest(repo_dir, task.fail_to_pass, test_paths)
    detail_parts.append(f"fail_after={'pass' if fail_after else 'fail'}")
    if not fail_after:
        detail_parts.append(fail_after_log)

    pass_subset = task.pass_to_pass[:5]
    pass_ok, pass_log = run_pytest(repo_dir, pass_subset, test_paths) if pass_subset else (True, "skipped")
    detail_parts.append(f"pass_to_pass={'pass' if pass_ok else 'fail'}")
    if not pass_ok:
        detail_parts.append(pass_log)

    resolved = fail_after and pass_ok
    return HarnessResult(
        instance_id=task.instance_id,
        patch_applied=True,
        harness_resolved=resolved,
        fail_to_pass_passed=fail_after,
        pass_to_pass_passed=pass_ok,
        detail="; ".join(detail_parts),
        repo_dir=str(repo_dir),
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

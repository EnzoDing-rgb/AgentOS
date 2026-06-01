from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import subprocess

from budgetflow.run_trace import (  # noqa: E402
    RunTraceLogger,
    SUBMIT_MARKER,
    extract_worktree_patch,
    patch_local_swebench_config,
)


def _logger(tmp_path: Path) -> RunTraceLogger:
    repo = tmp_path / "repo"
    repo.mkdir()
    trace = tmp_path / "trace"
    return RunTraceLogger(instance_id="test", repo_dir=repo, trace_dir=trace)


def test_git_diff_not_submitted(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    logger._detect_submit_attempt(["git diff HEAD~1"])
    assert logger._submitted is False
    assert logger._attempted_submit is False


def test_submit_marker_detected_as_attempt_only(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    logger._detect_submit_attempt([f"echo {SUBMIT_MARKER}"])
    assert logger._attempted_submit is True
    assert logger._submitted is False


def test_patch_txt_phase_not_submit(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    phase = logger._classify_phase(
        commands=["git diff > patch.txt"],
        changed=[],
        gold_edited=[],
    )
    assert phase == "patch_prep"
    logger._detect_submit_attempt(["git diff > patch.txt"])
    assert logger._attempted_submit is False
    assert logger._submitted is False


def test_finalize_agent_sets_real_submission(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    logger.finalize_agent(submitted=True, patch_extracted=True)
    assert logger._attempted_submit is True
    assert logger._submitted is True


def test_finalize_agent_ignores_patch_only(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    logger.finalize_agent(submitted=False, patch_extracted=True)
    assert logger._submitted is False


def test_extract_worktree_patch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    target = repo / "sympy/core.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n")
    subprocess.run(["git", "add", "sympy/core.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    target.write_text("x = 2\n")
    patch = extract_worktree_patch(repo, prefer_paths=("sympy/core.py",))
    assert patch is not None
    assert "sympy/core.py" in patch
    assert extract_worktree_patch(repo, prefer_paths=("other.py",)) is None


def test_local_config_adds_python_shim_to_path(tmp_path: Path) -> None:
    config = {"environment": {"env": {"PAGER": "cat"}}}
    patched = patch_local_swebench_config(config, tmp_path)

    env = patched["environment"]["env"]

    assert env["PAGER"] == "cat"
    assert Path(env["PATH"].split(":")[0], "python").exists()

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.run_trace import RunTraceLogger, SUBMIT_MARKER  # noqa: E402


def _logger(tmp_path: Path) -> RunTraceLogger:
    repo = tmp_path / "repo"
    repo.mkdir()
    trace = tmp_path / "trace"
    return RunTraceLogger(instance_id="test", repo_dir=repo, trace_dir=trace)


def test_git_diff_not_submitted(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    logger._detect_submitted(["git diff HEAD~1"])
    assert logger._submitted is False


def test_submit_marker_detected(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    logger._detect_submitted([f"echo {SUBMIT_MARKER}"])
    assert logger._submitted is True


def test_patch_txt_phase_not_submit(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    phase = logger._classify_phase(
        commands=["git diff > patch.txt"],
        changed=[],
        gold_edited=[],
    )
    assert phase == "patch_prep"
    logger._detect_submitted(["git diff > patch.txt"])
    assert logger._submitted is False


def test_finalize_agent_ignores_patch_only(tmp_path: Path) -> None:
    logger = _logger(tmp_path)
    logger.finalize_agent(submitted=False, patch_extracted=True)
    assert logger._submitted is False

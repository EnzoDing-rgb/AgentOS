"""Tests for run_autoresearch CLI — create, run, status, list, worker bridge."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.run_autoresearch import main  # noqa: E402


@pytest.fixture
def paper1_tmp(tmp_path):
    """Create a minimal paper1 tree for CLI testing."""
    p1 = tmp_path / "paper1"
    p1.mkdir()
    (p1 / "src").mkdir()
    (p1 / "tests").mkdir()
    (p1 / "docs").mkdir()
    return p1


@pytest.fixture
def prompt_file(tmp_path):
    """A sample prompt file."""
    pf = tmp_path / "test_prompt.md"
    pf.write_text("# Fix the sympy print bug\n\nApply the patch and verify with pytest.\n")
    return pf


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(paper1_tmp, *args) -> int:
    return main(["--paper1-root", str(paper1_tmp), *args])


# ── Create ────────────────────────────────────────────────────────────────────

class TestCreate:
    def test_create_workflow(self, paper1_tmp, prompt_file):
        rc = _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        assert rc == 0
        wdir = paper1_tmp / ".autoresearch" / "workflows" / "042-fix-bug"
        assert wdir.is_dir()
        assert (wdir / "state.json").is_file()
        assert (wdir / "worker_prompt.md").is_file()
        assert "Fix the sympy print bug" in (wdir / "worker_prompt.md").read_text()

    def test_create_creates_placeholder_files(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        wdir = paper1_tmp / ".autoresearch" / "workflows" / "042-fix-bug"
        assert (wdir / "codex_review.md").is_file()
        assert (wdir / "final.md").is_file()
        assert (wdir / "attempts" / "001" / "worker_output.md").is_file()

    def test_create_sets_status_pending(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("042-fix-bug")
        assert state.status == "pending"


# ── Run dry-run ───────────────────────────────────────────────────────────────

class TestRunDryRun:
    def test_dry_run_succeeds(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--dry-run")
        assert rc == 0

    def test_dry_run_writes_state(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--dry-run")
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("042-fix-bug")
        assert state.dry_run is True
        assert state.status == "running"

    def test_dry_run_creates_attempt_dir(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--dry-run")
        adir = paper1_tmp / ".autoresearch" / "workflows" / "042-fix-bug" / "attempts" / "001"
        assert adir.is_dir()


# ── Run manual ────────────────────────────────────────────────────────────────

class TestRunManual:
    def test_manual_succeeds(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--manual")
        assert rc == 0

    def test_manual_does_not_call_worker(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        # Default (no flags) is also manual mode.
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug")
        assert rc == 0

    def test_default_is_manual(self, paper1_tmp, prompt_file):
        """When no --dry-run, --manual, or --worker-cmd, default to manual mode."""
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug")
        assert rc == 0
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("042-fix-bug")
        assert state.manual_mode is True


# ── Worker bridge ─────────────────────────────────────────────────────────────

class TestWorkerBridge:
    def test_worker_cmd_runs_and_writes_output(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(
            paper1_tmp, "run", "--issue-id", "042-fix-bug",
            "--worker-cmd", "cat {prompt} > /dev/null; echo 'worker done' > {output}",
        )
        assert rc == 0
        output = paper1_tmp / ".autoresearch" / "workflows" / "042-fix-bug" / "attempts" / "001" / "worker_output.md"
        assert output.is_file()
        assert "worker done" in output.read_text()

    def test_worker_cmd_nonzero_exit_fails_workflow(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(
            paper1_tmp, "run", "--issue-id", "042-fix-bug",
            "--worker-cmd", "cat {prompt} > /dev/null; echo fail > {output}; exit 1",
        )
        assert rc == 1  # CLI returns 1 on worker failure
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("042-fix-bug")
        assert state.status == "failed"


# ── Worker-cmd validation ────────────────────────────────────────────────────

class TestWorkerCmdValidation:
    def test_missing_prompt_rejected(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "test", "--prompt-file", str(prompt_file))
        with pytest.raises(SystemExit) as exc:
            _run(paper1_tmp, "run", "--issue-id", "test", "--worker-cmd", "cat {output}")
        assert exc.value.code == 1

    def test_missing_output_rejected(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "test", "--prompt-file", str(prompt_file))
        with pytest.raises(SystemExit) as exc:
            _run(paper1_tmp, "run", "--issue-id", "test", "--worker-cmd", "cat {prompt}")
        assert exc.value.code == 1

    def test_both_missing_rejected(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "test", "--prompt-file", str(prompt_file))
        with pytest.raises(SystemExit) as exc:
            _run(paper1_tmp, "run", "--issue-id", "test", "--worker-cmd", "echo hello")
        assert exc.value.code == 1

    def test_both_present_accepted(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "test", "--prompt-file", str(prompt_file))
        rc = _run(
            paper1_tmp, "run", "--issue-id", "test",
            "--worker-cmd", "cat {prompt} > {output}",
        )
        assert rc == 0


# ── List filters ─────────────────────────────────────────────────────────────

class TestListFilters:
    def test_list_filter_by_status(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "task-a", "--dry-run")
        _run(paper1_tmp, "create", "--issue-id", "task-b", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "list", "--status", "running")
        assert rc == 0

    def test_list_filter_paused_only(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "task-a", "--paid-3x10", "3", "10")
        _run(paper1_tmp, "create", "--issue-id", "task-b", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "list", "--paused-only")
        assert rc == 0

    def test_list_filter_none_found(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "list", "--status", "complete")
        assert rc == 0


# ── Next command ──────────────────────────────────────────────────────────────

class TestNext:
    def test_next_pending(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "next", "--issue-id", "task")
        assert rc == 0

    def test_next_running(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "task", "--dry-run")
        rc = _run(paper1_tmp, "next", "--issue-id", "task")
        assert rc == 0

    def test_next_failed_retry_allowed(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "task", "--worker-cmd", "cat {prompt} > /dev/null; echo fail > {output}; exit 1")
        rc = _run(paper1_tmp, "next", "--issue-id", "task")
        assert rc == 0

    def test_next_paused(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "task", "--paid-3x10", "3", "10")
        rc = _run(paper1_tmp, "next", "--issue-id", "task")
        assert rc == 0

    def test_next_complete(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "task", "--dry-run")
        _run(paper1_tmp, "mark-complete", "--issue-id", "task")
        rc = _run(paper1_tmp, "next", "--issue-id", "task")
        assert rc == 0

    def test_next_nonexistent(self, paper1_tmp):
        rc = _run(paper1_tmp, "next", "--issue-id", "nonexistent")
        assert rc == 1


# ── Status ────────────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_shows_workflow(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "status", "--issue-id", "042-fix-bug")
        assert rc == 0

    def test_status_nonexistent(self, paper1_tmp):
        rc = _run(paper1_tmp, "status", "--issue-id", "nonexistent")
        assert rc == 1


# ── List ──────────────────────────────────────────────────────────────────────

class TestList:
    def test_list_empty(self, paper1_tmp):
        rc = _run(paper1_tmp, "list")
        assert rc == 0

    def test_list_shows_workflows(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "create", "--issue-id", "043-add-test", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "list")
        assert rc == 0

    def test_list_shows_mixed_statuses(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "task-a", "--dry-run")
        _run(paper1_tmp, "create", "--issue-id", "task-b", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "list")
        assert rc == 0


# ── Mark complete / failed ────────────────────────────────────────────────────

class TestMarkComplete:
    def test_mark_complete(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--dry-run")
        rc = _run(paper1_tmp, "mark-complete", "--issue-id", "042-fix-bug")
        assert rc == 0
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("042-fix-bug")
        assert state.status == "complete"

    def test_mark_complete_nonexistent(self, paper1_tmp):
        rc = _run(paper1_tmp, "mark-complete", "--issue-id", "nonexistent")
        assert rc == 1

    def test_mark_complete_writes_final(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--dry-run")
        _run(paper1_tmp, "mark-complete", "--issue-id", "042-fix-bug")
        final = paper1_tmp / ".autoresearch" / "workflows" / "042-fix-bug" / "final.md"
        assert "complete" in final.read_text()


class TestMarkFailed:
    def test_mark_failed(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--dry-run")
        rc = _run(paper1_tmp, "mark-failed", "--issue-id", "042-fix-bug", "--reason", "budget_exhausted")
        assert rc == 0
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("042-fix-bug")
        assert state.status == "failed"

    def test_mark_failed_nonexistent(self, paper1_tmp):
        rc = _run(paper1_tmp, "mark-failed", "--issue-id", "nonexistent")
        assert rc == 1

    def test_mark_failed_no_reason(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--dry-run")
        rc = _run(paper1_tmp, "mark-failed", "--issue-id", "042-fix-bug")
        assert rc == 0


# ── Pause conditions via CLI ──────────────────────────────────────────────────

class TestPauseViaCLI:
    def test_paid_3x10_pauses(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--paid-3x10", "3", "10")
        assert rc == 2  # paused
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("042-fix-bug")
        assert state.status == "paused"
        assert state.paused_reason == "paid_3x10_or_larger"

    def test_paid_3x7_does_not_pause(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--paid-3x10", "3", "7")
        assert rc == 0

    def test_northstar_change_pauses(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--northstar-change")
        assert rc == 2

    def test_large_refactor_pauses(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "042-fix-bug", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "run", "--issue-id", "042-fix-bug", "--large-refactor")
        assert rc == 2


# ── End-to-end workflow ───────────────────────────────────────────────────────

class TestEndToEnd:
    def test_full_lifecycle(self, paper1_tmp, prompt_file):
        """create → run (dry-run) → mark-complete."""
        assert _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file)) == 0
        assert _run(paper1_tmp, "run", "--issue-id", "task", "--dry-run") == 0
        assert _run(paper1_tmp, "mark-complete", "--issue-id", "task") == 0

        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("task")
        assert state.status == "complete"

    def test_failure_retry_flow(self, paper1_tmp, prompt_file):
        """create → run (worker fails) → retry → mark-failed."""
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        # First run: worker fails.
        _run(paper1_tmp, "run", "--issue-id", "task", "--worker-cmd", "cat {prompt} > /dev/null; echo fail > {output}; exit 1")
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("task")
        assert state.status == "failed"
        assert state.attempt == 1
        # Second run: retry succeeds.
        _run(paper1_tmp, "run", "--issue-id", "task", "--worker-cmd", "cat {prompt} > /dev/null; echo ok > {output}")
        state = c.load_state("task")
        assert state.status == "complete"
        assert state.attempt == 2

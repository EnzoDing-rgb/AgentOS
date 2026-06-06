"""Tests for run_autoresearch CLI — create, run, status, list, worker bridge."""

from __future__ import annotations

import sys
import subprocess
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


# ── Review CLI ─────────────────────────────────────────────────────────────────

class TestReviewCLI:
    def test_review_nonexistent_issue(self, paper1_tmp):
        rc = _run(paper1_tmp, "review", "--issue-id", "nonexistent")
        assert rc == 1

    def test_review_existing_issue(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        rc = _run(paper1_tmp, "review", "--issue-id", "task")
        # No metadata means FAIL, but command succeeds (rc=0 for WARN, rc=1 for FAIL)
        assert rc == 1  # No metadata → FAIL → exit 1

    def test_goal_review_nonexistent(self, paper1_tmp):
        rc = _run(paper1_tmp, "goal-review", "--goal-id", "nonexistent")
        assert rc == 1

    def test_goal_review_existing(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Review Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")
        rc = _run(paper1_tmp, "goal-review", "--goal-id", "g1")
        # No metadata → FAIL for each issue, overall FAIL → exit 1
        assert rc == 1
        # Verify codex_review.md was written.
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        review_path = c.workflow_dir("task-a") / "codex_review.md"
        assert review_path.is_file()
        content = review_path.read_text()
        assert "VERDICT:" in content
        assert "AUTORESEARCH_RESULT:" in content

    def test_goal_review_exits_2_on_warn(self, paper1_tmp, prompt_file):
        """goal-review returns 2 when review produces WARN."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Warn Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")
        # Create metadata with marker_appended=True (produces WARN).
        import json as _json
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        adir = c.attempt_dir("task-a", 1)
        adir.mkdir(parents=True, exist_ok=True)
        meta = {
            "model": "test", "input_tokens": 50, "output_tokens": 20,
            "status_code": 200, "marker_present_in_model_output": True,
            "marker_appended_by_wrapper": True, "error": None,
        }
        (adir / "worker_metadata.json").write_text(_json.dumps(meta))
        (adir / "worker_output.md").write_text("""<!-- AutoResearch API Worker — factual metadata
  model: test
  input_tokens: 50
  output_tokens: 20
  metadata: worker_metadata.json
-->
# Report
AUTORESEARCH_REAL_API_SMOKE:PASS
""")
        state = c.load_state("task-a")
        state.attempt = 1
        c._write_state(state)

        rc = _run(paper1_tmp, "goal-review", "--goal-id", "g1")
        assert rc == 2  # WARN → exit 2

    def test_mark_complete_rejects_fail_review(self, paper1_tmp, prompt_file):
        """mark-complete exits 1 when codex_review.md has FAIL verdict."""
        _run(paper1_tmp, "create", "--issue-id", "task", "--prompt-file", str(prompt_file))
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        review_path = c.workflow_dir("task") / "codex_review.md"
        review_path.write_text("VERDICT: FAIL\nSCORE: 0/100\nAUTORESEARCH_RESULT:FAIL\n")
        rc = _run(paper1_tmp, "mark-complete", "--issue-id", "task")
        assert rc == 1


# ── Goal-loop tests ────────────────────────────────────────────────────────────

FAKE_WORKER = ROOT / "scripts" / "autoresearch_fake_worker.py"
FAKE_WORKER_CMD = f"cat {{prompt}} > /dev/null; python3 {FAKE_WORKER} {{prompt}} {{output}}"


class TestGoalLoop:
    def test_loop_all_pass_completes(self, paper1_tmp, prompt_file):
        """goal-loop with fake workers should PASS all issues and exit 0."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Loop Test")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "create", "--issue-id", "task-b", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-b")

        rc = _run(paper1_tmp, "goal-loop", "--goal-id", "g1",
                  "--worker-cmd", FAKE_WORKER_CMD, "--max-steps", "5")
        assert rc == 0

        # Verify goal is complete.
        from budgetflow.autoresearch_goal import GoalManager
        gm = GoalManager(paper1_root=paper1_tmp)
        goal = gm.load_goal("g1")
        assert goal.status == "complete"

    def test_loop_warn_exits_2(self, paper1_tmp, prompt_file, tmp_path):
        """goal-loop with WARN review exits 2 and writes owner_decision.md.

        Uses a custom worker that writes real-API output with
        marker_appended_by_wrapper=true, so the review gate produces WARN
        (not auto-detected as fake worker, and not clean enough for PASS).
        """
        # Write a helper that produces WARN-triggering output.
        # Uses \n (literal in the raw string) which the helper's Python
        # interpreter converts to real newlines in the output file.
        helper = tmp_path / "warn_worker.py"
        helper.write_text(r"""import json, sys
from pathlib import Path

output_path = Path(sys.argv[2])
output_path.parent.mkdir(parents=True, exist_ok=True)

output = (
    '<!-- AutoResearch API Worker -- factual metadata\n'
    '  model: test\n'
    '  input_tokens: 50\n'
    '  output_tokens: 20\n'
    '  metadata: worker_metadata.json\n'
    '-->\n'
    '# Report\n'
    '\n'
    'AUTORESEARCH_REAL_API_SMOKE:PASS\n'
)
output_path.write_text(output)

meta = {
    "model": "test", "input_tokens": 50, "output_tokens": 20,
    "status_code": 200, "marker_present_in_model_output": True,
    "marker_appended_by_wrapper": True, "error": None,
}
meta_path = output_path.parent / "worker_metadata.json"
meta_path.write_text(json.dumps(meta))
print(f"[warn_worker] wrote output and metadata to {output_path.parent}")
""")

        WARN_CMD = f"python3 {helper} {{prompt}} {{output}}"

        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Warn Loop")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        rc = _run(paper1_tmp, "goal-loop", "--goal-id", "g1",
                  "--worker-cmd", WARN_CMD, "--max-steps", "5")
        assert rc == 2  # WARN → exit 2

        # Verify owner_decision.md was written.
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        dp = c.workflow_dir("task-a") / "owner_decision.md"
        assert dp.is_file()
        content = dp.read_text()
        assert "Owner Decision Required" in content
        assert "Why Paused" in content

    def test_loop_respects_max_steps(self, paper1_tmp, prompt_file):
        """goal-loop with max-steps=1 processes at most 1 issue."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Max Step Test")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "create", "--issue-id", "task-b", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-b")

        rc = _run(paper1_tmp, "goal-loop", "--goal-id", "g1",
                  "--worker-cmd", FAKE_WORKER_CMD, "--max-steps", "1")
        # Should not complete (only 1 step for 2 issues).
        assert rc == 1  # max steps exceeded

    def test_loop_worker_cmd_validation(self, paper1_tmp):
        """goal-loop rejects worker-cmd without {prompt} and {output}."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Bad Worker")
        with pytest.raises(SystemExit) as exc_info:
            _run(paper1_tmp, "goal-loop", "--goal-id", "g1",
                  "--worker-cmd", "echo bad > /tmp/out", "--max-steps", "2")
        assert exc_info.value.code == 1

    def test_loop_nonexistent_goal(self, paper1_tmp):
        """goal-loop returns 1 for nonexistent goal."""
        rc = _run(paper1_tmp, "goal-loop", "--goal-id", "no-goal",
                  "--worker-cmd", FAKE_WORKER_CMD, "--max-steps", "2")
        assert rc == 1

    def test_owner_decision_on_paid_pause(self, paper1_tmp, prompt_file):
        """goal-loop writes owner_decision.md when paid_3x10 triggers pause."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Paid Loop")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        rc = _run(paper1_tmp, "goal-loop", "--goal-id", "g1",
                  "--worker-cmd", FAKE_WORKER_CMD, "--max-steps", "3",
                  "--paid-3x10", "3", "10")
        assert rc == 2  # Paused

        # owner_decision should be written at goal level.
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        dp = paper1_tmp / ".autoresearch" / "goals" / "owner_decision.md"
        assert dp.is_file()
        assert "Owner Decision Required" in dp.read_text()


class TestSafeCommitPush:
    def _git(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)

    def _init_repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        self._git(repo, "init")
        self._git(repo, "config", "user.email", "test@example.com")
        self._git(repo, "config", "user.name", "AutoResearch Test")
        (repo / "paper1").mkdir()
        return repo

    def test_safe_commit_push_blocks_secret_after_staging(self, tmp_path):
        """Secret scan must run after _safe_commit_push stages allowed paths."""
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        from budgetflow.run_autoresearch import _safe_commit_push

        repo = self._init_repo(tmp_path)
        scripts = repo / "paper1" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "leak.py").write_text("ANTHROPIC_API_KEY=sk-this-is-a-very-long-secret-key\n")

        coordinator = AutoResearchCoordinator(paper1_root=repo / "paper1", git_root=repo)
        rc, msg = _safe_commit_push(coordinator, "g1", push=False)

        assert rc == 1
        assert "Secret scan found" in msg
        assert self._git(repo, "rev-list", "--count", "HEAD").returncode != 0

    def test_safe_commit_push_commits_allowed_clean_files(self, tmp_path):
        from budgetflow.autoresearch_coordinator import AutoResearchCoordinator
        from budgetflow.run_autoresearch import _safe_commit_push

        repo = self._init_repo(tmp_path)
        reports = repo / "paper1" / "docs" / "reports"
        reports.mkdir(parents=True)
        (reports / "999.md").write_text("# Clean report\n")

        coordinator = AutoResearchCoordinator(paper1_root=repo / "paper1", git_root=repo)
        rc, msg = _safe_commit_push(coordinator, "g1", push=False)

        assert rc == 0
        assert "committed" in msg
        assert self._git(repo, "rev-list", "--count", "HEAD").stdout.strip() == "1"

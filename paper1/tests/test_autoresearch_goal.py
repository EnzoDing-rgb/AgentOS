"""Tests for Goal-level coordinator — create, add-issue, status, run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.run_autoresearch import main  # noqa: E402
from budgetflow.autoresearch_goal import Goal, GoalManager  # noqa: E402
from budgetflow.autoresearch_coordinator import AutoResearchCoordinator  # noqa: E402


@pytest.fixture
def paper1_tmp(tmp_path):
    p1 = tmp_path / "paper1"
    p1.mkdir()
    (p1 / "src").mkdir()
    (p1 / "tests").mkdir()
    (p1 / "docs").mkdir()
    return p1


@pytest.fixture
def prompt_file(tmp_path):
    pf = tmp_path / "prompt.md"
    pf.write_text("# Test Issue\n\nRun a simple smoke task.\n")
    return pf


@pytest.fixture
def gm(paper1_tmp):
    c = AutoResearchCoordinator(paper1_root=paper1_tmp)
    return GoalManager(paper1_root=paper1_tmp, coordinator=c)


def _run(paper1_tmp, *args) -> int:
    return main(["--paper1-root", str(paper1_tmp), *args])


# ── Goal CRUD ────────────────────────────────────────────────────────────────

class TestGoalCreate:
    def test_create_writes_goal_json(self, gm):
        goal = gm.create_goal("test-goal", "Test Goal", budget_cap_usd=0.10)
        assert goal.goal_id == "test-goal"
        assert goal.title == "Test Goal"
        assert goal.status == "pending"
        assert goal.real_api_budget_cap_usd == 0.10
        gp = gm._goal_path("test-goal")
        assert gp.is_file()
        d = json.loads(gp.read_text())
        assert d["goal_id"] == "test-goal"

    def test_create_via_cli(self, paper1_tmp):
        rc = _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "My Goal", "--budget-cap-usd", "0.20")
        assert rc == 0
        gp = paper1_tmp / ".autoresearch" / "goals" / "g1.json"
        assert gp.is_file()

    def test_create_sets_timestamps(self, gm):
        goal = gm.create_goal("ts-goal", "Timestamps")
        assert goal.created_at != ""
        assert "T" in goal.created_at

    def test_load_roundtrip(self, gm):
        gm.create_goal("rt", "Roundtrip", budget_cap_usd=0.30, max_retries=3)
        loaded = gm.load_goal("rt")
        assert loaded is not None
        assert loaded.goal_id == "rt"
        assert loaded.max_retries_per_issue == 3


class TestGoalAddIssue:
    def test_add_issue_updates_ids(self, gm):
        gm.create_goal("g1", "Goal")
        goal = gm.add_issue("g1", "issue-a")
        assert goal is not None
        assert "issue-a" in goal.issue_ids

    def test_add_duplicate_issue_noop(self, gm):
        gm.create_goal("g1", "Goal")
        gm.add_issue("g1", "issue-a")
        goal = gm.add_issue("g1", "issue-a")
        assert goal.issue_ids.count("issue-a") == 1

    def test_add_issue_via_cli(self, paper1_tmp):
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Goal")
        rc = _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-1")
        assert rc == 0
        gm2 = GoalManager(paper1_root=paper1_tmp)
        goal = gm2.load_goal("g1")
        assert "task-1" in goal.issue_ids

    def test_add_issue_nonexistent_goal(self, gm):
        goal = gm.add_issue("nonexistent", "issue-a")
        assert goal is None

    def test_add_issue_nonexistent_goal_cli(self, paper1_tmp):
        rc = _run(paper1_tmp, "goal-add-issue", "--goal-id", "no", "--issue-id", "x")
        assert rc == 1


class TestGoalStatus:
    def test_status_shows_issues(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")
        rc = _run(paper1_tmp, "goal-status", "--goal-id", "g1")
        assert rc == 0

    def test_status_nonexistent(self, paper1_tmp):
        rc = _run(paper1_tmp, "goal-status", "--goal-id", "nonexistent")
        assert rc == 1


# ── Goal Run ─────────────────────────────────────────────────────────────────

class TestGoalRun:
    def test_run_dry_processes_first_issue(self, paper1_tmp, prompt_file):
        """goal-run --dry-run should process the first pending issue."""
        # Create goal + 2 issues.
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "create", "--issue-id", "task-b", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-b")

        rc = _run(paper1_tmp, "goal-run", "--goal-id", "g1", "--dry-run")
        assert rc == 0

        # task-a should now be running (not pending).
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("task-a")
        assert state.status == "running"
        # task-b should still be pending.
        state_b = c.load_state("task-b")
        assert state_b.status == "pending"

    def test_run_pauses_on_paid_3x10(self, paper1_tmp, prompt_file):
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        rc = _run(paper1_tmp, "goal-run", "--goal-id", "g1", "--paid-3x10", "3", "10")
        assert rc == 2  # paused

    def test_run_completes_two_issues_with_fake_worker(self, paper1_tmp, prompt_file):
        """Full two-issue goal run with fake worker (no API)."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Two-Issue Smoke")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "create", "--issue-id", "task-b", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-b")

        # Run task-a with fake worker (echo to output).
        rc1 = _run(paper1_tmp, "goal-run", "--goal-id", "g1",
                   "--worker-cmd", "cat {prompt} > /dev/null; echo 'done task-a\nAUTORESEARCH_REAL_API_SMOKE:PASS' > {output}")
        assert rc1 == 0

        # Manually mark task-a complete (since worker succeeded).
        _run(paper1_tmp, "mark-complete", "--issue-id", "task-a")

        # Run task-b.
        rc2 = _run(paper1_tmp, "goal-run", "--goal-id", "g1",
                   "--worker-cmd", "cat {prompt} > /dev/null; echo 'done task-b\nAUTORESEARCH_REAL_API_SMOKE:PASS' > {output}")
        assert rc2 == 0

        # Manually mark task-b complete.
        _run(paper1_tmp, "mark-complete", "--issue-id", "task-b")

        # Run again — should detect all complete.
        rc3 = _run(paper1_tmp, "goal-run", "--goal-id", "g1", "--dry-run")
        assert rc3 == 0

        gm = GoalManager(paper1_root=paper1_tmp)
        goal = gm.load_goal("g1")
        assert goal.status in ("running", "complete")

    def test_run_no_issues(self, paper1_tmp):
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Empty Goal")
        rc = _run(paper1_tmp, "goal-run", "--goal-id", "g1", "--dry-run")
        assert rc == 0

    def test_run_nonexistent_goal(self, paper1_tmp):
        rc = _run(paper1_tmp, "goal-run", "--goal-id", "nonexistent")
        assert rc == 1

    def test_run_retry_failed_issue(self, paper1_tmp, prompt_file):
        """Failed issue within retry limit should be retried."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Retry Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        # First run: worker fails.
        rc1 = _run(paper1_tmp, "goal-run", "--goal-id", "g1",
                   "--worker-cmd", "cat {prompt} > /dev/null; echo fail > {output}; exit 1")
        assert rc1 == 0  # goal still running (issue failed, retry available)

        # Second run: should retry same issue.
        rc2 = _run(paper1_tmp, "goal-run", "--goal-id", "g1",
                   "--worker-cmd", "cat {prompt} > /dev/null; echo 'retry success\nAUTORESEARCH_REAL_API_SMOKE:PASS' > {output}")
        assert rc2 == 0

        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("task-a")
        assert state.attempt == 2


# ── Goal summary ─────────────────────────────────────────────────────────────

class TestGoalSummary:
    def test_write_summary(self, gm, paper1_tmp, prompt_file):
        gm.create_goal("g1", "Summary Goal")
        # Create + add an issue.
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        c.create_workflow("task-a", "# Test\n")
        gm.add_issue("g1", "task-a")
        # Write a codex_review.md for the issue.
        review_path = c.workflow_dir("task-a") / "codex_review.md"
        review_path.write_text("VERDICT: PASS\nSCORE: 100\nAUTORESEARCH_RESULT:PASS\n")

        sp = gm.write_goal_summary("g1")
        assert sp is not None
        assert sp.is_file()
        content = sp.read_text()
        assert "Summary Goal" in content
        assert "task-a" in content

    def test_summary_nonexistent_goal(self, gm):
        sp = gm.write_goal_summary("nonexistent")
        assert sp is None


# ── Goal state serialization ─────────────────────────────────────────────────

# ── Goal completion invariants ────────────────────────────────────────────────

class TestGoalCompletionInvariants:
    def test_goal_with_fail_review_cannot_complete(self, paper1_tmp, prompt_file):
        """Goal with a FAIL codex review must not be complete."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Invariant Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        # Run with fake worker.
        _run(paper1_tmp, "goal-run", "--goal-id", "g1",
             "--worker-cmd", "cat {prompt} > /dev/null; echo 'done' > {output}")

        # Write a FAIL codex review.
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        review_path = c.workflow_dir("task-a") / "codex_review.md"
        review_path.write_text("VERDICT: FAIL\nSCORE: 0/100\nAUTORESEARCH_RESULT:FAIL\n")

        # mark-complete should be rejected due to FAIL review.
        rc = _run(paper1_tmp, "mark-complete", "--issue-id", "task-a")
        assert rc == 1

        # Simulate all issues done and run goal — should detect FAIL.
        gm = GoalManager(paper1_root=paper1_tmp)
        goal = gm.load_goal("g1")
        goal.current_issue_index = 1
        gm._write_goal(goal)
        result = gm.run_goal("g1", dry_run=True)
        assert result["goal_status"] == "failed"

    def test_goal_run_cli_exits_1_when_reviews_fail(self, paper1_tmp, prompt_file):
        """goal-run CLI returns 1 when completed issues include FAIL review."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Fail Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("task-a")
        state.status = "complete"
        c._write_state(state)
        (c.workflow_dir("task-a") / "codex_review.md").write_text(
            "VERDICT: FAIL\nSCORE: 0/100\nAUTORESEARCH_RESULT:FAIL\n"
        )

        rc = _run(paper1_tmp, "goal-run", "--goal-id", "g1", "--dry-run")
        assert rc == 1

    def test_goal_run_cli_exits_2_when_reviews_warn(self, paper1_tmp, prompt_file):
        """goal-run CLI returns 2 when completed issues include WARN review."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Warn Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        state = c.load_state("task-a")
        state.status = "complete"
        c._write_state(state)
        (c.workflow_dir("task-a") / "codex_review.md").write_text(
            "VERDICT: WARN\nSCORE: 90/100\nAUTORESEARCH_RESULT:WARN\n"
        )

        rc = _run(paper1_tmp, "goal-run", "--goal-id", "g1", "--dry-run")
        assert rc == 2

    def test_goal_review_exits_2_on_warn(self, paper1_tmp, prompt_file):
        """goal-review with WARN verdict exits 2. Uses metadata that triggers WARN."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Warn Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        # Create metadata with marker_appended=True (produces WARN from review_issue).
        import json as _json
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        adir = c.attempt_dir("task-a", 1)
        adir.mkdir(parents=True, exist_ok=True)
        meta = {
            "model": "test", "input_tokens": 50, "output_tokens": 20,
            "status_code": 200, "marker_present_in_model_output": True,
            "marker_appended_by_wrapper": True, "error": None,
        }
        (adir / "worker_metadata.json").write_text(_json.dumps(meta))
        # Output must have factual header and PASS marker for the header check.
        (adir / "worker_output.md").write_text("""<!-- AutoResearch API Worker — factual metadata
  model: test
  input_tokens: 50
  output_tokens: 20
  metadata: worker_metadata.json
-->
# Report
AUTORESEARCH_REAL_API_SMOKE:PASS
""")
        # Set attempt in state so coordinator sees it.
        state = c.load_state("task-a")
        state.attempt = 1
        c._write_state(state)

        rc = _run(paper1_tmp, "goal-review", "--goal-id", "g1")
        assert rc == 2  # WARN → exit 2

    def test_goal_review_exits_1_on_fail_no_metadata(self, paper1_tmp, prompt_file):
        """goal-review with missing metadata exits 1 (FAIL)."""
        _run(paper1_tmp, "goal-create", "--goal-id", "g1", "--title", "Fail Goal")
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        _run(paper1_tmp, "goal-add-issue", "--goal-id", "g1", "--issue-id", "task-a")

        rc = _run(paper1_tmp, "goal-review", "--goal-id", "g1")
        assert rc == 1  # No metadata → FAIL → exit 1

    def test_mark_complete_rejects_warn_without_override(self, paper1_tmp, prompt_file):
        """mark-complete rejects WARN review without --owner-override."""
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        review_path = c.workflow_dir("task-a") / "codex_review.md"
        review_path.write_text("VERDICT: WARN\nSCORE: 75/100\nAUTORESEARCH_RESULT:WARN\n")

        rc = _run(paper1_tmp, "mark-complete", "--issue-id", "task-a")
        assert rc == 1  # Rejected — no override

    def test_mark_complete_accepts_warn_with_override(self, paper1_tmp, prompt_file):
        """mark-complete accepts WARN review with --owner-override."""
        _run(paper1_tmp, "create", "--issue-id", "task-a", "--prompt-file", str(prompt_file))
        c = AutoResearchCoordinator(paper1_root=paper1_tmp)
        review_path = c.workflow_dir("task-a") / "codex_review.md"
        review_path.write_text("VERDICT: WARN\nSCORE: 75/100\nAUTORESEARCH_RESULT:WARN\n")

        rc = _run(paper1_tmp, "mark-complete", "--issue-id", "task-a",
                  "--owner-override", "Reviewed WARN, acceptable false positive")
        assert rc == 0  # Accepted with override

        # Verify override recorded in final.md.
        final_path = c.workflow_dir("task-a") / "final.md"
        content = final_path.read_text()
        assert "Owner Override" in content


class TestGoalSerialization:
    def test_to_dict_from_dict(self):
        goal = Goal(goal_id="test", title="T", status="running",
                    issue_ids=["a", "b"], current_issue_index=1)
        d = goal.to_dict()
        g2 = Goal.from_dict(d)
        assert g2.goal_id == "test"
        assert g2.issue_ids == ["a", "b"]
        assert g2.current_issue_index == 1

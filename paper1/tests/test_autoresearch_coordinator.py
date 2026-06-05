"""Tests for AutoResearch coordinator — workflow creation, state, retry, pause."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.autoresearch_coordinator import (  # noqa: E402
    AutoResearchCoordinator,
    PauseReason,
    WorkflowState,
    _safe_slug,
)
from budgetflow.autoresearch_guard import (  # noqa: E402
    ApprovalPolicy,
    ArtifactPolicy,
    requires_owner_approval,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def coordinator(tmp_path):
    """Coordinator scoped to a temp paper1 tree with git root."""
    paper1 = tmp_path / "paper1"
    paper1.mkdir()
    return AutoResearchCoordinator(paper1_root=paper1, git_root=paper1, tmp_root=tmp_path)


@pytest.fixture
def workflow(coordinator):
    """Pre-created workflow for a typical issue."""
    return coordinator.create_workflow(
        "042-fix-bug",
        "# Fix the sympy print bug\n\nRun the fix and verify.",
    )


# ── Safe slug ────────────────────────────────────────────────────────────────

def test_safe_slug_normal():
    assert _safe_slug("042-fix-bug") == "042-fix-bug"


def test_safe_slug_special_chars():
    assert _safe_slug("fix bug (urgent)!") == "fix-bug-urgent"


# ── Workflow creation ────────────────────────────────────────────────────────

class TestWorkflowCreation:
    def test_creates_workflow_dir(self, coordinator, workflow):
        wdir = coordinator.workflow_dir("042-fix-bug")
        assert wdir.is_dir()

    def test_writes_state_json(self, coordinator, workflow):
        sp = coordinator.workflow_dir("042-fix-bug") / "state.json"
        assert sp.is_file()
        d = json.loads(sp.read_text())
        assert d["issue_id"] == "042-fix-bug"
        assert d["status"] == "pending"
        assert d["max_retries"] == 2

    def test_writes_worker_prompt(self, coordinator, workflow):
        pp = coordinator.workflow_dir("042-fix-bug") / "worker_prompt.md"
        assert pp.is_file()
        assert "Fix the sympy print bug" in pp.read_text()

    def test_writes_codex_review_placeholder(self, coordinator, workflow):
        rp = coordinator.workflow_dir("042-fix-bug") / "codex_review.md"
        assert rp.is_file()

    def test_writes_final_placeholder(self, coordinator, workflow):
        fp = coordinator.workflow_dir("042-fix-bug") / "final.md"
        assert fp.is_file()

    def test_creates_attempt_dir(self, coordinator, workflow):
        adir = coordinator.attempt_dir("042-fix-bug", 1)
        assert adir.is_dir()

    def test_writes_worker_output_placeholder(self, coordinator, workflow):
        op = coordinator.attempt_dir("042-fix-bug", 1) / "worker_output.md"
        assert op.is_file()

    def test_workflow_state_initial(self, coordinator, workflow):
        assert workflow.status == "pending"
        assert workflow.attempt == 0
        assert workflow.max_retries == 2

    def test_load_state_roundtrip(self, coordinator, workflow):
        loaded = coordinator.load_state("042-fix-bug")
        assert loaded is not None
        assert loaded.issue_id == workflow.issue_id
        assert loaded.status == workflow.status


# ── Retry ────────────────────────────────────────────────────────────────────

class TestRetry:
    def test_run_increments_attempt(self, coordinator, workflow):
        st = coordinator.run(state=workflow)
        assert st.attempt == 1
        assert st.status == "running"

    def test_retry_max_2(self, coordinator, workflow):
        # First run.
        st = coordinator.run(state=workflow)
        assert st.attempt == 1
        # Second run (after failure).
        st.status = "failed"
        coordinator._write_state(st)
        st2 = coordinator.run(state=st)
        assert st2.attempt == 2
        # Third run (exceeds max_retries) — should still run but be flagged.
        st2.status = "failed"
        coordinator._write_state(st2)
        st3 = coordinator.run(state=st2)
        assert st3.attempt == 3
        # Pause check should fire after exceeding max_retries.
        pauses = coordinator.check_pause_conditions(state=st3)
        assert any(r == PauseReason.RETRY_EXHAUSTED for r, _ in pauses)

    def test_attempt_dirs_increment(self, coordinator, workflow):
        st = coordinator.run(state=workflow)
        assert coordinator.attempt_dir(st.issue_id, 1).is_dir()
        st.status = "failed"
        coordinator._write_state(st)
        st2 = coordinator.run(state=st)
        assert coordinator.attempt_dir(st2.issue_id, 2).is_dir()


# ── Pause conditions ─────────────────────────────────────────────────────────

class TestPauseConditions:
    def test_paid_3x10_triggers(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(
            state=workflow, paid_experiment_scale=(3, 10),
        )
        assert any(r == PauseReason.PAID_3X10 for r, _ in pauses)

    def test_paid_3x7_does_not_trigger(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(
            state=workflow, paid_experiment_scale=(3, 7),
        )
        assert not any(r == PauseReason.PAID_3X10 for r, _ in pauses)

    def test_northstar_change_triggers(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(state=workflow, northstar_change=True)
        assert any(r == PauseReason.NORTHSTAR_CHANGE for r, _ in pauses)

    def test_large_refactor_triggers(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(state=workflow, large_refactor=True)
        assert any(r == PauseReason.LARGE_REFACTOR for r, _ in pauses)

    def test_data_migration_triggers(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(state=workflow, data_migration=True)
        assert any(r == PauseReason.DATA_MIGRATION for r, _ in pauses)

    def test_swebench_docker_triggers(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(state=workflow, swebench_docker=True)
        assert any(r == PauseReason.SWEBENCH_DOCKER for r, _ in pauses)

    def test_higher_risk_triggers(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(state=workflow, higher_risk=True)
        assert any(r == PauseReason.HIGHER_RISK for r, _ in pauses)

    def test_no_flags_no_pause(self, coordinator, workflow):
        pauses = coordinator.check_pause_conditions(state=workflow)
        assert len(pauses) == 0

    def test_run_pauses_on_flag(self, coordinator, workflow):
        st = coordinator.run(state=workflow, paid_experiment_scale=(3, 10))
        assert st.status == "paused"
        assert st.paused_reason == PauseReason.PAID_3X10

    def test_paused_workflow_stays_paused(self, coordinator, workflow):
        st = coordinator.run(state=workflow, paid_experiment_scale=(3, 10))
        assert st.status == "paused"
        # Running again without override should stay paused.
        st2 = coordinator.run(state=st)
        assert st2.status == "paused"


# ── Dry-run ───────────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_call_worker(self, coordinator, workflow):
        called = []
        coordinator.worker_fn = lambda prompt, output: called.append(1) or 0
        st = coordinator.run(state=workflow, dry_run=True)
        assert len(called) == 0
        assert st.status == "running"
        assert st.dry_run is True

    def test_dry_run_writes_state(self, coordinator, workflow):
        st = coordinator.run(state=workflow, dry_run=True)
        loaded = coordinator.load_state(workflow.issue_id)
        assert loaded is not None
        assert loaded.dry_run is True

    def test_dry_run_creates_attempt_dir(self, coordinator, workflow):
        st = coordinator.run(state=workflow, dry_run=True)
        assert coordinator.attempt_dir(st.issue_id, 1).is_dir()


# ── Manual mode ──────────────────────────────────────────────────────────────

class TestManualMode:
    def test_manual_mode_does_not_call_worker(self, coordinator, workflow):
        called = []
        coordinator.worker_fn = lambda prompt, output: called.append(1) or 0
        st = coordinator.run(state=workflow, manual_mode=True)
        assert len(called) == 0
        assert st.manual_mode is True

    def test_manual_mode_has_prompt_path(self, coordinator, workflow):
        st = coordinator.run(state=workflow, manual_mode=True)
        assert Path(st.worker_prompt_path).is_file()

    def test_manual_mode_has_output_path(self, coordinator, workflow):
        st = coordinator.run(state=workflow, manual_mode=True)
        output_dir = Path(st.worker_output_path).parent
        assert output_dir.is_dir()


# ── Mark complete / failed ───────────────────────────────────────────────────

class TestMarkComplete:
    def test_mark_complete(self, coordinator, workflow):
        st = coordinator.run(state=workflow)
        st = coordinator.mark_complete(st)
        assert st.status == "complete"

    def test_complete_writes_final(self, coordinator, workflow):
        st = coordinator.run(state=workflow)
        st = coordinator.mark_complete(st)
        fp = coordinator.workflow_dir(st.issue_id) / "final.md"
        assert fp.is_file()
        assert "complete" in fp.read_text()

    def test_mark_failed(self, coordinator, workflow):
        st = coordinator.run(state=workflow)
        st = coordinator.mark_failed(st)
        assert st.status == "failed"


# ── ArtifactPolicy — workflow checkpoint policy ─────────────────────────────

class TestArtifactPolicyWorkflows:
    """ArtifactPolicy must accept durable workflow checkpoint files."""

    @staticmethod
    def policy():
        return ArtifactPolicy(project_root=Path("/repo/paper1"))

    def test_allows_state_json(self):
        assert self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/state.json")
        )

    def test_allows_worker_prompt_md(self):
        assert self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/worker_prompt.md")
        )

    def test_allows_codex_review_md(self):
        assert self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/codex_review.md")
        )

    def test_allows_final_md(self):
        assert self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/final.md")
        )

    def test_allows_worker_output_md(self):
        assert self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/attempts/001/worker_output.md")
        )

    def test_allows_worker_output_log(self):
        assert self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/attempts/002/worker_output.log")
        )

    def test_rejects_random_tmp_in_attempts(self):
        assert not self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/attempts/001/random.tmp")
        )

    def test_rejects_unknown_workflow_file(self):
        assert not self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/log.md")
        )

    def test_rejects_workflow_dir_itself(self):
        assert not self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034")
        )

    def test_rejects_attempts_dir_itself(self):
        assert not self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/.autoresearch/workflows/034/attempts/001")
        )

    def test_data_runs_still_rejected(self):
        rejected = [
            Path("/repo/paper1/data/runs/postfix_029.jsonl"),
            Path("/repo/paper1/data/runs/compare_5x5.jsonl"),
            Path("/repo/paper1/data/runs/checkpoint.json"),
        ]
        for path in rejected:
            assert not self.policy().is_allowed_for_autoresearch_checkpoint(path), f"should reject {path}"

    def test_src_still_rejected(self):
        assert not self.policy().is_allowed_for_autoresearch_checkpoint(
            Path("/repo/paper1/src/budgetflow/run_mini_swe_compare.py")
        )

    def test_baseline_autoresearch_still_accepted(self):
        """program.md, agents/, issues/ should still be accepted."""
        allowed = [
            Path("/repo/paper1/.autoresearch/program.md"),
            Path("/repo/paper1/.autoresearch/agents/codex.md"),
            Path("/repo/paper1/.autoresearch/issues/042-fix-bug.md"),
        ]
        for path in allowed:
            assert self.policy().is_allowed_for_autoresearch_checkpoint(path), f"should allow {path}"

    def test_docs_still_accepted(self):
        allowed = [
            Path("/repo/paper1/docs/autoresearch_workflow.md"),
            Path("/repo/paper1/docs/reports/034.md"),
        ]
        for path in allowed:
            assert self.policy().is_allowed_for_autoresearch_checkpoint(path), f"should allow {path}"

    def test_approval_policy_3x10_paid(self):
        policy = ApprovalPolicy(policy_count=3, task_count=10, paid=True, owner_approved=False)
        assert policy.must_stop_before_run()

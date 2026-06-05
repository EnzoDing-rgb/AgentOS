"""AutoResearch minimum viable coordinator.

Non-invasive state machine that manages workflow directories, writes worker
prompts, captures outputs, and enforces pause conditions. Does NOT call the
Worker, make API calls, or auto-commit — those are external integrations.

Usage:
  from budgetflow.autoresearch_coordinator import AutoResearchCoordinator

  c = AutoResearchCoordinator(paper1_root=Path("paper1"))
  c.create_workflow("042-fix-bug", worker_prompt="Fix the thing.")
  c.run(dry_run=True)   # write prompts/state, no Worker
  c.run(manual=True)    # write prompts, print path for manual execution
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .autoresearch_guard import (
    ApprovalPolicy,
    ArtifactPolicy,
    RuntimePolicy,
    requires_owner_approval,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_slug(raw: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.strip()).strip("-")
    return slug or "issue"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Pause conditions enum ────────────────────────────────────────────────────

class PauseReason:
    PAID_3X10 = "paid_3x10_or_larger"
    NORTHSTAR_CHANGE = "northstar_or_metric_change"
    LARGE_REFACTOR = "large_runner_workflow_harness_storage_refactor"
    DATA_MIGRATION = "delete_or_migrate_experiment_data"
    SWEBENCH_DOCKER = "official_swebench_docker_run"
    RETRY_EXHAUSTED = "retry_exhausted_after_2_attempts"
    HIGHER_RISK = "materially_higher_cost_runtime_or_rollback_risk"

    @classmethod
    def all_labels(cls) -> dict[str, str]:
        return {
            cls.PAID_3X10: "Paid 3x10 or larger experiment",
            cls.NORTHSTAR_CHANGE: "NorthStar or evaluation metric change",
            cls.LARGE_REFACTOR: "Large runner/workflow/harness/storage refactor",
            cls.DATA_MIGRATION: "Delete or migrate experiment data",
            cls.SWEBENCH_DOCKER: "Official SWE-bench Docker run",
            cls.RETRY_EXHAUSTED: "Retry exhausted after 2 failed attempts",
            cls.HIGHER_RISK: "Materially higher cost/runtime/rollback risk",
        }


# ── State ────────────────────────────────────────────────────────────────────

@dataclass
class WorkflowState:
    issue_id: str
    status: str = "pending"  # pending | running | paused | complete | failed
    attempt: int = 0
    max_retries: int = 2
    paused_reason: str | None = None
    paused_reason_label: str | None = None
    created_at: str = ""
    updated_at: str = ""
    worker_prompt_path: str = ""
    worker_output_path: str = ""
    codex_review_path: str = ""
    final_path: str = ""
    dry_run: bool = False
    manual_mode: bool = False

    def to_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "status": self.status,
            "attempt": self.attempt,
            "max_retries": self.max_retries,
            "paused_reason": self.paused_reason,
            "paused_reason_label": self.paused_reason_label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "worker_prompt_path": self.worker_prompt_path,
            "worker_output_path": self.worker_output_path,
            "codex_review_path": self.codex_review_path,
            "final_path": self.final_path,
            "dry_run": self.dry_run,
            "manual_mode": self.manual_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowState:
        return cls(
            issue_id=d["issue_id"],
            status=d.get("status", "pending"),
            attempt=d.get("attempt", 0),
            max_retries=d.get("max_retries", 2),
            paused_reason=d.get("paused_reason"),
            paused_reason_label=d.get("paused_reason_label"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            worker_prompt_path=d.get("worker_prompt_path", ""),
            worker_output_path=d.get("worker_output_path", ""),
            codex_review_path=d.get("codex_review_path", ""),
            final_path=d.get("final_path", ""),
            dry_run=d.get("dry_run", False),
            manual_mode=d.get("manual_mode", False),
        )


# ── Coordinator ──────────────────────────────────────────────────────────────

@dataclass
class AutoResearchCoordinator:
    """Minimum viable coordinator that manages workflow state on disk.

    Does NOT call Worker, make API calls, or auto-commit. Those are
    external integrations called by the owner or Codex after reviewing
    the written prompts and state.
    """

    paper1_root: Path
    git_root: Path | None = None
    tmp_root: Path = Path("/tmp")
    max_retries: int = 2

    # Optional callbacks for external integration (not called by default).
    worker_fn: Callable[[Path, Path], int] | None = None
    codex_review_fn: Callable[[Path, Path], str] | None = None

    def __post_init__(self) -> None:
        self.paper1_root = Path(self.paper1_root).resolve()
        self.git_root = Path(self.git_root or self.paper1_root).resolve()
        self.tmp_root = Path(self.tmp_root).resolve()
        self._runtime_policy = RuntimePolicy(
            project_root=self.paper1_root,
            git_root=self.git_root,
            tmp_root=self.tmp_root,
        )
        self._artifact_policy = ArtifactPolicy(project_root=self.paper1_root)

    # ── Paths ────────────────────────────────────────────────────────────────

    @property
    def workflows_dir(self) -> Path:
        return self.paper1_root / ".autoresearch" / "workflows"

    def workflow_dir(self, issue_id: str) -> Path:
        return self.workflows_dir / _safe_slug(issue_id)

    def attempts_dir(self, issue_id: str) -> Path:
        return self.workflow_dir(issue_id) / "attempts"

    def attempt_dir(self, issue_id: str, attempt: int) -> Path:
        return self.attempts_dir(issue_id) / f"{attempt:03d}"

    def _state_path(self, issue_id: str) -> Path:
        return self.workflow_dir(issue_id) / "state.json"

    # ── State I/O ────────────────────────────────────────────────────────────

    def _write_state(self, state: WorkflowState) -> None:
        state.updated_at = _now_iso()
        state_path = self._state_path(state.issue_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n"
        )

    def load_state(self, issue_id: str) -> WorkflowState | None:
        sp = self._state_path(issue_id)
        if not sp.is_file():
            return None
        return WorkflowState.from_dict(json.loads(sp.read_text()))

    # ── Workflow creation ────────────────────────────────────────────────────

    def create_workflow(
        self,
        issue_id: str,
        worker_prompt: str,
        *,
        dry_run: bool = False,
        manual_mode: bool = False,
    ) -> WorkflowState:
        """Create workflow directory and write initial prompt + state.

        Returns the initial WorkflowState. Does NOT invoke the Worker.
        """
        wdir = self.workflow_dir(issue_id)
        wdir.mkdir(parents=True, exist_ok=True)
        adir = self.attempt_dir(issue_id, 1)
        adir.mkdir(parents=True, exist_ok=True)

        # Write worker prompt.
        prompt_path = self.workflow_dir(issue_id) / "worker_prompt.md"
        prompt_path.write_text(worker_prompt.strip() + "\n")

        # Write placeholder files.
        output_path = adir / "worker_output.md"
        output_path.write_text("(pending)\n")
        review_path = self.workflow_dir(issue_id) / "codex_review.md"
        review_path.write_text("(pending — Codex review required)\n")
        final_path = self.workflow_dir(issue_id) / "final.md"
        final_path.write_text("(pending)\n")

        state = WorkflowState(
            issue_id=issue_id,
            status="pending",
            attempt=0,
            max_retries=self.max_retries,
            created_at=_now_iso(),
            worker_prompt_path=str(prompt_path),
            worker_output_path=str(output_path),
            codex_review_path=str(review_path),
            final_path=str(final_path),
            dry_run=dry_run,
            manual_mode=manual_mode,
        )
        self._write_state(state)
        return state

    def _write_attempt_files(self, state: WorkflowState) -> None:
        """Ensure per-attempt directories and placeholder files exist."""
        adir = self.attempt_dir(state.issue_id, state.attempt)
        adir.mkdir(parents=True, exist_ok=True)
        out = adir / "worker_output.md"
        if not out.exists():
            out.write_text("(pending)\n")
        state.worker_output_path = str(out)
        review = self.workflow_dir(state.issue_id) / "codex_review.md"
        if not review.exists():
            review.write_text("(pending — Codex review required)\n")
        state.codex_review_path = str(review)

    # ── Pause conditions ─────────────────────────────────────────────────────

    def check_pause_conditions(
        self,
        *,
        state: WorkflowState | None = None,
        paid_experiment_scale: tuple[int, int] | None = None,
        northstar_change: bool = False,
        large_refactor: bool = False,
        data_migration: bool = False,
        swebench_docker: bool = False,
        higher_risk: bool = False,
    ) -> list[tuple[str, str]]:
        """Return list of (reason_key, reason_label) that would pause.

        Callers should supply flags based on the issue context. If any flag
        is True, that pause condition is triggered.
        """
        triggered: list[tuple[str, str]] = []
        labels = PauseReason.all_labels()

        if paid_experiment_scale is not None:
            pc, tc = paid_experiment_scale
            if requires_owner_approval(policy_count=pc, task_count=tc, paid=True):
                triggered.append((PauseReason.PAID_3X10, labels[PauseReason.PAID_3X10]))
        if northstar_change:
            triggered.append((PauseReason.NORTHSTAR_CHANGE, labels[PauseReason.NORTHSTAR_CHANGE]))
        if large_refactor:
            triggered.append((PauseReason.LARGE_REFACTOR, labels[PauseReason.LARGE_REFACTOR]))
        if data_migration:
            triggered.append((PauseReason.DATA_MIGRATION, labels[PauseReason.DATA_MIGRATION]))
        if swebench_docker:
            triggered.append((PauseReason.SWEBENCH_DOCKER, labels[PauseReason.SWEBENCH_DOCKER]))
        if higher_risk:
            triggered.append((PauseReason.HIGHER_RISK, labels[PauseReason.HIGHER_RISK]))

        if state is not None and state.attempt > state.max_retries:
            triggered.append((PauseReason.RETRY_EXHAUSTED, labels[PauseReason.RETRY_EXHAUSTED]))

        return triggered

    # ── Run loop ─────────────────────────────────────────────────────────────

    def run(
        self,
        *,
        issue_id: str | None = None,
        state: WorkflowState | None = None,
        dry_run: bool = False,
        manual_mode: bool = False,
        # Pause condition flags — default False = safe.
        paid_experiment_scale: tuple[int, int] | None = None,
        northstar_change: bool = False,
        large_refactor: bool = False,
        data_migration: bool = False,
        swebench_docker: bool = False,
        higher_risk: bool = False,
    ) -> WorkflowState:
        """Execute one step of the workflow lifecycle.

        If state is "pending": start the first attempt.
        If state is "running": this is a no-op (caller manages Worker).
        If state is "retry": increment attempt and re-run.
        If state is "paused": do not proceed.

        The coordinator writes prompts and state to disk. It does NOT call
        the Worker — the caller is responsible for executing the prompt and
        writing the output back to the attempt dir.
        """
        if state is None and issue_id is not None:
            state = self.load_state(issue_id)
        if state is None:
            raise ValueError("No state provided and no existing workflow found.")

        state.dry_run = dry_run
        state.manual_mode = manual_mode

        # Check pause conditions.
        pauses = self.check_pause_conditions(
            state=state,
            paid_experiment_scale=paid_experiment_scale,
            northstar_change=northstar_change,
            large_refactor=large_refactor,
            data_migration=data_migration,
            swebench_docker=swebench_docker,
            higher_risk=higher_risk,
        )
        if pauses:
            reason_key, reason_label = pauses[0]
            state.status = "paused"
            state.paused_reason = reason_key
            state.paused_reason_label = reason_label
            self._write_state(state)
            self._log_pause(state)
            return state

        if state.status == "paused":
            # Don't auto-resume; caller must explicitly override.
            return state

        if state.status in ("pending", "failed"):
            state.status = "running"
            state.attempt += 1
            self._write_attempt_files(state)
            self._write_state(state)

            # Dry-run: write prompt, skip Worker invocation.
            if dry_run:
                print(f"[autoresearch] DRY-RUN issue={state.issue_id} attempt={state.attempt}")
                print(f"  prompt: {state.worker_prompt_path}")
                print(f"  output: {state.worker_output_path}")
                return state

            # Manual mode: print the prompt path, caller executes manually.
            if manual_mode:
                print(f"[autoresearch] MANUAL MODE — execute this prompt, then write output to disk:")
                print(f"  prompt: {state.worker_prompt_path}")
                print(f"  output: {state.worker_output_path}")
                print(f"  review: {state.codex_review_path}")
                return state

            # Invoke worker callback if registered.
            if self.worker_fn is not None:
                exit_code = self.worker_fn(
                    Path(state.worker_prompt_path),
                    Path(state.worker_output_path),
                )
                if exit_code == 0:
                    state.status = "complete"
                elif state.attempt <= state.max_retries:
                    state.status = "failed"
                else:
                    state.status = "failed"
                    state.paused_reason = PauseReason.RETRY_EXHAUSTED
                    state.paused_reason_label = PauseReason.all_labels()[PauseReason.RETRY_EXHAUSTED]

        elif state.status == "running":
            # Already running; caller manages the worker externally.
            pass

        self._write_state(state)
        return state

    def mark_complete(self, state: WorkflowState) -> WorkflowState:
        """Mark workflow as complete after Codex gate approval."""
        state.status = "complete"
        self._write_state(state)
        final = Path(state.final_path)
        final.write_text(
            f"# {state.issue_id} — Final Summary\n\n"
            f"Status: complete\n"
            f"Attempts: {state.attempt}\n"
            f"Completed at: {_now_iso()}\n\n"
            f"Worker prompt: {state.worker_prompt_path}\n"
            f"Codex review: {state.codex_review_path}\n"
        )
        return state

    def mark_failed(self, state: WorkflowState, reason: str = "") -> WorkflowState:
        """Mark workflow as permanently failed."""
        state.status = "failed"
        self._write_state(state)
        return state

    # ── Logging ──────────────────────────────────────────────────────────────

    def _log_pause(self, state: WorkflowState) -> None:
        print(
            f"\n[autoresearch] PAUSED issue={state.issue_id}\n"
            f"  reason: {state.paused_reason_label}\n"
            f"  key: {state.paused_reason}\n"
            f"  attempt: {state.attempt}/{state.max_retries}\n"
            f"  state: {self._state_path(state.issue_id)}\n",
            flush=True,
        )

    def print_status(self, issue_id: str) -> None:
        """Print current workflow status for manual inspection."""
        state = self.load_state(issue_id)
        if state is None:
            print(f"No workflow found for {issue_id}")
            return
        labels = PauseReason.all_labels()
        paused = f" ({labels.get(state.paused_reason or '', state.paused_reason or '')})" if state.paused_reason else ""
        print(
            f"issue={state.issue_id} status={state.status}{paused} "
            f"attempt={state.attempt}/{state.max_retries} "
            f"dry_run={state.dry_run} manual={state.manual_mode}",
            flush=True,
        )
        if state.status == "paused":
            print(f"  To resume: coordinator.resume('{state.issue_id}')", flush=True)
        if state.manual_mode:
            print(f"  prompt: {state.worker_prompt_path}", flush=True)
            print(f"  output: {state.worker_output_path}", flush=True)

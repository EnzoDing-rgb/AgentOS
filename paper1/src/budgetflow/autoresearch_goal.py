"""AutoResearch Goal-level coordinator.

A Goal groups multiple issues under a shared objective, tracks progress,
and iterates through issues with retry and pause enforcement.

Usage:
  from budgetflow.autoresearch_goal import Goal, GoalManager

  gm = GoalManager(paper1_root=Path("paper1"))
  gm.create_goal("039-smoke", "Real API Goal Smoke", budget_cap_usd=0.30)
  gm.add_issue("039-smoke", "039-issue-a")
  gm.add_issue("039-smoke", "039-issue-b")
  gm.run_goal("039-smoke", dry_run=True)
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .autoresearch_coordinator import AutoResearchCoordinator, PauseReason


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Goal state ───────────────────────────────────────────────────────────────


@dataclass
class Goal:
    goal_id: str
    title: str = ""
    status: str = "pending"  # pending | running | paused | review_required | complete | failed
    issue_ids: list[str] = field(default_factory=list)
    current_issue_index: int = 0
    max_retries_per_issue: int = 2
    real_api_budget_cap_usd: float = 0.0
    total_api_calls: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "title": self.title,
            "status": self.status,
            "issue_ids": self.issue_ids,
            "current_issue_index": self.current_issue_index,
            "max_retries_per_issue": self.max_retries_per_issue,
            "real_api_budget_cap_usd": self.real_api_budget_cap_usd,
            "total_api_calls": self.total_api_calls,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Goal:
        return cls(
            goal_id=d["goal_id"],
            title=d.get("title", ""),
            status=d.get("status", "pending"),
            issue_ids=d.get("issue_ids", []),
            current_issue_index=d.get("current_issue_index", 0),
            max_retries_per_issue=d.get("max_retries_per_issue", 2),
            real_api_budget_cap_usd=d.get("real_api_budget_cap_usd", 0.0),
            total_api_calls=d.get("total_api_calls", 0),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


# ── Goal manager ─────────────────────────────────────────────────────────────


@dataclass
class GoalManager:
    paper1_root: Path
    coordinator: AutoResearchCoordinator | None = None

    def __post_init__(self) -> None:
        self.paper1_root = Path(self.paper1_root).resolve()
        if self.coordinator is None:
            self.coordinator = AutoResearchCoordinator(paper1_root=self.paper1_root)

    @property
    def goals_dir(self) -> Path:
        return self.paper1_root / ".autoresearch" / "goals"

    def _goal_path(self, goal_id: str) -> Path:
        from .autoresearch_coordinator import _safe_slug
        return self.goals_dir / f"{_safe_slug(goal_id)}.json"

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_goal(self, goal_id: str, title: str, *, budget_cap_usd: float = 0.0,
                    max_retries: int = 2) -> Goal:
        self.goals_dir.mkdir(parents=True, exist_ok=True)
        goal = Goal(
            goal_id=goal_id, title=title,
            max_retries_per_issue=max_retries,
            real_api_budget_cap_usd=budget_cap_usd,
            created_at=_now_iso(),
        )
        self._write_goal(goal)
        return goal

    def load_goal(self, goal_id: str) -> Goal | None:
        gp = self._goal_path(goal_id)
        if not gp.is_file():
            return None
        return Goal.from_dict(json.loads(gp.read_text()))

    def _write_goal(self, goal: Goal) -> None:
        goal.updated_at = _now_iso()
        self.goals_dir.mkdir(parents=True, exist_ok=True)
        path = self._goal_path(goal.goal_id)
        path.write_text(json.dumps(goal.to_dict(), indent=2, ensure_ascii=False) + "\n")

    def add_issue(self, goal_id: str, issue_id: str) -> Goal | None:
        goal = self.load_goal(goal_id)
        if goal is None:
            return None
        if issue_id not in goal.issue_ids:
            goal.issue_ids.append(issue_id)
            self._write_goal(goal)
        return goal

    # ── Run ───────────────────────────────────────────────────────────────────

    def _check_goal_reviews(self, goal: Goal) -> str:
        """Check all issue codex reviews for the goal.

        Returns 'pass' (all PASS), 'warn' (any WARN, no FAIL), or 'fail' (any FAIL).
        """
        assert self.coordinator is not None
        worst = "pass"
        for issue_id in goal.issue_ids:
            review_path = self.coordinator.workflow_dir(issue_id) / "codex_review.md"
            if not review_path.is_file():
                continue
            text = review_path.read_text()
            if "VERDICT: FAIL" in text:
                return "fail"
            if "VERDICT: WARN" in text:
                worst = "warn"
        return worst

    def run_goal(
        self,
        goal_id: str,
        *,
        dry_run: bool = False,
        manual_mode: bool = False,
        worker_cmd: str | None = None,
        paid_experiment_scale: tuple[int, int] | None = None,
        northstar_change: bool = False,
        large_refactor: bool = False,
        data_migration: bool = False,
        swebench_docker: bool = False,
        higher_risk: bool = False,
    ) -> dict:
        """Run one step of a Goal — process the next pending/failed issue.

        Returns a dict with keys: goal_status, issue_id, issue_status, action, error.
        """
        goal = self.load_goal(goal_id)
        if goal is None:
            return {"goal_status": "error", "error": f"Goal not found: {goal_id}"}

        assert self.coordinator is not None

        # Check for pause conditions before touching any issue.
        pauses = self.coordinator.check_pause_conditions(
            paid_experiment_scale=paid_experiment_scale,
            northstar_change=northstar_change,
            large_refactor=large_refactor,
            data_migration=data_migration,
            swebench_docker=swebench_docker,
            higher_risk=higher_risk,
        )
        if pauses:
            goal.status = "paused"
            self._write_goal(goal)
            return {"goal_status": "paused", "pause_reason": pauses[0][1]}

        if goal.status == "paused":
            return {"goal_status": "paused", "action": "owner/Codex approval required"}

        # Find the next issue to work on.
        result = self._find_next_issue(goal)
        if result is None:
            review_status = self._check_goal_reviews(goal)
            if review_status == "fail":
                goal.status = "failed"
                self._write_goal(goal)
                return {"goal_status": "failed", "action": "all issues done but review FAIL — goal cannot complete"}
            elif review_status == "warn":
                goal.status = "review_required"
                self._write_goal(goal)
                return {"goal_status": "review_required", "action": "all issues done but review WARN — owner approval required"}
            goal.status = "complete"
            self._write_goal(goal)
            return {"goal_status": "complete", "action": "all issues complete and reviewed PASS"}

        issue_id, issue_state = result
        goal.status = "running"
        goal.current_issue_index = goal.issue_ids.index(issue_id) if issue_id in goal.issue_ids else goal.current_issue_index

        # Build worker callback if worker_cmd provided.
        worker_fn = None
        if worker_cmd:
            from .run_autoresearch import _make_worker_cmd, _validate_worker_cmd
            _validate_worker_cmd(worker_cmd)
            worker_fn = _make_worker_cmd(worker_cmd)
            self.coordinator.worker_fn = worker_fn
        elif not dry_run and not manual_mode:
            manual_mode = True

        # Run the issue.
        state = self.coordinator.run(
            state=issue_state,
            dry_run=dry_run,
            manual_mode=manual_mode,
            paid_experiment_scale=paid_experiment_scale,
            northstar_change=northstar_change,
            large_refactor=large_refactor,
            data_migration=data_migration,
            swebench_docker=swebench_docker,
            higher_risk=higher_risk,
        )

        if state.status == "paused":
            goal.status = "paused"
            self._write_goal(goal)
            return {"goal_status": "paused", "issue_id": issue_id, "pause_reason": state.paused_reason_label}

        if state.status == "failed":
            if state.attempt > goal.max_retries_per_issue:
                # Exhausted retries for this issue; move to next on next run.
                goal.current_issue_index += 1
            # Otherwise, leave current_issue_index so next run retries.
            self._write_goal(goal)
            return {"goal_status": "running", "issue_id": issue_id, "issue_status": "failed",
                    "attempt": state.attempt, "max_retries": goal.max_retries_per_issue}

        if state.status == "complete" or state.status == "running":
            # Issue in progress or complete. Move index past this issue.
            if state.status == "complete":
                goal.current_issue_index += 1
            self._write_goal(goal)
            return {"goal_status": "running", "issue_id": issue_id, "issue_status": state.status}

        self._write_goal(goal)
        return {"goal_status": goal.status, "issue_id": issue_id, "issue_status": state.status}

    def _find_next_issue(self, goal: Goal):
        """Return (issue_id, WorkflowState) for the next issue to process, or None."""
        assert self.coordinator is not None
        for idx in range(goal.current_issue_index, len(goal.issue_ids)):
            issue_id = goal.issue_ids[idx]
            state = self.coordinator.load_state(issue_id)
            if state is None:
                continue
            if state.status in ("pending", "failed"):
                return issue_id, state
            # Already complete — skip.
        return None

    # ── Status ────────────────────────────────────────────────────────────────

    def print_goal_status(self, goal_id: str) -> None:
        goal = self.load_goal(goal_id)
        if goal is None:
            print(f"No goal found for {goal_id}")
            return
        assert self.coordinator is not None
        print(f"Goal: {goal.goal_id} — {goal.title}")
        print(f"  status: {goal.status}")
        print(f"  budget_cap: ${goal.real_api_budget_cap_usd:.2f}")
        print(f"  issues: {len(goal.issue_ids)} total, current index {goal.current_issue_index}")
        print()
        labels = PauseReason.all_labels()
        for i, issue_id in enumerate(goal.issue_ids):
            state = self.coordinator.load_state(issue_id)
            if state is None:
                print(f"  [{i}] {issue_id} — no workflow")
                continue
            marker = " <-- next" if i == goal.current_issue_index and state.status != "complete" else ""
            paused = f" PAUSED({labels.get(state.paused_reason or '', state.paused_reason or '')})" if state.paused_reason else ""
            print(f"  [{i}] {issue_id} — {state.status} attempt={state.attempt}/{state.max_retries}{paused}{marker}")
        print()

    def _aggregate_goal_metadata(self, goal: Goal) -> dict:
        """Aggregate facts from worker_metadata.json across all issues.

        Returns dict with: total_api_calls, total_input_tokens, total_output_tokens,
        marker_appended_count, successful_http_calls.
        """
        result = {
            "total_api_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "marker_appended_count": 0,
            "successful_http_calls": 0,
        }
        assert self.coordinator is not None
        for issue_id in goal.issue_ids:
            wf_dir = self.coordinator.workflow_dir(issue_id)
            attempts_dir = wf_dir / "attempts"
            if not attempts_dir.is_dir():
                continue
            # Find the highest attempt number.
            attempt_nums = sorted(
                int(d.name) for d in attempts_dir.iterdir()
                if d.is_dir() and d.name.isdigit()
            )
            for anum in reversed(attempt_nums):
                meta_path = attempts_dir / f"{anum:03d}" / "worker_metadata.json"
                if meta_path.is_file():
                    try:
                        meta = json.loads(meta_path.read_text())
                    except json.JSONDecodeError:
                        continue
                    result["total_api_calls"] += 1
                    result["total_input_tokens"] += meta.get("input_tokens", 0) or 0
                    result["total_output_tokens"] += meta.get("output_tokens", 0) or 0
                    if meta.get("marker_appended_by_wrapper"):
                        result["marker_appended_count"] += 1
                    if meta.get("status_code") == 200:
                        result["successful_http_calls"] += 1
                    break  # Only count the latest attempt per issue.
        return result

    def write_goal_summary(self, goal_id: str) -> Path | None:
        """Write a goal-level summary markdown, aggregating live metadata."""
        goal = self.load_goal(goal_id)
        if goal is None:
            return None
        assert self.coordinator is not None

        agg = self._aggregate_goal_metadata(goal)

        # Update goal JSON with live facts.
        goal.total_api_calls = agg["total_api_calls"]
        self._write_goal(goal)

        lines = [
            f"# Goal Summary — {goal.goal_id}",
            "",
            f"**Title:** {goal.title}",
            f"**Status:** {goal.status}",
            f"**Budget cap:** ${goal.real_api_budget_cap_usd:.2f}",
            f"**Total API calls:** {agg['total_api_calls']}",
            f"**Total input tokens:** {agg['total_input_tokens']}",
            f"**Total output tokens:** {agg['total_output_tokens']}",
            f"**Successful HTTP calls:** {agg['successful_http_calls']}",
            f"**Marker appended by wrapper:** {agg['marker_appended_count']}",
            f"**Created:** {goal.created_at}",
            f"**Updated:** {goal.updated_at}",
            "",
            "## Issues",
            "",
        ]
        for i, issue_id in enumerate(goal.issue_ids):
            state = self.coordinator.load_state(issue_id)
            if state is None:
                lines.append(f"- [{i}] **{issue_id}** — no workflow")
            else:
                lines.append(f"- [{i}] **{issue_id}** — {state.status} (attempt {state.attempt}/{state.max_retries})")
        lines.append("")
        lines.append("## Verdicts")
        lines.append("")
        lines.append("| Issue | Verdict | Score |")
        lines.append("|-------|---------|-------|")
        for issue_id in goal.issue_ids:
            wf_dir = self.coordinator.workflow_dir(issue_id)
            review_path = wf_dir / "codex_review.md"
            if review_path.is_file():
                text = review_path.read_text()
                verdict = "?"
                score = "?"
                for line in text.splitlines():
                    if line.startswith("VERDICT:"):
                        verdict = line.split(":", 1)[1].strip()
                    if line.startswith("SCORE:"):
                        score = line.split(":", 1)[1].strip()
                lines.append(f"| {issue_id} | {verdict} | {score} |")
            else:
                lines.append(f"| {issue_id} | NO REVIEW | — |")

        sp = self.goals_dir / f"{goal.goal_id}.summary.md"
        sp.write_text("\n".join(lines) + "\n")
        return sp

"""Safety policy for running AutoResearch around BudgetFlow.

This module is intentionally non-invasive: it does not run AutoResearch or
modify experiment code.  It centralizes the rules that wrappers must enforce
before letting an autonomous loop touch this repository.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


def _resolve(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _safe_slug(raw: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.strip()).strip("-")
    return slug or "autoresearch"


@dataclass(frozen=True)
class RuntimePolicy:
    """Decides where AutoResearch runtime state is allowed to live."""

    project_root: Path
    git_root: Path
    tmp_root: Path = Path("/tmp")

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", _resolve(self.project_root))
        object.__setattr__(self, "git_root", _resolve(self.git_root))
        object.__setattr__(self, "tmp_root", _resolve(self.tmp_root))

    def requires_isolated_checkout(self) -> bool:
        """Return true when direct AutoResearch local mode is unsafe."""
        return self.project_root != self.git_root

    def isolation_reason(self) -> str:
        if self.requires_isolated_checkout():
            return (
                "project root is not git root; direct local-mode AutoResearch "
                "would run git add -A from the monorepo root"
            )
        return "project root is git root"

    def runtime_root(self, *, goal_slug: str) -> Path:
        """High-churn AutoResearch workflow state belongs on local scratch."""
        return self.tmp_root / f"budgetflow-autoresearch-{_safe_slug(goal_slug)}"

    def environment(self) -> dict[str, str]:
        """Environment defaults for high-churn subprocesses."""
        return {
            "TMPDIR": str(self.tmp_root),
            "PIP_CACHE_DIR": os.environ.get("PIP_CACHE_DIR", "/tmp/budgetflow-pip-cache"),
        }


def requires_owner_approval(*, policy_count: int, task_count: int, paid: bool) -> bool:
    """Owner approval gate for paid experiment scale."""
    if not paid:
        return False
    return policy_count >= 3 and task_count >= 10


@dataclass(frozen=True)
class ApprovalPolicy:
    policy_count: int
    task_count: int
    paid: bool
    owner_approved: bool = False

    def must_stop_before_run(self) -> bool:
        return (
            requires_owner_approval(
                policy_count=self.policy_count,
                task_count=self.task_count,
                paid=self.paid,
            )
            and not self.owner_approved
        )

    def reason(self) -> str:
        if self.must_stop_before_run():
            return (
                "owner approval required before paid experiment "
                f"{self.policy_count}x{self.task_count}"
            )
        return "owner approval not required"


@dataclass(frozen=True)
class ArtifactPolicy:
    """Whitelist accepted artifacts that AutoResearch may checkpoint."""

    project_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", _resolve(self.project_root))

    def is_allowed_for_autoresearch_checkpoint(self, path: Path) -> bool:
        try:
            rel = _resolve(path).relative_to(self.project_root)
        except ValueError:
            return False

        parts = rel.parts
        if not parts:
            return False

        if parts[0] in {"src", "tests", "tmp"}:
            return False
        if parts[:2] == ("data", "runs"):
            return False

        if parts[0] == ".autoresearch":
            return self._is_allowed_autoresearch_path(parts)
        if parts[0] == "docs":
            return self._is_allowed_docs_path(parts)
        return False

    @staticmethod
    def _is_allowed_autoresearch_path(parts: tuple[str, ...]) -> bool:
        if len(parts) < 2:
            return False
        if parts[1] in {"program.md", "agents", "issues"}:
            return True
        if parts[1] == "workflows":
            return ArtifactPolicy._is_allowed_workflow_path(parts)
        return False

    @staticmethod
    def _is_allowed_workflow_path(parts: tuple[str, ...]) -> bool:
        """Whitelist specific durable files under .autoresearch/workflows/<id>/.

        Allowed: state.json, worker_prompt.md, codex_review.md, final.md,
        attempts/<NNN>/worker_output.md, attempts/<NNN>/worker_output.log.
        """
        if len(parts) < 3:
            return False  # .autoresearch/workflows alone — no issue dir
        # parts[0] = .autoresearch, parts[1] = workflows, parts[2] = <issue_id>
        if len(parts) == 3:
            return False  # issue dir itself, not a file
        if len(parts) == 4:
            # Top-level workflow files: state.json, worker_prompt.md, codex_review.md, final.md
            return parts[3] in {"state.json", "worker_prompt.md", "codex_review.md", "final.md"}
        if len(parts) >= 5 and parts[3] == "attempts":
            # attempts/<NNN>/<file>
            if len(parts) == 6:
                return parts[5] in {"worker_output.md", "worker_output.log"}
        return False

    @staticmethod
    def _is_allowed_docs_path(parts: tuple[str, ...]) -> bool:
        if len(parts) < 2:
            return False
        if parts[1] == "autoresearch_workflow.md":
            return True
        if parts[1] == "reports" and len(parts) >= 3:
            return True
        return False


def current_tmp_root() -> Path:
    return Path(os.environ.get("TMPDIR") or "/tmp")

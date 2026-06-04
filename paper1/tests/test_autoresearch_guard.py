from pathlib import Path

from budgetflow.autoresearch_guard import (
    ApprovalPolicy,
    ArtifactPolicy,
    RuntimePolicy,
    requires_owner_approval,
)


def test_runtime_policy_requires_isolation_for_project_subdir_repo(tmp_path):
    repo_root = tmp_path / "AgentOS"
    project_root = repo_root / "paper1"
    repo_root.mkdir()
    project_root.mkdir()

    policy = RuntimePolicy(project_root=project_root, git_root=repo_root)

    assert policy.requires_isolated_checkout()
    assert "project root is not git root" in policy.isolation_reason()


def test_runtime_policy_allows_direct_run_for_isolated_project_repo(tmp_path):
    project_root = tmp_path / "paper1"
    project_root.mkdir()

    policy = RuntimePolicy(project_root=project_root, git_root=project_root)

    assert not policy.requires_isolated_checkout()


def test_runtime_policy_uses_tmp_for_high_churn_runtime(tmp_path):
    project_root = tmp_path / "AgentOS" / "paper1"
    project_root.mkdir(parents=True)

    policy = RuntimePolicy(project_root=project_root, git_root=project_root)
    runtime_root = policy.runtime_root(goal_slug="3x10-readiness")

    assert runtime_root.is_absolute()
    assert str(runtime_root).startswith("/tmp/")
    assert "3x10-readiness" in runtime_root.name


def test_requires_owner_approval_at_3x10_or_larger():
    assert not requires_owner_approval(policy_count=3, task_count=7, paid=True)
    assert requires_owner_approval(policy_count=3, task_count=10, paid=True)
    assert requires_owner_approval(policy_count=3, task_count=20, paid=True)
    assert not requires_owner_approval(policy_count=3, task_count=10, paid=False)


def test_approval_policy_rejects_paid_3x10_without_owner_approval():
    policy = ApprovalPolicy(policy_count=3, task_count=10, paid=True, owner_approved=False)

    assert policy.must_stop_before_run()
    assert "owner approval" in policy.reason()


def test_artifact_policy_rejects_source_tests_run_data_and_tmp():
    policy = ArtifactPolicy(project_root=Path("/repo/paper1"))

    rejected = [
        Path("/repo/paper1/src/budgetflow/run_mini_swe_compare.py"),
        Path("/repo/paper1/tests/test_020_features.py"),
        Path("/repo/paper1/data/runs/postfix_029.jsonl"),
        Path("/repo/paper1/tmp/sympy__sympy/worktree/.git"),
    ]

    for path in rejected:
        assert not policy.is_allowed_for_autoresearch_checkpoint(path)


def test_artifact_policy_allows_autoresearch_config_and_docs():
    policy = ArtifactPolicy(project_root=Path("/repo/paper1"))

    allowed = [
        Path("/repo/paper1/.autoresearch/program.md"),
        Path("/repo/paper1/.autoresearch/agents/claude.md"),
        Path("/repo/paper1/.autoresearch/issues/issue-001-readonly-smoke.md"),
        Path("/repo/paper1/docs/autoresearch_workflow.md"),
        Path("/repo/paper1/docs/reports/autoresearch_readiness.md"),
    ]

    for path in allowed:
        assert policy.is_allowed_for_autoresearch_checkpoint(path)

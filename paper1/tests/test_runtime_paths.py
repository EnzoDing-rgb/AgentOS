"""Tests for budgetflow.runtime — path resolution, NFS detection, env/CLI precedence."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.runtime import (  # noqa: E402
    get_locks_dir,
    get_paper1_root,
    get_project_root,
    get_repo_cache_dir,
    get_runtime_root,
    get_runtime_root_source,
    get_trace_dir,
    get_worktree_root,
    is_nfs_or_banned,
    resolve_mini_swe_src,
    resolve_runtime_root,
    set_runtime_root,
)


class TestProjectRoot:
    def test_project_root_is_agentos(self):
        assert get_project_root().name == "AgentOS"

    def test_paper1_root_is_paper1(self):
        assert get_paper1_root().name == "paper1"

    def test_paper1_is_child_of_project(self):
        assert get_paper1_root().parent == get_project_root()

    def test_mini_swe_src_resolves_to_external(self):
        src = resolve_mini_swe_src()
        assert (src / "minisweagent").is_dir()
        # Not /Lishun unless no other option.
        assert not str(src).startswith("/Lishun") or not any(
            p.name == "external" for p in src.parents
        ), f"resolved to /Lishun but repo external/ exists: {src}"


class TestDefaultRuntimeRoot:
    def test_default_is_tmp_budgetflow(self):
        set_runtime_root(None)
        root = get_runtime_root()
        assert root == Path("/tmp/budgetflow-runtime")

    def test_default_source_is_default(self):
        set_runtime_root(None)
        assert get_runtime_root_source() == "default"


class TestEnvOverride:
    def test_env_var_sets_root(self, monkeypatch):
        monkeypatch.setenv("BUDGETFLOW_RUNTIME_ROOT", "/tmp/test-runtime-env")
        set_runtime_root(None)
        root, source = resolve_runtime_root()
        assert root == Path("/tmp/test-runtime-env")
        assert source == "env"

    def test_env_var_nfs_banned(self, monkeypatch):
        """resolve_runtime_root raises before touching fs for banned paths."""
        monkeypatch.setenv("BUDGETFLOW_RUNTIME_ROOT", "/Lishun/nonexistent/path")
        set_runtime_root(None)
        with pytest.raises(SystemExit):
            resolve_runtime_root()


class TestCliOverride:
    def test_set_runtime_root_overrides_env(self, monkeypatch):
        monkeypatch.setenv("BUDGETFLOW_RUNTIME_ROOT", "/tmp/env-path")
        set_runtime_root("/tmp/cli-path")
        root = get_runtime_root()
        assert root == Path("/tmp/cli-path")
        assert get_runtime_root_source() == "cli"
        set_runtime_root(None)

    def test_set_runtime_root_nfs_blocked(self):
        with pytest.raises(SystemExit):
            set_runtime_root("/Lishun/blocked/path")

    def test_set_runtime_root_nfs_allowed_mock_mkdir(self, monkeypatch):
        """allow_nfs=True bypasses ban; mock mkdir to avoid touching real fs."""
        monkeypatch.setattr(Path, "mkdir", lambda self, *a, **kw: None)
        try:
            set_runtime_root("/Lishun/simulated/path", allow_nfs=True)
            assert get_runtime_root() == Path("/Lishun/simulated/path")
        finally:
            set_runtime_root(None)


class TestWorktreeOverride:
    def test_runtime_worktree_default(self):
        set_runtime_root(None)
        wt = get_worktree_root()
        assert wt == Path("/tmp/budgetflow-runtime/worktrees")

    def test_worktree_root_deprecated_override(self):
        set_runtime_root(None)
        from budgetflow.local_harness import set_worktree_root as swr, get_worktree_root as gwr
        try:
            swr("/tmp/custom-worktrees")
            assert gwr() == Path("/tmp/custom-worktrees")
        finally:
            swr(None)


class TestNFSDetection:
    def test_lishun_prefix_is_nfs(self):
        assert is_nfs_or_banned("/Lishun/foo") is True
        assert is_nfs_or_banned("/Lishun") is True

    def test_tmp_is_not_nfs(self):
        assert is_nfs_or_banned("/tmp/foo") is False
        assert is_nfs_or_banned("/root/.dev/AgentOS") is False


class TestSubdirectories:
    def test_lock_dir_under_runtime(self):
        set_runtime_root(None)
        locks = get_locks_dir()
        assert locks == Path("/tmp/budgetflow-runtime/locks")
        assert locks.exists()

    def test_trace_dir_under_runtime(self):
        set_runtime_root(None)
        trace = get_trace_dir("sympy-123", "budgetflow_full")
        assert trace == Path("/tmp/budgetflow-runtime/traces/trace_sympy-123_budgetflow_full")
        assert trace.exists()

    def test_repo_cache_under_runtime(self):
        set_runtime_root(None)
        rc = get_repo_cache_dir()
        assert rc == Path("/tmp/budgetflow-runtime/repos")


class TestPersistentPathsUnaffected:
    """JSONL, checkpoint, heartbeat paths must stay in paper1/data/runs."""

    def test_runs_dir_not_in_runtime(self):
        set_runtime_root(None)
        root = get_runtime_root()
        runs = ROOT / "data" / "runs"
        try:
            root.relative_to(runs)
            assert False, "runtime root should not be under data/runs"
        except ValueError:
            pass


class TestRepoCacheIsolation:
    """repo_dir_for defaults to runtime cache, legacy only when opted in."""

    def test_repo_cache_uses_runtime_by_default(self, monkeypatch):
        """Even if legacy path exists, default goes to runtime repos."""
        monkeypatch.delenv("BUDGETFLOW_USE_LEGACY_REPO_CACHE", raising=False)
        set_runtime_root(None)
        # Runtime cache dir should be the primary target.
        expected = get_repo_cache_dir() / "sympy__sympy"
        from budgetflow.lite_tasks import LiteTaskRecord
        from budgetflow.local_harness import repo_dir_for
        task = LiteTaskRecord(
            instance_id="sympy__sympy-13480",
            repo="sympy/sympy",
            base_commit="abc",
            problem_statement="test",
            patch="",
            test_patch="",
            fail_to_pass=(),
            pass_to_pass=(),
            gold_files=(),
            workflow=None,
        )
        result = repo_dir_for(task)
        assert result == expected, f"expected {expected}, got {result}"

    def test_legacy_fallback_only_when_enabled(self, monkeypatch, tmp_path):
        """With BUDGETFLOW_USE_LEGACY_REPO_CACHE=1, legacy wins if exists."""
        monkeypatch.setenv("BUDGETFLOW_USE_LEGACY_REPO_CACHE", "1")
        set_runtime_root(None)
        # Redirect _LEGACY_REPO_CACHE to a temp dir so we don't touch real clones.
        import budgetflow.local_harness as lh
        monkeypatch.setattr(lh, "_LEGACY_REPO_CACHE", tmp_path / "legacy_cache", raising=False)
        monkeypatch.setattr(lh, "_LEGACY_REPO_CACHE_ALT", tmp_path / "legacy_alt", raising=False)
        from budgetflow.local_harness import repo_dir_for
        from budgetflow.lite_tasks import LiteTaskRecord
        legacy_dir = tmp_path / "legacy_cache" / "sympy__sympy"
        legacy_dir.mkdir(parents=True)
        task = LiteTaskRecord(
            instance_id="sympy__sympy-13480",
            repo="sympy/sympy",
            base_commit="abc",
            problem_statement="test",
            patch="",
            test_patch="",
            fail_to_pass=(),
            pass_to_pass=(),
            gold_files=(),
            workflow=None,
        )
        result = repo_dir_for(task)
        assert result == legacy_dir


def teardown_module():
    set_runtime_root(None)

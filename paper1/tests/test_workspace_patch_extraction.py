from __future__ import annotations

import subprocess
from pathlib import Path

from budgetflow.defaults import PAID_MAINLINE_STEP_LIMIT
from budgetflow.adapter import runner


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_workspace_patch_baselines_compat_then_collects_only_agent_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("old\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "base")

    (repo / "app.py").write_text("compat\nold\n")
    baseline = runner._capture_workspace_baseline(repo)

    assert baseline.changed_files == ("app.py",)
    assert subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=repo).returncode == 1

    (repo / "app.py").write_text("compat\nfixed\n")
    (repo / "patch.txt").write_text("this auxiliary file must not be scored\n")
    _git(repo, "add", "app.py")

    workspace_patch = runner._collect_workspace_patch(repo, baseline_ref=baseline.ref)

    assert workspace_patch.text is not None
    assert workspace_patch.source == "workspace_diff"
    assert workspace_patch.changed_files == ("app.py",)
    assert "+fixed" in workspace_patch.text
    assert "+compat" not in workspace_patch.text
    assert "patch.txt" not in workspace_patch.text


def test_workspace_patch_does_not_score_baseline_only_compat_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "compat.py").write_text("from collections import Mapping\n")
    _git(repo, "add", "compat.py")
    _git(repo, "commit", "-m", "base")

    (repo / "compat.py").write_text("from collections.abc import Mapping\n")
    baseline = runner._capture_workspace_baseline(repo)

    workspace_patch = runner._collect_workspace_patch(repo, baseline_ref=baseline.ref)

    assert baseline.changed_files == ("compat.py",)
    assert workspace_patch.text is None
    assert workspace_patch.source == "none"
    assert workspace_patch.changed_files == ()


def test_workspace_patch_collects_agent_commits_against_baseline_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("old\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "base")

    baseline = runner._capture_workspace_baseline(repo)

    (repo / "app.py").write_text("fixed\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "agent change")

    workspace_patch = runner._collect_workspace_patch(repo, baseline_ref=baseline.ref)

    assert workspace_patch.text is not None
    assert workspace_patch.source == "workspace_diff"
    assert "+fixed" in workspace_patch.text


def test_workspace_patch_cleans_setup_lock_binary_and_non_ascii_noise(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("old\n")
    (repo / "setup.py").write_text("old setup\n")
    (repo / "poetry.lock").write_text("old lock\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")

    baseline = runner._capture_workspace_baseline(repo)

    (repo / "app.py").write_text("fixed\n")
    (repo / "setup.py").write_text("new setup\n")
    (repo / "poetry.lock").write_text("new lock\n")
    (repo / "unicodé.py").write_text("noise\n")

    workspace_patch = runner._collect_workspace_patch(repo, baseline_ref=baseline.ref)

    assert workspace_patch.text is not None
    assert "diff --git a/app.py b/app.py" in workspace_patch.text
    assert "setup.py" not in workspace_patch.text
    assert "poetry.lock" not in workspace_patch.text
    assert "unicod" not in workspace_patch.text


def test_workspace_patch_handles_non_utf8_binary_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "blob.bin").write_bytes(b"\x00old\x8f\n")
    _git(repo, "add", "blob.bin")
    _git(repo, "commit", "-m", "base")

    baseline = runner._capture_workspace_baseline(repo)
    (repo / "blob.bin").write_bytes(b"\x00new\x8f\xff\n")

    workspace_patch = runner._collect_workspace_patch(repo, baseline_ref=baseline.ref)

    assert workspace_patch.text is None
    assert workspace_patch.source == "none"
    assert workspace_patch.changed_files == ("blob.bin",)
    assert workspace_patch.drop_reason


def test_workspace_patch_diff_decode_error_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("old\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "base")

    baseline = runner._capture_workspace_baseline(repo)
    (repo / "app.py").write_text("fixed\n")

    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        cmd = args[0]
        if (
            isinstance(cmd, list)
            and cmd[:4] == ["git", "diff", "--no-color", "--binary"]
            and kwargs.get("text") is True
            and kwargs.get("errors") != "replace"
        ):
            raise UnicodeDecodeError("utf-8", b"\x8f", 0, 1, "invalid start byte")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    workspace_patch = runner._collect_workspace_patch(repo, baseline_ref=baseline.ref)

    assert workspace_patch.text is not None
    assert "+fixed" in workspace_patch.text


def test_workspace_patch_rejects_patch_that_cannot_reverse_apply(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("old\n \n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "base")

    baseline = runner._capture_workspace_baseline(repo)
    (repo / "app.py").write_text("fixed\n \n")

    def corrupt_trailing_context(patch: str | None) -> str:
        assert patch is not None
        return patch.rstrip() + "\n"

    monkeypatch.setattr(runner, "clean_scoreable_patch", corrupt_trailing_context)

    workspace_patch = runner._collect_workspace_patch(repo, baseline_ref=baseline.ref)

    assert workspace_patch.text is None
    assert workspace_patch.source == "none"
    assert workspace_patch.changed_files == ("app.py",)


def test_scoreable_patch_prefers_workspace_diff_over_submission() -> None:
    workspace_patch = runner.WorkspacePatch(
        text="diff --git a/app.py b/app.py\n+workspace\n",
        source="workspace_diff",
        changed_files=("app.py",),
    )

    selected = runner._select_scoreable_patch(
        workspace_patch=workspace_patch,
        submitted_patch_text="diff --git a/app.py b/app.py\n+submitted\n",
    )

    assert selected.patch_text == workspace_patch.text
    assert selected.patch_source == "workspace_diff"
    assert selected.submitted_patch_text == "diff --git a/app.py b/app.py\n+submitted\n"


def test_scoreable_patch_does_not_fallback_to_submission() -> None:
    selected = runner._select_scoreable_patch(
        workspace_patch=runner.WorkspacePatch(text=None, source="none", changed_files=()),
        submitted_patch_text="diff --git a/app.py b/app.py\n+submitted\n",
    )

    assert selected.patch_text is None
    assert selected.patch_source == "none"
    assert selected.submitted_patch_text == "diff --git a/app.py b/app.py\n+submitted\n"


def test_runner_default_step_limit_uses_paid_mainline_cap() -> None:
    config = runner._load_agent_config()

    assert config["agent"]["step_limit"] == PAID_MAINLINE_STEP_LIMIT

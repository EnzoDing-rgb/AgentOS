from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from budgetflow import local_harness
from budgetflow.local_harness import build_pytest_node_ids, evaluate_local_harness


def test_build_pytest_node_ids_from_plain_test_names(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_one():\n    pass\n")

    node_ids, missing = build_pytest_node_ids(
        tmp_path,
        ("test_one",),
        ["tests/test_sample.py"],
    )

    assert node_ids == ["tests/test_sample.py::test_one"]
    assert missing == []


def test_build_pytest_node_ids_keeps_full_node_ids(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "class TestCase:\n"
        "    def test_one(self):\n"
        "        pass\n"
    )

    node_ids, missing = build_pytest_node_ids(
        tmp_path,
        ("tests/test_sample.py::TestCase::test_one",),
        ["tests/test_sample.py"],
    )

    assert node_ids == ["tests/test_sample.py::TestCase::test_one"]
    assert missing == []


def test_evaluate_local_harness_does_not_resolve_when_fail_to_pass_already_passed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = SimpleNamespace(
        instance_id="repo__already-green",
        repo="repo/project",
        base_commit="abc123",
        test_patch="diff --git a/tests/test_sample.py b/tests/test_sample.py\n",
        patch="",
        fail_to_pass=("tests/test_sample.py::test_regression",),
        pass_to_pass=("tests/test_sample.py::test_existing",),
    )

    monkeypatch.setattr(local_harness, "clone_or_checkout", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(local_harness, "repo_dir_for", lambda task: tmp_path)
    monkeypatch.setattr(local_harness, "test_paths_for", lambda task: ["tests/test_sample.py"])
    monkeypatch.setattr(local_harness, "apply_patch", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(local_harness, "run_pytest", lambda *args, **kwargs: (True, "passed"))

    result = evaluate_local_harness(task, "diff --git a/app.py b/app.py\n")

    assert result.fail_before is True
    assert result.fail_after is True
    assert result.pass_to_pass_passed is True
    assert result.harness_resolved is False


def test_evaluate_local_harness_runs_all_pass_to_pass_tests(tmp_path: Path, monkeypatch) -> None:
    task = SimpleNamespace(
        instance_id="repo__all-pass-to-pass",
        repo="repo/project",
        base_commit="abc123",
        test_patch="diff --git a/tests/test_sample.py b/tests/test_sample.py\n",
        patch="",
        fail_to_pass=("tests/test_sample.py::test_regression",),
        pass_to_pass=tuple(f"tests/test_sample.py::test_existing_{index}" for index in range(8)),
    )
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(local_harness, "clone_or_checkout", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(local_harness, "repo_dir_for", lambda task: tmp_path)
    monkeypatch.setattr(local_harness, "test_paths_for", lambda task: ["tests/test_sample.py"])
    monkeypatch.setattr(local_harness, "apply_patch", lambda *args, **kwargs: (True, "ok"))

    def fake_run_pytest(repo_dir, test_names, test_paths):
        calls.append(tuple(test_names))
        return (len(calls) != 1, "expected fail-before")

    monkeypatch.setattr(local_harness, "run_pytest", fake_run_pytest)

    result = evaluate_local_harness(task, "diff --git a/app.py b/app.py\n")

    assert result.harness_resolved is True
    assert calls[-1] == task.pass_to_pass

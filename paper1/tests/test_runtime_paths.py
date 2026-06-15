from __future__ import annotations

from pathlib import Path

import pytest

from budgetflow import runtime


def test_resolve_mini_swe_src_rejects_lishun_env(monkeypatch) -> None:
    monkeypatch.setenv("MINI_SWE_SRC", "/Lishun/archive/mini-swe-agent/src")

    with pytest.raises(SystemExit, match="/Lishun"):
        runtime.resolve_mini_swe_src()


def test_resolve_swebench_export_rejects_lishun_env(monkeypatch) -> None:
    monkeypatch.setenv("SWEBENCH_EXPORT_DIR", "/Lishun/archive/swebench_lite_export")

    with pytest.raises(SystemExit, match="/Lishun"):
        runtime.resolve_swebench_export_dir()


def test_repo_local_mini_swe_src_exists() -> None:
    src = runtime.resolve_mini_swe_src()

    assert src == runtime.get_project_root() / "external" / "mini-swe-agent" / "src"
    assert (src / "minisweagent").is_dir()


def test_repo_local_swebench_export_exists() -> None:
    export_dir = runtime.resolve_swebench_export_dir()

    assert export_dir == runtime.get_paper1_root() / "data" / "swebench_lite_export"
    assert export_dir is not None
    assert (export_dir / "test.jsonl").is_file()


def test_runtime_root_defaults_to_tmp(monkeypatch) -> None:
    monkeypatch.delenv("BUDGETFLOW_RUNTIME_ROOT", raising=False)
    runtime.set_runtime_root(None)

    root, source = runtime.resolve_runtime_root()

    assert source == "default"
    assert root == Path("/tmp/budgetflow-runtime")
    runtime.set_runtime_root(None)

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.tool_sandbox import ToolResult, execute_tool, parse_tool_action, tools_for_stage
from budgetflow.types import Stage


def test_read_file_and_grep(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pkg").mkdir()
    (repo / "pkg" / "mod.py").write_text("def broken():\n    return 1\n")
    result = execute_tool(repo, Stage.LOCALIZATION, "read_file", {"path": "pkg/mod.py"})
    assert result.ok, result.error
    assert "def broken" in result.output
    grep = execute_tool(repo, Stage.LOCALIZATION, "grep", {"pattern": "broken", "path": "pkg"})
    assert grep.ok
    assert "mod.py" in grep.output


def test_apply_edits_and_submit(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    apply = execute_tool(
        repo,
        Stage.REPAIR,
        "apply_edits",
        {"edits": [{"op": "replace", "file": "a.py", "old": "x = 1", "new": "x = 2"}]},
    )
    assert apply.ok, apply.error
    submit = execute_tool(repo, Stage.REPAIR, "submit_patch", {})
    assert submit.ok, submit.error
    assert "x = 2" in submit.output


def test_parse_tool_action() -> None:
    text = '```json\n{"action": "grep", "args": {"pattern": "foo"}}\n```'
    action, args, err = parse_tool_action(text)
    assert err is None
    assert action == "grep"
    assert args == {"pattern": "foo"}


def test_stage_tool_permissions() -> None:
    assert "apply_edits" not in tools_for_stage(Stage.LOCALIZATION)
    assert "apply_edits" in tools_for_stage(Stage.REPAIR)

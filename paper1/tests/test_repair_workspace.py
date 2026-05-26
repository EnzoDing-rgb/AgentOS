from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.repair_workspace import RepairEdit, apply_repair_edits, parse_repair_edits, realize_repair_edits


def test_parse_multi_op_edits() -> None:
    text = """```json
{"edits": [{"op": "replace", "file": "a.py", "old": "x = 1", "new": "x = 2"}]}
```"""
    edits, error = parse_repair_edits(text)
    assert error is None
    assert edits is not None
    assert edits[0].op == "replace"


def test_apply_replace_and_export(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "a.py"
    file_path.write_text("def foo():\n    x = 1\n    return x\n")
    edits = [RepairEdit(op="replace", file="a.py", old="x = 1", new="x = 2", anchor=None)]
    ok, error = apply_repair_edits(repo, edits)
    assert ok, error
    assert "x = 2" in file_path.read_text()


def test_anchor_replace_applies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "b.py"
    file_path.write_text("before\nTARGET = old\nafter\n")
    edits = [
        RepairEdit(
            op="anchor_replace",
            file="b.py",
            old="old",
            new="new",
            anchor="TARGET = old",
        )
    ]
    ok, error = apply_repair_edits(repo, edits)
    assert ok, error
    assert "TARGET = new" in file_path.read_text()


def test_line_replace_preserves_indent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "unitsystem.py"
    file_path.write_text("def foo(self):\n    if dim != addend_dim:\n        pass\n")
    edits = [
        RepairEdit(
            op="line_replace",
            file="unitsystem.py",
            old=None,
            new="if not self.get_dimension_system().equivalent_dims(dim, addend_dim):",
            anchor="    if dim != addend_dim:",
        )
    ]
    ok, error = apply_repair_edits(repo, edits)
    assert ok, error
    text = file_path.read_text()
    assert "equivalent_dims" in text
    assert "    if not self" in text


def test_line_replace_applies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "d.py"
    file_path.write_text("keep\nif dim != addend_dim:\n    raise ValueError('x')\n")
    edits = [
        RepairEdit(
            op="line_replace",
            file="d.py",
            old=None,
            new="                if not self.get_dimension_system().equivalent_dims(dim, addend_dim):",
            anchor="if dim != addend_dim:",
        )
    ]
    ok, error = apply_repair_edits(repo, edits)
    assert ok, error
    assert "equivalent_dims" in file_path.read_text()


def test_realize_repair_edits_roundtrip(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True, capture_output=True)
    (repo / "c.py").write_text("value = 1\n")
    subprocess.run(["git", "add", "c.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    text = """{"edits": [{"op": "replace", "file": "c.py", "old": "value = 1", "new": "value = 9"}]}"""
    patch, error = realize_repair_edits(repo, text)
    assert error is None
    assert patch is not None
    assert "value = 9" in patch

from __future__ import annotations

from pathlib import Path

from budgetflow.local_harness import build_pytest_node_ids


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

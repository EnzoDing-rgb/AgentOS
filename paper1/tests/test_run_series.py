from pathlib import Path

from budgetflow.run_series import allocate_series_stem, list_series_stems


def test_allocate_series_stem_empty(tmp_path: Path) -> None:
    assert allocate_series_stem(tmp_path, "policy_5x7") == "policy_5x7-0"


def test_allocate_series_stem_increments(tmp_path: Path) -> None:
    (tmp_path / "policy_5x7-0.jsonl").write_text("")
    (tmp_path / "policy_5x7-2.summary.log").write_text("")
    assert allocate_series_stem(tmp_path, "policy_5x7") == "policy_5x7-3"
    assert list_series_stems(tmp_path, "policy_5x7") == ["policy_5x7-0", "policy_5x7-2"]

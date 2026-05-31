from pathlib import Path

import pytest

from budgetflow.run_series import (
    allocate_series_stem,
    default_series_base,
    latest_series_stem,
    list_series_stems,
    resolve_compare_stem,
    series_run_complete,
)


def test_allocate_series_stem_empty(tmp_path: Path) -> None:
    assert allocate_series_stem(tmp_path, "policy_5x7") == "policy_5x7-0"


def test_allocate_series_stem_increments(tmp_path: Path) -> None:
    (tmp_path / "policy_5x7-0.jsonl").write_text("")
    (tmp_path / "policy_5x7-2.summary.log").write_text("")
    assert allocate_series_stem(tmp_path, "policy_5x7") == "policy_5x7-3"
    assert list_series_stems(tmp_path, "policy_5x7") == ["policy_5x7-0", "policy_5x7-2"]


def test_latest_series_stem(tmp_path: Path) -> None:
    (tmp_path / "policy_15x7-8.jsonl").write_text("")
    (tmp_path / "policy_15x7-9.jsonl").write_text("")
    assert latest_series_stem(tmp_path, "policy_15x7") == "policy_15x7-9"


def test_default_series_base() -> None:
    assert default_series_base(tasks_n=15, strategies_n=7, task_set="medium") == "policy_15x7"
    assert default_series_base(tasks_n=5, strategies_n=7, task_set="easy") == "compare_5x7"


def test_resolve_new_auto_increments(tmp_path: Path) -> None:
    (tmp_path / "policy_15x7-8.jsonl").write_text('{"strategy":"x","instance_id":"a"}\n')
    stem, mode = resolve_compare_stem(
        tmp_path, series="policy_15x7", resume=False, total_runs=105, explicit_stem=None
    )
    assert stem == "policy_15x7-9"
    assert mode == "new"


def test_resolve_resume_latest(tmp_path: Path) -> None:
    (tmp_path / "policy_15x7-8.jsonl").write_text('{"strategy":"x","instance_id":"a"}\n')
    (tmp_path / "policy_15x7-9.jsonl").write_text('{"strategy":"x","instance_id":"a"}\n')
    stem, mode = resolve_compare_stem(
        tmp_path, series="policy_15x7", resume=True, total_runs=105, explicit_stem=None
    )
    assert stem == "policy_15x7-9"
    assert mode == "resume"


def test_resolve_refuses_overwrite_explicit(tmp_path: Path) -> None:
    (tmp_path / "policy_15x7-8.jsonl").write_text("")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        resolve_compare_stem(
            tmp_path,
            series="policy_15x7",
            resume=False,
            total_runs=105,
            explicit_stem="policy_15x7-8",
        )


def test_resume_complete_latest_errors(tmp_path: Path) -> None:
    path = tmp_path / "policy_15x7-8.jsonl"
    lines = ['{"strategy":"s","instance_id":"t%d"}' % i for i in range(3)]
    path.write_text("\n".join(lines) + "\n")
    assert series_run_complete(tmp_path, "policy_15x7-8", total_runs=3)
    with pytest.raises(SystemExit, match="complete"):
        resolve_compare_stem(tmp_path, series="policy_15x7", resume=True, total_runs=3, explicit_stem=None)

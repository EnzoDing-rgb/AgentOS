from __future__ import annotations

import pytest

from budgetflow.run_series import resolve_compare_stem


def test_resume_explicit_stem_blocks_completed_run(tmp_path) -> None:
    (tmp_path / "done.jsonl").write_text("{}\n{}\n")

    with pytest.raises(SystemExit, match="already complete"):
        resolve_compare_stem(
            tmp_path,
            series="compare_1x2",
            resume=True,
            total_runs=2,
            explicit_stem="done",
        )


def test_resume_explicit_stem_requires_existing_jsonl(tmp_path) -> None:
    with pytest.raises(SystemExit, match="does not exist"):
        resolve_compare_stem(
            tmp_path,
            series="compare_1x2",
            resume=True,
            total_runs=2,
            explicit_stem="missing",
        )


def test_resume_explicit_stem_allows_incomplete_run(tmp_path) -> None:
    (tmp_path / "partial.jsonl").write_text("{}\n")

    stem, mode = resolve_compare_stem(
        tmp_path,
        series="compare_1x2",
        resume=True,
        total_runs=2,
        explicit_stem="partial",
    )

    assert stem == "partial"
    assert mode == "resume"

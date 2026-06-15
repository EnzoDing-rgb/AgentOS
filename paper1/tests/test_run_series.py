from __future__ import annotations

import pytest

from budgetflow.run_series import (
    allocate_series_stem,
    detect_sibling_stems,
    list_series_stems,
    release_run_identity,
    resolve_compare_stem,
    sibling_stems_exist,
)


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


# ── Sibling detection ──────────────────────────────────────────────────


def test_sibling_stems_detected(tmp_path) -> None:
    (tmp_path / "compare_1x2-0.jsonl").write_text("")
    (tmp_path / "compare_1x2-1.jsonl").write_text("")
    (tmp_path / "compare_1x2-2.jsonl").write_text("")

    assert sibling_stems_exist(tmp_path, "compare_1x2") is True
    siblings = detect_sibling_stems(tmp_path, "compare_1x2")
    assert len(siblings) == 3
    assert siblings == ["compare_1x2-0", "compare_1x2-1", "compare_1x2-2"]


def test_single_stem_not_sibling(tmp_path) -> None:
    (tmp_path / "compare_1x2-0.jsonl").write_text("")

    assert sibling_stems_exist(tmp_path, "compare_1x2") is False
    assert detect_sibling_stems(tmp_path, "compare_1x2") == []


def test_no_sibling_for_different_series(tmp_path) -> None:
    (tmp_path / "compare_1x2-0.jsonl").write_text("")
    (tmp_path / "policy_5x5-0.jsonl").write_text("")

    assert sibling_stems_exist(tmp_path, "compare_1x2") is False
    assert sibling_stems_exist(tmp_path, "policy_5x5") is False


def test_sibling_detection_blocks_new_run(tmp_path) -> None:
    (tmp_path / "compare_1x2-0.jsonl").write_text("")
    (tmp_path / "compare_1x2-1.jsonl").write_text("")

    with pytest.raises(SystemExit, match="sibling stems detected"):
        resolve_compare_stem(
            tmp_path,
            series="compare_1x2",
            resume=False,
            total_runs=2,
        )


def test_repair_mode_allows_sibling_series(tmp_path) -> None:
    (tmp_path / "compare_1x2-0.jsonl").write_text("")
    (tmp_path / "compare_1x2-1.jsonl").write_text("")

    stem, mode = resolve_compare_stem(
        tmp_path,
        series="compare_1x2",
        resume=False,
        total_runs=2,
        repair=True,
    )

    assert stem == "compare_1x2-2"
    assert mode == "new"


def test_allocate_stem_writes_lock(tmp_path) -> None:
    stem = allocate_series_stem(tmp_path, "compare_1x2")
    assert stem == "compare_1x2-0"
    lock = tmp_path / f"{stem}.lock"
    assert lock.is_file()
    assert int(lock.read_text()) > 0  # PID


def test_release_run_identity_removes_own_lock(tmp_path) -> None:
    stem = allocate_series_stem(tmp_path, "compare_1x2")
    lock = tmp_path / f"{stem}.lock"

    release_run_identity(stem, tmp_path)

    assert not lock.exists()


def test_allocate_stem_increments_past_existing(tmp_path) -> None:
    (tmp_path / "compare_1x2-0.jsonl").write_text("")
    (tmp_path / "compare_1x2-1.jsonl").write_text("")

    stem = allocate_series_stem(tmp_path, "compare_1x2")
    assert stem == "compare_1x2-2"


def test_list_series_stems_sorted(tmp_path) -> None:
    (tmp_path / "compare_1x2-5.jsonl").write_text("")
    (tmp_path / "compare_1x2-0.jsonl").write_text("")
    (tmp_path / "compare_1x2-3.jsonl").write_text("")

    stems = list_series_stems(tmp_path, "compare_1x2")
    assert stems == ["compare_1x2-0", "compare_1x2-3", "compare_1x2-5"]

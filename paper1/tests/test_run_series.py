from __future__ import annotations

import json

import pytest

from budgetflow.run_series import (
    allocate_series_stem,
    completed_scoreable_keys,
    detect_sibling_stems,
    latest_run_contract,
    list_series_stems,
    release_run_identity,
    resolve_compare_stem,
    resolve_run_identity,
    scoreable_run_contracts,
    series_run_complete,
    sibling_stems_exist,
    validate_resume_contract,
)
from budgetflow.compare_checkpoint import CompareCheckpointStore


def test_resume_explicit_stem_blocks_completed_run(tmp_path) -> None:
    rows = [
        {"strategy": "bare_t2_baseline", "instance_id": "task-a", "score_status": "pass"},
        {"strategy": "bare_t2_baseline", "instance_id": "task-b", "score_status": "true_fail"},
    ]
    (tmp_path / "done.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")

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


def test_resume_without_prior_run_does_not_allocate_lock(tmp_path) -> None:
    with pytest.raises(SystemExit, match="no prior runs"):
        resolve_compare_stem(
            tmp_path,
            series="mainline",
            resume=True,
            total_runs=2,
        )

    assert list(tmp_path.glob("*.lock")) == []


def test_resume_explicit_stem_allows_incomplete_run(tmp_path) -> None:
    row = {"strategy": "bare_t2_baseline", "instance_id": "task-a", "score_status": "pass"}
    (tmp_path / "partial.jsonl").write_text(json.dumps(row) + "\n")

    stem, mode = resolve_compare_stem(
        tmp_path,
        series="compare_1x2",
        resume=True,
        total_runs=2,
        explicit_stem="partial",
    )

    assert stem == "partial"
    assert mode == "resume"


def test_retired_series_blocks_new_run(tmp_path) -> None:
    with pytest.raises(SystemExit, match="refusing retired run series"):
        resolve_run_identity(
            tmp_path,
            tasks_n=30,
            strategies_n=6,
            task_set="easy",
            resume=False,
            total_runs=180,
            explicit_series="mainline_6x30_v1",
        )


def test_retired_series_blocks_explicit_stem_resume(tmp_path) -> None:
    (tmp_path / "mainline_6x30_v1-0.jsonl").write_text("")

    with pytest.raises(SystemExit, match="forensic-only"):
        resolve_run_identity(
            tmp_path,
            tasks_n=30,
            strategies_n=6,
            task_set="easy",
            resume=True,
            total_runs=180,
            explicit_series="mainline_6x30_v1",
            explicit_stem="mainline_6x30_v1-0",
        )


def test_series_run_complete_counts_unique_scoreable_pairs_only(tmp_path) -> None:
    path = tmp_path / "mainline-0.jsonl"
    rows = [
        {"strategy": "bare_t2_baseline", "instance_id": "task-a", "score_status": "pass"},
        {"strategy": "bare_t2_baseline", "instance_id": "task-a", "score_status": "pass"},
        {"strategy": "bare_t2_baseline", "instance_id": "task-b", "score_status": "abort"},
        {"strategy": "bare_t2_baseline", "instance_id": "task-c", "score_status": "true_fail"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    assert completed_scoreable_keys(path) == {
        ("bare_t2_baseline", "task-a"),
        ("bare_t2_baseline", "task-c"),
    }
    assert series_run_complete(tmp_path, "mainline-0", total_runs=2)
    assert not series_run_complete(tmp_path, "mainline-0", total_runs=3)


def test_series_run_complete_uses_expected_pairs_not_count_only(tmp_path) -> None:
    path = tmp_path / "mainline-0.jsonl"
    rows = [
        {"strategy": "bare_t2_baseline", "instance_id": "task-a", "score_status": "pass"},
        {"strategy": "bare_t2_baseline", "instance_id": "task-b", "score_status": "true_fail"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    assert not series_run_complete(
        tmp_path,
        "mainline-0",
        total_runs=2,
        expected_keys={
            ("bare_t2_baseline", "task-a"),
            ("bare_t2_baseline", "task-c"),
        },
    )


def test_resume_explicit_stem_allows_same_count_but_different_expected_pairs(tmp_path) -> None:
    path = tmp_path / "mainline-0.jsonl"
    rows = [
        {"strategy": "bare_t2_baseline", "instance_id": "task-a", "score_status": "pass"},
        {"strategy": "bare_t2_baseline", "instance_id": "task-b", "score_status": "true_fail"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    stem, mode = resolve_compare_stem(
        tmp_path,
        series="mainline",
        resume=True,
        total_runs=2,
        explicit_stem="mainline-0",
        expected_keys={
            ("bare_t2_baseline", "task-a"),
            ("bare_t2_baseline", "task-c"),
        },
    )

    assert stem == "mainline-0"
    assert mode == "resume"


def test_staged_resume_expands_expected_pairs_without_false_completion(tmp_path) -> None:
    strategies = [
        "bare_t2_baseline",
        "bare_t3_baseline",
        "enterprise_router_baseline",
        "budgetflow_same_enterprise_router",
        "budgetflow_task_level",
        "budgetflow_segment",
    ]
    tasks = [f"task-{index:02d}" for index in range(30)]

    def keys(first_n: int) -> set[tuple[str, str]]:
        return {(strategy, task) for strategy in strategies for task in tasks[:first_n]}

    def append_completed(first_n: int) -> None:
        rows = [
            json.dumps({"strategy": strategy, "instance_id": task, "score_status": "pass"})
            for strategy, task in sorted(keys(first_n))
        ]
        (tmp_path / "mainline_6x30_v1-0.jsonl").write_text("\n".join(rows) + "\n")

    append_completed(10)

    with pytest.raises(SystemExit, match="already complete"):
        resolve_compare_stem(
            tmp_path,
            series="mainline_6x30_v1",
            resume=True,
            total_runs=60,
            explicit_stem="mainline_6x30_v1-0",
            expected_keys=keys(10),
        )

    stem, mode = resolve_compare_stem(
        tmp_path,
        series="mainline_6x30_v1",
        resume=True,
        total_runs=120,
        explicit_stem="mainline_6x30_v1-0",
        expected_keys=keys(20),
    )
    assert (stem, mode) == ("mainline_6x30_v1-0", "resume")

    append_completed(20)
    stem, mode = resolve_compare_stem(
        tmp_path,
        series="mainline_6x30_v1",
        resume=True,
        total_runs=180,
        explicit_stem="mainline_6x30_v1-0",
        expected_keys=keys(30),
    )
    assert (stem, mode) == ("mainline_6x30_v1-0", "resume")

    append_completed(30)
    with pytest.raises(SystemExit, match="already complete"):
        resolve_compare_stem(
            tmp_path,
            series="mainline_6x30_v1",
            resume=True,
            total_runs=180,
            explicit_stem="mainline_6x30_v1-0",
            expected_keys=keys(30),
        )


def test_resume_contract_allows_same_budget_catalog_and_value_provenance(tmp_path) -> None:
    path = tmp_path / "mainline_6x30_v1-0.jsonl"
    contract = {
        "budget_mode": "shared_batch_hard_budget",
        "batch_budget_cap": 2.999,
        "budget_plan_hard_cap_usd": 2.999,
        "budget_plan_generation_mode": "frozen_plan_cap_sum",
        "budget_plan_task_ids": ("task-a", "task-b"),
        "budget_plan_strategy_names": ("bare_t2_baseline", "budgetflow_segment"),
        "catalog_revision": "default-2026-06-10",
        "catalog_path": "/repo/docs/config/model_tiers.default.json",
        "value_profile": "manual_value",
        "value_source_class": "pre_registered_manual",
        "value_matrix_artifact": "docs/reports/value_matrix.json",
    }
    row = {
        "strategy": "budgetflow_segment",
        "instance_id": "task-a",
        "score_status": "pass",
        "budget_mode": contract["budget_mode"],
        "batch_budget_cap": contract["batch_budget_cap"],
        "budget_plan": {
            "hard_cap_usd": contract["budget_plan_hard_cap_usd"],
            "generation_mode": contract["budget_plan_generation_mode"],
            "task_ids": list(contract["budget_plan_task_ids"]),
            "strategy_names": list(contract["budget_plan_strategy_names"]),
        },
        "catalog": {
            "catalog_revision": contract["catalog_revision"],
            "catalog_path": contract["catalog_path"],
        },
        "task_value_profile": contract["value_profile"],
        "task_value_source_class": contract["value_source_class"],
        "value_matrix_artifact": contract["value_matrix_artifact"],
    }
    path.write_text(json.dumps(row) + "\n")

    assert latest_run_contract(path) == contract
    assert scoreable_run_contracts(path) == [contract]
    validate_resume_contract(path, expected_contract=contract)


def test_resume_contract_blocks_missing_or_mismatched_provenance(tmp_path) -> None:
    path = tmp_path / "mainline_6x30_v1-0.jsonl"
    path.write_text(json.dumps({
        "strategy": "budgetflow_segment",
        "instance_id": "task-a",
        "score_status": "pass",
        "budget_mode": "shared_batch_hard_budget",
    }) + "\n")

    with pytest.raises(SystemExit, match="resume contract mismatch"):
        validate_resume_contract(
            path,
            expected_contract={
                "budget_mode": "shared_batch_hard_budget",
                "catalog_revision": "default-2026-06-10",
                "value_source_class": "pre_registered_manual",
            },
        )


def test_resume_contract_checks_all_scoreable_rows_not_only_latest(tmp_path) -> None:
    path = tmp_path / "mainline_6x30_v1-0.jsonl"
    good_contract = {
        "budget_mode": "shared_batch_hard_budget",
        "batch_budget_cap": 2.999,
        "budget_plan_hard_cap_usd": 2.999,
        "budget_plan_generation_mode": "frozen_plan_cap_sum",
        "budget_plan_task_ids": ("task-a", "task-b"),
        "budget_plan_strategy_names": ("bare_t2_baseline", "budgetflow_segment"),
        "catalog_revision": "default-2026-06-10",
        "catalog_path": "/repo/docs/config/model_tiers.default.json",
        "value_profile": "manual_value",
        "value_source_class": "pre_registered_manual",
        "value_matrix_artifact": "docs/reports/value_matrix.json",
    }

    def row(task_id: str, *, cap: float) -> dict:
        return {
            "strategy": "budgetflow_segment",
            "instance_id": task_id,
            "score_status": "pass",
            "budget_mode": good_contract["budget_mode"],
            "batch_budget_cap": cap,
            "budget_plan": {
                "hard_cap_usd": good_contract["budget_plan_hard_cap_usd"],
                "generation_mode": good_contract["budget_plan_generation_mode"],
                "task_ids": list(good_contract["budget_plan_task_ids"]),
                "strategy_names": list(good_contract["budget_plan_strategy_names"]),
            },
            "catalog": {
                "catalog_revision": good_contract["catalog_revision"],
                "catalog_path": good_contract["catalog_path"],
            },
            "task_value_profile": good_contract["value_profile"],
            "task_value_source_class": good_contract["value_source_class"],
            "value_matrix_artifact": good_contract["value_matrix_artifact"],
        }

    path.write_text(
        json.dumps(row("task-a", cap=0.06)) + "\n"
        + json.dumps(row("task-b", cap=2.999)) + "\n"
    )

    assert latest_run_contract(path) == good_contract
    with pytest.raises(SystemExit, match=r"row1:batch_budget_cap"):
        validate_resume_contract(path, expected_contract=good_contract)


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


def test_checkpoint_resume_updates_total_runs_when_task_set_expands(tmp_path) -> None:
    path = tmp_path / "mainline_6x30_v1-0.checkpoint.json"
    checkpoint = CompareCheckpointStore(path, stem="mainline_6x30_v1-0", total_runs=120)
    checkpoint.mark_task_done("bare_t2_baseline", "task-a", batch_spent=0.01, batch_cap=1.0)

    resumed = CompareCheckpointStore(path, stem="mainline_6x30_v1-0", total_runs=180)
    resumed.mark_task_done("bare_t2_baseline", "task-b", batch_spent=0.02, batch_cap=1.0)

    assert resumed.total_runs == 180
    assert '"total_runs": 180' in path.read_text()


def test_checkpoint_total_runs_floors_to_completed_pair_count(tmp_path) -> None:
    path = tmp_path / "mainline_6x30_v1-0.checkpoint.json"
    path.write_text('{"stem":"mainline_6x30_v1-0","total_runs":1,"strategies":{}}\n')

    resumed = CompareCheckpointStore(
        path,
        stem="mainline_6x30_v1-0",
        total_runs=2,
        completed_floor=5,
    )
    resumed.save()

    assert resumed.total_runs == 5
    assert '"total_runs": 5' in path.read_text()

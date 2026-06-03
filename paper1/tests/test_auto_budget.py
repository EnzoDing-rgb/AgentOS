from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from budgetflow.auto_budget import (
    _HISTORICAL_PRIOR,
    AutoBudgetEstimator,
    AutoBudgetMemory,
    BudgetEstimate,
    _classify_cap_sufficiency,
)
from budgetflow.lite_tasks import LiteTaskRecord
from budgetflow.loop import WorkflowSpec


def _make_task(
    instance_id="sympy__sympy-14774",
    patch="line1\nline2\nline3",
    f2p=("test_a",),
    p2p=("test_x",),
    repo="sympy/sympy",
) -> LiteTaskRecord:
    return LiteTaskRecord(
        instance_id=instance_id,
        repo=repo,
        base_commit="abc123",
        problem_statement="fix thing",
        patch=patch,
        test_patch="test patch",
        fail_to_pass=f2p,
        pass_to_pass=p2p,
        gold_files=("foo.py",),
        workflow=WorkflowSpec(workflow_id="test", steps=[]),
    )


class TestAutoBudgetEstimator:
    def test_exact_history_match_high_confidence(self):
        est = AutoBudgetEstimator()
        task = _make_task("sympy__sympy-14774")
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        assert result.instance_id == "sympy__sympy-14774"
        assert result.source == "history_exact"
        assert result.confidence == "high"  # 7/7 resolved
        assert result.estimated_cost == 0.01
        assert result.cap == 0.05  # 0.01 * 1.5 = 0.015, clamped to min 0.05

    def test_exact_history_match_medium_confidence(self):
        est = AutoBudgetEstimator()
        task = _make_task("sympy__sympy-16988")
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        assert result.source == "history_exact"
        assert result.confidence == "medium"  # 3/8 resolved
        assert result.estimated_cost == 0.70
        assert result.cap == pytest.approx(1.05)  # 0.70 * 1.5 = 1.05, below max 10.0

    def test_exact_history_clamps_to_min(self):
        est = AutoBudgetEstimator()
        task = _make_task("sympy__sympy-14774")
        result = est.estimate(task, scale=1.0, min_cap=0.10, max_cap=10.0)
        assert result.cap == 0.10  # 0.01 * 1.0 = 0.01 < 0.10

    def test_exact_history_clamps_to_max(self):
        est = AutoBudgetEstimator()
        task = _make_task("sympy__sympy-16988")
        result = est.estimate(task, scale=20.0, min_cap=0.05, max_cap=10.0)
        assert result.cap == 10.0  # 0.70 * 20 = 14.0 > 10.0

    def test_fallback_easy_task(self):
        est = AutoBudgetEstimator()
        task = _make_task(
            "django__django-12113",
            patch="line1\nline2",  # 2 lines
            f2p=("test_a",),  # 1 f2p
            p2p=(),  # 0 p2p
            repo="django/django",
        )
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        assert result.source == "global_fallback"
        assert result.confidence == "low"
        # difficulty_score = 2 + 1*2 = 4 → easy, base=0.20
        # django repo floor = 1.00 → estimated_cost = max(0.20, 1.00) = 1.00
        assert result.estimated_cost == 1.00
        # cap = max(1.00, 0.05, 1.00*1.5=1.50) = 1.50
        assert result.cap == 1.50
        assert result.features["bucket"] == "easy"

    def test_fallback_medium_task(self):
        est = AutoBudgetEstimator()
        task = _make_task(
            "django__django-12497",
            patch="\n".join("x" for _ in range(20)),  # 20 lines
            f2p=tuple(f"t{n}" for n in range(5)),  # 5 f2p
            p2p=(),
            repo="django/django",
        )
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        assert result.source == "global_fallback"
        # difficulty_score = 20 + 5*2 = 30 → medium
        # estimated_cost = max(0.50, 1.00) = 1.00
        assert result.estimated_cost == 1.00
        # cap = max(1.00, 0.05, 1.00*1.5=1.50) = 1.50
        assert result.cap == 1.50
        assert result.features["bucket"] == "medium"

    def test_fallback_hard_task(self):
        est = AutoBudgetEstimator()
        task = _make_task(
            "some__hard-task",
            patch="\n".join("x" for _ in range(40)),  # 40 lines
            f2p=tuple(f"t{n}" for n in range(12)),  # 12 f2p
            p2p=tuple(f"p{n}" for n in range(50)),
            repo="some/repo",
        )
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        assert result.source == "global_fallback"
        # difficulty_score = 40 + 12*2 = 64 → hard (>=38)
        assert result.estimated_cost == 1.50
        assert result.cap == 2.25
        assert result.features["bucket"] == "hard"

    def test_fallback_clamps_to_min(self):
        est = AutoBudgetEstimator()
        task = _make_task("new__repo-task", patch="line1", f2p=("t1",))
        result = est.estimate(task, scale=1.0, min_cap=0.50, max_cap=10.0)
        assert result.source == "global_fallback"
        # easy bucket: base=0.20, no repo floor
        # cap = max(0, 0.50, 0.20*1.0=0.20) = 0.50
        assert result.cap == 0.50

    def test_features_recorded(self):
        est = AutoBudgetEstimator()
        task = _make_task("sympy__sympy-14774")
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        assert "patch_lines" in result.features
        assert "f2p_count" in result.features
        assert "p2p_count" in result.features
        assert "resolved_ratio" in result.features
        assert result.features["resolved_ratio"] == 1.0

    def test_custom_prior(self):
        custom = {"my__task-1": {"median_cost": 0.50, "median_turns": 20, "resolved": 5, "total": 5}}
        est = AutoBudgetEstimator(prior=custom)
        task = _make_task("my__task-1")
        result = est.estimate(task, scale=1.2, min_cap=0.05, max_cap=10.0)
        assert result.estimated_cost == 0.50
        assert result.cap == 0.60
        assert result.confidence == "high"

    def test_from_history_file(self):
        records = [
            {"instance_id": "sympy__sympy-14774", "task_cost": 0.03},
            {"instance_id": "sympy__sympy-14774", "task_cost": 0.05},
            {"instance_id": "sympy__sympy-14774", "task_cost": 0.04},  # median=0.04
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
            path = Path(f.name)
        try:
            est = AutoBudgetEstimator.from_history(path)
            task = _make_task("sympy__sympy-14774")
            result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
            assert result.estimated_cost == 0.04  # median of [0.03, 0.04, 0.05]
        finally:
            path.unlink()

    def test_from_history_file_falls_back_to_embedded(self):
        est = AutoBudgetEstimator.from_history(Path("/nonexistent/file.jsonl"))
        task = _make_task("sympy__sympy-14774")
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        assert result.estimated_cost == 0.01  # embedded prior

    def test_default_scale_and_min_cap(self):
        """v1 defaults: scale=1.5, min_cap=0.05."""
        est = AutoBudgetEstimator()
        task = _make_task("sympy__sympy-14774")
        result = est.estimate(task)  # default params
        # cap = max(0, 0.05, 0.01*1.5=0.015) = 0.05
        assert result.cap == 0.05

    def test_django_repo_floor(self):
        """Django tasks get repo floor of $1.00 estimated_cost."""
        est = AutoBudgetEstimator()
        task = _make_task("django__django-new", patch="line1", f2p=("t1",), repo="django/django")
        result = est.estimate(task, scale=2.5, min_cap=0.05, max_cap=10.0)
        assert result.source == "global_fallback"
        # easy bucket base=0.20, repo floor=1.00 → estimated_cost=1.00
        assert result.estimated_cost == 1.00
        # cap = max(1.00, 0.05, 1.00*2.5=2.50) = 2.50
        assert result.cap == 2.50

    def test_sympy_no_repo_floor(self):
        """SymPy has no repo floor."""
        est = AutoBudgetEstimator()
        task = _make_task("sympy__sympy-new", patch="line1", f2p=("t1",), repo="sympy/sympy")
        result = est.estimate(task, scale=2.5, min_cap=0.05, max_cap=10.0)
        assert result.source == "global_fallback"
        assert result.estimated_cost == 0.20
        assert result.cap == 0.50  # max(0, 0.05, 0.20*2.5=0.50) = 0.50


class TestAutoBudgetMemory:
    def test_write_and_read(self):
        mem = AutoBudgetMemory()
        assert len(mem) == 0
        mem.write_record({"instance_id": "test__task-1", "total_cost": 0.10, "cap_was_sufficient": "sufficient"})
        assert len(mem) == 1
        assert mem.records[0]["instance_id"] == "test__task-1"
        assert "timestamp" in mem.records[0]
        assert mem.records[0]["estimator_version"] == "v1"

    def test_build_record(self):
        rec = AutoBudgetMemory.build_record(
            instance_id="sympy__sympy-14774",
            repo="sympy/sympy",
            strategy="budget_only_tight",
            routing="budget_only",
            resolved=True,
            harness_resolved=True,
            failure_class="",
            forensic_primary_axis="pass",
            total_cost=0.12,
            estimated_task_cap=0.20,
            estimated_task_cost=0.01,
            patch_extracted=True,
            agent_gold_edited=True,
            llm_turns=9,
            patch_lines=12,
            f2p_count=1,
            p2p_count=114,
            problem_length=500,
            gold_file_count=1,
            exit_status="BudgetFlowBudgetError",
            detail="harness pass",
        )
        assert rec["cap_was_sufficient"] == "sufficient"
        assert rec["total_cost"] == 0.12
        assert rec["repo"] == "sympy/sympy"

    def test_memory_exact_beats_fallback(self):
        mem = AutoBudgetMemory()
        mem.write_record(AutoBudgetMemory.build_record(
            instance_id="django__django-12113", repo="django/django",
            strategy="budget_only_tight", routing="budget_only",
            resolved=True, harness_resolved=True,
            failure_class="", forensic_primary_axis="pass",
            total_cost=0.35, estimated_task_cap=1.00, estimated_task_cost=0.50,
            patch_extracted=True, agent_gold_edited=True, llm_turns=12,
            patch_lines=10, f2p_count=1, p2p_count=0,
            problem_length=500, gold_file_count=1,
        ))
        est = AutoBudgetEstimator(memory=mem)
        task = _make_task("django__django-12113", patch="line1\nline2", f2p=("t1",), repo="django/django")
        result = est.estimate(task, scale=2.5, min_cap=0.05, max_cap=10.0)
        # Memory hit: median=0.35
        assert result.source == "memory_exact"
        assert result.estimated_cost == 0.35

    def test_underbudget_memory_inflates_cap(self):
        mem = AutoBudgetMemory()
        mem.write_record(AutoBudgetMemory.build_record(
            instance_id="test__task-1", repo="test/repo",
            strategy="budget_only_tight", routing="budget_only",
            resolved=False, harness_resolved=False,
            failure_class="budget_fail", forensic_primary_axis="budget",
            total_cost=0.30, estimated_task_cap=0.30, estimated_task_cost=0.20,
            patch_extracted=True, agent_gold_edited=True, llm_turns=14,
            patch_lines=10, f2p_count=1, p2p_count=0,
            problem_length=500, gold_file_count=1,
            exit_status="BudgetFlowBudgetError",
            detail="patch extracted but budget exhausted",
        ))
        est = AutoBudgetEstimator(memory=mem)
        task = _make_task("test__task-1", repo="test/repo")
        result = est.estimate(task, scale=2.5, min_cap=0.05, max_cap=10.0)
        assert result.source == "memory_exact"
        # underbudget cost=0.30 → inflated to max(0.30, 0.30*1.5=0.45) = 0.45
        assert result.estimated_cost == pytest.approx(0.45)

    def test_harness_failure_excluded(self):
        mem = AutoBudgetMemory()
        mem.write_record(AutoBudgetMemory.build_record(
            instance_id="sympy__sympy-14774", repo="sympy/sympy",
            strategy="budget_only_tight", routing="budget_only",
            resolved=False, harness_resolved=False,
            failure_class="harness_failure", forensic_primary_axis="infra",
            total_cost=0.05, estimated_task_cap=0.20, estimated_task_cost=0.01,
            patch_extracted=False, agent_gold_edited=False, llm_turns=5,
            patch_lines=12, f2p_count=1, p2p_count=114,
            problem_length=500, gold_file_count=1,
        ))
        est = AutoBudgetEstimator(memory=mem)
        task = _make_task("sympy__sympy-14774")
        result = est.estimate(task, scale=2.5, min_cap=0.05, max_cap=10.0)
        # Harness failure excluded → falls back to history_exact
        assert result.source == "history_exact"
        assert result.estimated_cost == 0.01

    def test_knn_fallback_same_repo(self):
        mem = AutoBudgetMemory()
        for i in range(3):
            mem.write_record(AutoBudgetMemory.build_record(
                instance_id=f"django__django-{10000+i}", repo="django/django",
                strategy="all_pro", routing="all_pro",
                resolved=True, harness_resolved=True,
                failure_class="", forensic_primary_axis="pass",
                total_cost=0.40 + i * 0.05,
                estimated_task_cap=1.00, estimated_task_cost=0.50,
                patch_extracted=True, agent_gold_edited=True, llm_turns=8,
                patch_lines=12, f2p_count=1, p2p_count=2,
                problem_length=500, gold_file_count=1,
            ))
        est = AutoBudgetEstimator(memory=mem, k=3)
        task = _make_task("django__django-new", patch="line1\n" * 13, f2p=("t1",), p2p=("p1", "p2"), repo="django/django")
        result = est.estimate(task, scale=2.5, min_cap=0.05, max_cap=10.0)
        # kNN should find the 3 similar django tasks
        assert result.source == "memory_repo_knn"
        assert result.memory_neighbors > 0

    def test_memory_to_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
            f.write(json.dumps({"instance_id": "test__task-1", "total_cost": 0.10, "cap_was_sufficient": "sufficient"}) + "\n")
        try:
            mem = AutoBudgetMemory(path)
            assert len(mem) == 1
            # Write another record
            mem.write_record({"instance_id": "test__task-2", "total_cost": 0.20, "cap_was_sufficient": "sufficient"})
            # Re-read from file
            mem2 = AutoBudgetMemory(path)
            assert len(mem2) == 2
        finally:
            path.unlink()


class TestCapSufficiency:
    def test_sufficient_on_pass(self):
        assert _classify_cap_sufficiency(
            resolved=True, harness_resolved=True,
            exit_status="Submitted", failure_class="",
            patch_extracted=True, agent_gold_edited=True,
        ) == "sufficient"

    def test_harness_failure_excluded(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False,
            exit_status="Submitted", failure_class="harness_failure",
            patch_extracted=False, agent_gold_edited=False,
        ) == "exclude_harness"

    def test_likely_underbudget(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False,
            exit_status="BudgetFlowBudgetError", failure_class="budget_fail",
            patch_extracted=True, agent_gold_edited=True,
        ) == "likely_underbudget"

    def test_underbudget_or_model(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False,
            exit_status="BudgetFlowBudgetError", failure_class="repair_quality",
            patch_extracted=True, agent_gold_edited=True,
        ) == "underbudget_or_model"

    def test_not_enough_evidence(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False,
            exit_status="BudgetFlowBudgetError", failure_class="budget_fail",
            patch_extracted=False, agent_gold_edited=False,
        ) == "not_enough_evidence"

    def test_exclude_corrupt(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False,
            exit_status="Submitted", failure_class="corrupt_patch",
            patch_extracted=True, agent_gold_edited=False,
        ) == "exclude_corrupt"

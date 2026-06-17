"""Tests for ModelFit estimation from clean historical JSONL evidence.

Verifies that per-tier fit rates are derived from verified outcome and
cost/turn evidence, with budget-exhausted rows as censored lower-bound
signals that penalise the exhausted tier.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import tempfile

import pytest

sys.path.insert(0, "src")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _catalog() -> dict:
    return {
        "catalog_revision": "test",
        "catalog_content_hash": "test",
    }


def _setup_catalog_test():
    """Make the in-memory catalog match our test catalog hash."""
    import budgetflow.model_tiers as mt

    original = {
        "revision": mt.catalog_revision(),
        "hash": mt._catalog_content_hash,
    }
    mt._catalog_revision = "test"
    mt._catalog_content_hash = "test"
    return original


def _restore_catalog(original: dict):
    import budgetflow.model_tiers as mt

    mt._catalog_revision = original["revision"]
    mt._catalog_content_hash = original["hash"]


class TestModelFitEstimation:
    def test_derives_fit_from_completed_rows(self):
        """Clean completed T2 and T3 rows on the same task → per-tier fit derived."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        records = [
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-a",
                "total_cost": 2.30,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "HarnessFailed",
                "row_finished_at": 1,
            },
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.2745,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {"task-a": {"bootstrap_difficulty": 23.35}}
            evidence = estimate_model_fit_from_jsonl(path, ["task-a"], value_features)

            # Both tiers should have fit estimates
            assert 2 in evidence.tier_fit
            assert 3 in evidence.tier_fit
            # T3 should have higher fit than T2 (lower cost for same task)
            assert evidence.tier_fit[3] > evidence.tier_fit[2], (
                f"T3 fit {evidence.tier_fit[3]:.4f} should exceed T2 fit {evidence.tier_fit[2]:.4f}"
            )
            # T2 fit should be materially lower than catalog 0.24
            assert evidence.tier_fit[2] < 0.20, (
                f"T2 fit {evidence.tier_fit[2]:.4f} should be materially below catalog 0.24"
            )
            assert evidence.evidence_tasks >= 1
            assert evidence.confidence in ("medium", "high")

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_budget_exhausted_penalises_tier(self):
        """Budget-exhausted T2 row drags down T2 fit estimate."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        # T2 budget_exhausted on task-a (censored), T3 completed on task-b
        records = [
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-a",
                "total_cost": 2.30,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "BudgetFlowBudgetError",
                "exit_reason": "budget_exhausted",
                "row_finished_at": 1,
            },
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.30,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-b",
                "total_cost": 0.50,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {
                "task-a": {"bootstrap_difficulty": 23.35},
                "task-b": {"bootstrap_difficulty": 20.0},
            }
            evidence = estimate_model_fit_from_jsonl(path, ["task-a", "task-b"], value_features)

            assert 2 in evidence.tier_fit
            # T2 has censored evidence → should be in censored_tiers
            assert 2 in evidence.censored_tiers, (
                f"T2 should be in censored_tiers due to budget_exhausted row; "
                f"got censored_tiers={evidence.censored_tiers}"
            )
            # T2 fit should be penalised
            assert evidence.tier_fit[2] < 0.20, (
                f"T2 fit {evidence.tier_fit[2]:.4f} should be penalised below catalog 0.24"
            )

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_censored_only_tier_gets_conservative_penalty(self):
        """Tier with ONLY censored evidence gets a 0.5x conservative penalty."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        records = [
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-a",
                "total_cost": 2.30,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "BudgetFlowBudgetError",
                "exit_reason": "budget_exhausted",
                "row_finished_at": 1,
            },
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.30,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {"task-a": {"bootstrap_difficulty": 23.35}}
            evidence = estimate_model_fit_from_jsonl(path, ["task-a"], value_features)

            # T2 has ONLY censored evidence on task-a (no completed T2 rows)
            # The conservative penalty should apply
            assert evidence.tier_fit[2] < 0.10, (
                f"T2 fit {evidence.tier_fit[2]:.4f} should be heavily penalised "
                f"(censored-only tier with conservative 0.5x multiplier)"
            )
            assert 2 in evidence.censored_tiers

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_no_historical_data_falls_back_to_catalog(self):
        """When there's no historical data for a tier, catalog progress_score is used."""
        from budgetflow.model_fit_estimator import _build_evidence

        evidence = _build_evidence({}, {}, set())
        # Should have catalog defaults (tiers 1, 2, 3)
        assert len(evidence.tier_fit) >= 2
        assert evidence.confidence == "low"
        assert evidence.evidence_tasks == 0
        assert any("catalog fallback" in r for r in evidence.reasons)

    def test_excludes_non_scoreable_rows(self):
        """Rows with score_status != pass/true_fail are excluded."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        records = [
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.50,
                "catalog": cat,
                "score_status": "timeout",
                "exit_status": "Timeout",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {"task-a": {"bootstrap_difficulty": 30.0}}
            evidence = estimate_model_fit_from_jsonl(path, ["task-a"], value_features)
            # No scoreable evidence → fallback to catalog
            assert evidence.evidence_tasks == 0
            assert evidence.confidence == "low"

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_excludes_infra_provider_aborts(self):
        """Rows with infra/provider aborts are excluded from ModelFit estimation."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        records = [
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 2.00,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "HarnessFailed",
                "failure_class": "infra_fail",
                "row_finished_at": 1,
            },
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-a",
                "total_cost": 1.00,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "HarnessFailed",
                "provider_error_kind": "rate_limit",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {"task-a": {"bootstrap_difficulty": 30.0}}
            evidence = estimate_model_fit_from_jsonl(path, ["task-a"], value_features)
            assert evidence.evidence_tasks == 0
            assert evidence.confidence == "low"

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_excludes_catalog_mismatch_rows(self):
        """Rows with non-matching catalog are excluded."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        records = [
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-a",
                "total_cost": 0.50,
                "catalog": {"catalog_revision": "different", "catalog_content_hash": "different"},
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {"task-a": {"bootstrap_difficulty": 30.0}}
            evidence = estimate_model_fit_from_jsonl(path, ["task-a"], value_features)
            assert evidence.evidence_tasks == 0

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_ignores_strategies_with_ambiguous_tier(self):
        """BudgetFlow strategies (tier varies by task) are skipped for now."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        records = [
            {
                "strategy": "budgetflow_task_level",
                "instance_id": "task-a",
                "total_cost": 1.50,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "HarnessFailed",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {"task-a": {"bootstrap_difficulty": 30.0}}
            evidence = estimate_model_fit_from_jsonl(path, ["task-a"], value_features)
            # budgetflow_task_level has ambiguous tier → no evidence
            assert evidence.evidence_tasks == 0

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_multiple_tasks_strengthen_confidence(self):
        """Evidence from 3+ tasks → high confidence."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl

        cat = _catalog()
        records = []
        for i, task_id in enumerate(["task-a", "task-b", "task-c"]):
            records.append({
                "strategy": "bare_t2_baseline",
                "instance_id": task_id,
                "total_cost": 0.50 + i * 0.10,
                "catalog": cat,
                "score_status": "pass" if i < 2 else "true_fail",
                "exit_status": "HarnessResolved" if i < 2 else "HarnessFailed",
                "row_finished_at": 1,
            })
            records.append({
                "strategy": "bare_t3_baseline",
                "instance_id": task_id,
                "total_cost": 0.20 + i * 0.05,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            })
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {
                "task-a": {"bootstrap_difficulty": 20.0},
                "task-b": {"bootstrap_difficulty": 25.0},
                "task-c": {"bootstrap_difficulty": 30.0},
            }
            evidence = estimate_model_fit_from_jsonl(
                path, ["task-a", "task-b", "task-c"], value_features
            )
            assert evidence.confidence == "high"
            assert evidence.evidence_tasks == 3

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_to_allocation_model_fit_format(self):
        """ModelFitEvidence.to_allocation_model_fit returns keyed form."""
        from budgetflow.model_fit_estimator import ModelFitEvidence

        evidence = ModelFitEvidence(
            tier_fit={2: 0.027, 3: 0.25},
            confidence="medium",
            evidence_tasks=1,
            censored_tiers={2},
        )
        alloc_fit = evidence.to_allocation_model_fit()
        assert alloc_fit == {"tier2": 0.027, "tier3": 0.25}


class TestSixByFiveLikeScenario:
    """End-to-end: model_fit absent from value matrix, clean historical evidence
    says T2 long-tail / T3 efficient, task-level chooses T3 for the high-value task."""

    def test_chooses_t3_when_historical_evidence_shows_t2_long_tail(self):
        """6x5-like: T2 budget_exhausted at $2.30/85 turns, T3 resolved at $0.27/9 turns."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl
        from budgetflow.adapter.strategies import (
            build_routing_context,
            choose_backend,
            _expected_total_cost,
        )
        from budgetflow.allocation import AllocationContext
        from budgetflow.types import Stage, TurnInfo

        cat = _catalog()
        records = [
            # T2 on task-hard: budget_exhausted after $2.30 (85 turns effectively)
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-hard",
                "total_cost": 2.30,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "BudgetFlowBudgetError",
                "exit_reason": "budget_exhausted",
                "row_finished_at": 1,
            },
            # T3 on task-hard: resolved in 9 turns, $0.2745
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-hard",
                "total_cost": 0.2745,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
            # T2 on task-easy: completed at $0.50
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-easy",
                "total_cost": 0.50,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                path = Path(f.name)
            _write_jsonl(path, records)

            value_features = {
                "task-hard": {"bootstrap_difficulty": 23.35},
                "task-easy": {"bootstrap_difficulty": 10.0},
            }
            evidence = estimate_model_fit_from_jsonl(
                path, ["task-hard", "task-easy"], value_features
            )

            # T2 fit should be heavily penalised by censored evidence
            assert evidence.tier_fit[2] < 0.15, (
                f"T2 fit {evidence.tier_fit[2]:.4f} should be well below catalog 0.24"
            )
            fit_ratio = evidence.tier_fit[3] / max(evidence.tier_fit[2], 0.001)
            assert fit_ratio > 2.0, (
                f"T3/T2 fit ratio {fit_ratio:.2f} should be substantial"
            )

            # Now wire into task-level selection for the hard task
            from budgetflow.types import Backend

            backends = [
                Backend("tier2", 2, 0.0009, 0.0045, 100, 20, 1024, 0.24, 4200),
                Backend("tier3", 3, 0.0045, 0.0225, 100, 20, 1024, 0.25, 1200),
            ]

            # AllocationContext: high-value task with NO per-task model_fit
            alloc = AllocationContext(
                task_value=2.0,
                task_effort=23.35,
                model_fit=None,  # absent — as in current 6x5 value matrix
                value_source="manual",
                effort_source="bootstrap",
                model_fit_source="none",
            )

            ctx = build_routing_context(
                "value_aware_task_level",
                list(backends),
                budget_pressure=0.3,
                task_value=2.0,
                median_task_value=1.0,
                allocation=alloc,
                model_fit_override=evidence.tier_fit,
            )

            per_turn = {
                b.name: b.cost_per_input_token * 2000 + b.cost_per_output_token * b.mean_output_tokens
                for b in backends
            }

            # Verify T2 expected total cost > T3
            t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
            t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
            assert t2_total > t3_total, (
                f"T2 total ${t2_total:.4f} should exceed T3 ${t3_total:.4f} "
                f"with derived ModelFit"
            )

            turn = TurnInfo(
                workflow_id="task-hard",
                step_index=1,
                stage=Stage.LOCALIZATION,
                w_i=1.0,
                context_len=1000,
            )
            backend = choose_backend(ctx, turn, per_turn)
            assert backend.tier == 3, (
                f"6x5-like: expected T3 for hard task with long-tail T2 evidence, "
                f"got {backend.name}"
            )

            path.unlink()
        finally:
            _restore_catalog(catalog_orig)

    def test_budget_compiler_projection_increases_with_derived_fit(self):
        """Budget compiler T2 cold-start projection materially increases with derived fit."""
        from budgetflow.model_fit_estimator import estimate_model_fit_from_jsonl
        from budgetflow.experiments.budget_binding import (
            _cold_start_cost_estimate,
            calibrate_budget,
        )

        cat = _catalog()
        records = [
            {
                "strategy": "bare_t2_baseline",
                "instance_id": "task-x",
                "total_cost": 2.30,
                "catalog": cat,
                "score_status": "true_fail",
                "exit_status": "BudgetFlowBudgetError",
                "exit_reason": "budget_exhausted",
                "row_finished_at": 1,
            },
            {
                "strategy": "bare_t3_baseline",
                "instance_id": "task-x",
                "total_cost": 0.2745,
                "catalog": cat,
                "score_status": "pass",
                "exit_status": "HarnessResolved",
                "row_finished_at": 1,
            },
        ]
        catalog_orig = _setup_catalog_test()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                jsonl_path = Path(f.name)
            _write_jsonl(jsonl_path, records)

            value_features = {"task-x": {"bootstrap_difficulty": 23.35}}
            evidence = estimate_model_fit_from_jsonl(
                jsonl_path, ["task-x"], value_features
            )

            # Cold-start WITHOUT derived fit (catalog only)
            t2_catalog_only = _cold_start_cost_estimate("budgetflow_task_level", 23.35)
            # Cold-start WITH derived fit
            t2_with_fit = _cold_start_cost_estimate(
                "budgetflow_task_level", 23.35, fit_overrides=evidence.tier_fit
            )

            # With derived fit, T2 projection should be materially higher
            ratio = t2_with_fit / max(t2_catalog_only, 0.0001)
            assert ratio > 1.5, (
                f"Derived fit should increase T2 projection by >1.5x; "
                f"catalog-only=${t2_catalog_only:.6f}, with-fit=${t2_with_fit:.6f}, "
                f"ratio={ratio:.2f}x"
            )

            # Now test full calibrate_budget pipeline
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                vm_path = Path(f.name)
                f.write(json.dumps({"tasks": {"task-x": {"task_effort": {"bootstrap_heuristic": 23.35}}}}))

            plan = calibrate_budget(
                ["task-x"],
                historical_jsonl=jsonl_path,
                value_matrix_path=vm_path,
                strategies=("budgetflow_task_level", "bare_t3_baseline"),
                target_utilization=0.90,
            )

            # plan should have model_fit_evidence
            assert plan.model_fit_evidence is not None, "plan should store model_fit_evidence"
            assert plan.model_fit_evidence["confidence"] in ("medium", "high")
            # T2 projection should include censored floor + fit-scaled runway
            t2_projected = plan.projected_spend_by_strategy.get("budgetflow_task_level", 0)
            assert t2_projected > 2.30, (
                f"T2 projected ${t2_projected:.4f} should exceed censored floor $2.30"
            )

            jsonl_path.unlink()
            vm_path.unlink()
        finally:
            _restore_catalog(catalog_orig)

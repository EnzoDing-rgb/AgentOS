"""Prove Task Value / Task Effort / Model Fit stay in separate namespaces."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from budgetflow.allocation import AllocationContext
from budgetflow.value_matrix import bootstrap_task_effort, build_bootstrap_value_matrix


@dataclass
class _FakeTask:
    instance_id: str
    repo: str
    patch: str = ""
    problem_statement: str = ""
    hints_text: str = ""
    fail_to_pass: list = ()
    pass_to_pass: list = ()
    test_patch: str = ""


# ── P0: concept separation ──────────────────────────────────────────────

def test_task_value_and_effort_in_separate_namespaces() -> None:
    """bootstrap_heuristic lives under task_effort, not task_value."""
    matrix = build_bootstrap_value_matrix(
        [_FakeTask(instance_id="test__task-1", repo="test/test")],
        task_source="test",
    )
    task = matrix["tasks"]["test__task-1"]

    tv = task.get("task_value", {})
    assert "bootstrap_heuristic" not in tv
    assert "bootstrap_difficulty" not in tv
    assert "equal" in tv

    te = task.get("task_effort")
    assert te is not None
    assert "bootstrap_heuristic" in te
    assert isinstance(te["bootstrap_heuristic"], (int, float))


def test_task_value_only_has_known_profiles() -> None:
    """task_value namespace: only equal and manual_value profiles."""
    matrix = build_bootstrap_value_matrix(
        [_FakeTask(instance_id="test__task-2", repo="test/test")],
        task_source="test",
    )
    tv = matrix["tasks"]["test__task-2"].get("task_value", {})
    for key in tv:
        assert key in {"equal", "manual_value"}, (
            f"task_value namespace polluted by {key!r}"
        )


def test_old_values_path_not_supported() -> None:
    """Legacy values[profile] is NOT read — only task_value[profile]."""
    from budgetflow.value_efficiency import _extract_lookup

    artifact = {
        "tasks": {
            "old__task-1": {
                "values": {"equal": 1.0}
            }
        }
    }
    # Old schema without task_value key returns None (no fallback).
    assert _extract_lookup(artifact, "equal") is None


def test_task_value_lookup() -> None:
    """_extract_lookup reads task_value[profile]."""
    from budgetflow.value_efficiency import _extract_lookup

    artifact = {
        "tasks": {
            "t__1": {"task_value": {"equal": 2.0}}
        }
    }
    assert _extract_lookup(artifact, "equal") == {"t__1": 2.0}


def test_effort_lookup() -> None:
    """_extract_effort_lookup reads task_effort.bootstrap_heuristic."""
    from budgetflow.value_efficiency import _extract_effort_lookup

    artifact = {
        "tasks": {
            "effort__task-1": {"task_effort": {"bootstrap_heuristic": 42.0}}
        }
    }
    assert _extract_effort_lookup(artifact) == {"effort__task-1": 42.0}


# ── AllocationContext ────────────────────────────────────────────────────

def test_allocation_context_defaults() -> None:
    ctx = AllocationContext()
    assert ctx.task_value == 1.0
    assert ctx.task_effort is None
    assert ctx.model_fit is None
    assert ctx.value_source == "equal_sanity"
    assert ctx.effort_source == "none"
    assert ctx.model_fit_source == "catalog_progress_prior"
    assert not ctx.has_effort
    assert not ctx.has_model_fit


def test_allocation_context_has_effort() -> None:
    ctx = AllocationContext(task_effort=25.0, effort_source="bootstrap_heuristic")
    assert ctx.has_effort
    meta = ctx.to_metadata()
    assert meta["task_effort"] == 25.0
    assert meta["effort_source"] == "bootstrap_heuristic"


def test_allocation_context_has_model_fit() -> None:
    ctx = AllocationContext(model_fit={"tier1": 0.3, "tier2": 0.6, "tier3": 0.9})
    assert ctx.has_model_fit
    assert ctx.to_metadata()["has_model_fit"] is True


def test_allocation_context_to_metadata() -> None:
    ctx = AllocationContext(
        task_value=2.0,
        task_effort=15.0,
        model_fit={"tier2": 0.5},
        value_source="value_matrix",
        effort_source="bootstrap_heuristic",
        model_fit_source="catalog_progress_prior",
    )
    meta = ctx.to_metadata()
    assert meta["task_value"] == 2.0
    assert meta["task_effort"] == 15.0
    assert meta["has_model_fit"] is True
    assert meta["value_source"] == "value_matrix"


# ── bootstrap_task_effort ────────────────────────────────────────────────

def test_bootstrap_task_effort_structure() -> None:
    result = bootstrap_task_effort(
        {"instance_id": "x", "repo": "a/b",
         "patch": "", "problem_statement": "", "hints_text": ""}
    )
    assert "bootstrap_heuristic" in result
    assert result["source"] == "task_metadata_formula"
    assert "features" in result
    assert isinstance(result["bootstrap_heuristic"], float)


# ── TierFrontier: ModelFit-based advisory scoring ────────────────────────

def test_tier_frontier_score_better_with_higher_progress_delta() -> None:
    """Frontier score is lower (better T3 case) when progress delta is positive."""
    from budgetflow.tier_frontier import TierFrontier
    from budgetflow.allocation import AllocationContext

    # Simulate a frontier where T3 has good repair progress delta
    frontier = TierFrontier(
        reference_tier=2,
        strongest_tier=3,
        reference_display="T2",
        strongest_display="T3",
        strongest_input_ratio=2.0,
        strongest_output_ratio=2.5,
        strongest_progress_delta={"localization": 0.1, "repair": 0.3, "validation": 0.2},
        reference_runway_turns=35,
        reason="test",
    )

    # High progress delta → low score → good T3 case
    score_repair = frontier.frontier_score("repair", budget_pressure=0.1)
    score_localization = frontier.frontier_score("localization", budget_pressure=0.1)
    assert score_repair < score_localization  # repair has higher delta


def test_tier_frontier_score_worse_with_tight_budget() -> None:
    """Higher budget pressure → higher (worse) frontier score."""
    from budgetflow.tier_frontier import TierFrontier
    from budgetflow.allocation import AllocationContext

    frontier = TierFrontier(
        reference_tier=2,
        strongest_tier=3,
        reference_display="T2",
        strongest_display="T3",
        strongest_input_ratio=2.0,
        strongest_output_ratio=2.5,
        strongest_progress_delta={"localization": 0.1, "repair": 0.3, "validation": 0.2},
        reference_runway_turns=35,
        reason="test",
    )

    score_loose = frontier.frontier_score("repair", budget_pressure=0.0)
    score_tight = frontier.frontier_score("repair", budget_pressure=0.8)
    assert score_tight > score_loose  # tight budget → worse T3 case


def test_tier_frontier_score_uses_task_value_from_allocation() -> None:
    """Higher task value → lower (better) frontier score."""
    from budgetflow.tier_frontier import TierFrontier
    from budgetflow.allocation import AllocationContext

    frontier = TierFrontier(
        reference_tier=2,
        strongest_tier=3,
        reference_display="T2",
        strongest_display="T3",
        strongest_input_ratio=2.0,
        strongest_output_ratio=2.5,
        strongest_progress_delta={"repair": 0.2},
        reference_runway_turns=35,
        reason="test",
    )

    low_value = AllocationContext(task_value=0.5)
    high_value = AllocationContext(task_value=2.0)
    score_low = frontier.frontier_score("repair", allocation=low_value, budget_pressure=0.1)
    score_high = frontier.frontier_score("repair", allocation=high_value, budget_pressure=0.1)
    assert score_high < score_low  # higher value → better T3 case


def test_tier_frontier_score_uses_per_tier_model_fit_delta() -> None:
    """ModelFit tier priors must be consumed as tier3-tier2 delta."""
    from budgetflow.tier_frontier import TierFrontier

    frontier = TierFrontier(
        reference_tier=2,
        strongest_tier=3,
        reference_display="T2",
        strongest_display="T3",
        strongest_input_ratio=2.0,
        strongest_output_ratio=2.0,
        strongest_progress_delta={"repair": 0.01},
        reference_runway_turns=35,
        reason="test",
    )

    weak_catalog_score = frontier.frontier_score("repair", allocation=AllocationContext(task_value=1.0))
    empirical_fit_score = frontier.frontier_score(
        "repair",
        allocation=AllocationContext(
            task_value=1.0,
            model_fit={"tier2": 0.30, "tier3": 0.80},
            model_fit_source="budget_plan:historical_jsonl",
        ),
    )

    assert empirical_fit_score < weak_catalog_score
    assert empirical_fit_score == pytest.approx((2.0 - 1.0) / (0.50 * 35.0))


def test_tier_frontier_no_progress_delta_returns_cost_ratio() -> None:
    """When progress delta is zero or negative, score is dominated by cost ratio."""
    from budgetflow.tier_frontier import TierFrontier

    frontier = TierFrontier(
        reference_tier=2,
        strongest_tier=3,
        reference_display="T2",
        strongest_display="T3",
        strongest_input_ratio=3.0,
        strongest_output_ratio=3.5,
        strongest_progress_delta={"repair": -0.1},
        reference_runway_turns=35,
        reason="test",
    )

    score = frontier.frontier_score("repair", budget_pressure=0.0)
    # No value gain → score = cost_ratio (≈3.0), well above 2.0 threshold
    assert score > 2.0


def test_value_aware_task_level_has_task_fixed_backend_slot() -> None:
    """value_aware_task_level owns a task-fixed backend slot."""
    from budgetflow.adapter.strategies import build_routing_context

    ctx = build_routing_context(
        "value_aware_task_level",
        backends=[],
    )
    assert ctx.bootstrap_policy is not None
    assert getattr(ctx, "task_level_backend", "missing") is None


def test_budgetflow_segment_uses_segment_signal() -> None:
    """bf_segment passes turn.segment to policy (Claim 2 enhancement)."""
    from budgetflow.adapter.strategies import build_routing_context

    ctx = build_routing_context(
        "budgetflow_segment",
        backends=[],
    )
    assert ctx.bootstrap_policy is not None

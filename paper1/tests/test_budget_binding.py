"""Tests for budget_binding.py — prove no task-id hardcoding in T3 estimation."""
from __future__ import annotations

import json
from pathlib import Path

from budgetflow.experiments.budget_binding import (
    _estimate_t3_cost_share,
    _load_frozen_preferred_models,
    _load_frozen_caps,
)


# ── _load_frozen_preferred_models ────────────────────────────────────────


def test_load_frozen_preferred_models_extracts_tier2_and_tier3(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({
        "plan": {
            "custom__project-1": {"preferred_model": "tier3", "base_cap": 0.5},
            "custom__project-2": {"preferred_model": "tier2", "base_cap": 0.3},
            "custom__project-3": {"base_cap": 0.2},
        }
    }))
    models = _load_frozen_preferred_models(plan_path)
    assert models == {"custom__project-1": "tier3", "custom__project-2": "tier2"}


def test_load_frozen_preferred_models_empty_when_no_preferred_model(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({
        "plan": {
            "task-a": {"base_cap": 0.1},
            "task-b": {"base_cap": 0.2},
        }
    }))
    models = _load_frozen_preferred_models(plan_path)
    assert models == {}


# ── _estimate_t3_cost_share — no task-id dependency ─────────────────────


def test_t3_share_reads_preferred_model_not_task_id() -> None:
    """T3 share for frozen-plan strategies comes from preferred_models, not task_id."""
    preferred = {"some_arbitrary__repo-999": "tier3"}
    share = _estimate_t3_cost_share(
        "enterprise_router_baseline",
        "some_arbitrary__repo-999",
        {},
        preferred_models=preferred,
    )
    assert share == 1.0


def test_t3_share_tier2_task_returns_zero() -> None:
    preferred = {"completely__different-task": "tier2"}
    share = _estimate_t3_cost_share(
        "budgetflow_same_router",
        "completely__different-task",
        {},
        preferred_models=preferred,
    )
    assert share == 0.0


def test_t3_share_task_not_in_preferred_models_returns_zero() -> None:
    """If preferred_models doesn't list the task, assume tier2 (conservative)."""
    share = _estimate_t3_cost_share(
        "enterprise_router_baseline",
        "missing__task-99999",
        {},
        preferred_models={"other__task-1": "tier2"},
    )
    assert share == 0.0


def test_t3_share_preferred_models_none_returns_zero() -> None:
    """When preferred_models is None (no frozen plan), conservative default."""
    share = _estimate_t3_cost_share(
        "enterprise_router_baseline",
        "sympy__sympy-16988",  # even this well-known id is not special
        {},
        preferred_models=None,
    )
    assert share == 0.0


def test_t3_share_bare_t3_always_one_regardless_of_preferred() -> None:
    share = _estimate_t3_cost_share(
        "bare_t3_baseline",
        "some_task",
        {},
        preferred_models={"some_task": "tier2"},
    )
    assert share == 1.0


def test_t3_share_bare_t2_always_zero_regardless_of_preferred() -> None:
    share = _estimate_t3_cost_share(
        "bare_t2_baseline",
        "some_task",
        {},
        preferred_models={"some_task": "tier3"},
    )
    assert share == 0.0


# ── No hardcoded task IDs remain ────────────────────────────────────────


def test_no_sympy_task_id_hardcoding() -> None:
    """Prove the source code doesn't hardcode 16988 or 20639."""
    import inspect
    source = inspect.getsource(_estimate_t3_cost_share)
    assert "16988" not in source
    assert "20639" not in source
    assert "sympy__" not in source.lower()

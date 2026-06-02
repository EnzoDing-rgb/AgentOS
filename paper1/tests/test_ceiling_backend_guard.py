from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.adapter.backends import build_backends_for_strategy, build_ceiling_backends, build_compare_backends
from budgetflow.adapter.strategies import build_routing_context, choose_backend
from budgetflow.defaults import (
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER3_BACKEND,
)
from budgetflow.types import Stage, TurnInfo


def _turn() -> TurnInfo:
    return TurnInfo(
        workflow_id="wf",
        step_index=1,
        stage=Stage.LOCALIZATION,
        w_i=1.0,
        context_len=1000,
    )


def test_compare_backends_use_three_model_tiers() -> None:
    names = {backend.name for backend in build_compare_backends(include_t1=True)}

    assert names == {TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND}


def test_compare_backends_skip_t1_by_default() -> None:
    names = {backend.name for backend in build_compare_backends()}

    assert TIER1_BACKEND not in names
    assert names == {TIER2_BACKEND, TIER3_BACKEND}


def test_all_flash_strategy_gets_t1_ablation_pool() -> None:
    names = {backend.name for backend in build_backends_for_strategy("all_flash")}

    assert TIER1_BACKEND in names


def test_budget_only_routes_within_three_tiers() -> None:
    ctx = build_routing_context("budget_only", build_compare_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name != TIER1_BACKEND
    assert backend.tier <= 3


def test_all_tier2_still_selects_t2_when_t1_is_absent() -> None:
    ctx = build_routing_context("all_tier2", build_compare_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER2_BACKEND


def test_all_pro_selects_coder_plus() -> None:
    ctx = build_routing_context("all_pro", build_compare_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER2_BACKEND


def test_all_t3_uses_t3_backend() -> None:
    ctx = build_routing_context("all_t3", build_ceiling_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER3_BACKEND

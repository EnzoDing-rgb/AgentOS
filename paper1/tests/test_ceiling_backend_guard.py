from __future__ import annotations

from budgetflow.adapter.backends import build_ceiling_backends, build_compare_backends
from budgetflow.adapter.strategies import build_routing_context, choose_backend
from budgetflow.defaults import TIER5_BACKEND
from budgetflow.types import Stage, TurnInfo


def _turn() -> TurnInfo:
    return TurnInfo(
        workflow_id="wf",
        step_index=1,
        stage=Stage.LOCALIZATION,
        w_i=1.0,
        context_len=1000,
    )


def test_compare_backends_exclude_gpt55_ceiling_by_default() -> None:
    assert TIER5_BACKEND not in {backend.name for backend in build_compare_backends()}


def test_budget_only_cannot_route_to_gpt55_ceiling() -> None:
    ctx = build_routing_context("budget_only", build_compare_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name != TIER5_BACKEND
    assert backend.tier <= 4


def test_all_gpt55_uses_explicit_ceiling_pool() -> None:
    ctx = build_routing_context("all_gpt55", build_ceiling_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER5_BACKEND

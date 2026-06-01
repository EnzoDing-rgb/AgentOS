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
    TIER4_BACKEND,
    TIER4_GPT53_BACKEND,
    TIER4_QWEN_MAX_BACKEND,
    TIER5_BACKEND,
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


def test_compare_backends_exclude_gpt55_ceiling_by_default() -> None:
    assert TIER5_BACKEND not in {backend.name for backend in build_compare_backends()}
    assert TIER4_BACKEND in {backend.name for backend in build_compare_backends()}
    assert TIER4_QWEN_MAX_BACKEND not in {backend.name for backend in build_compare_backends()}
    assert TIER4_GPT53_BACKEND not in {backend.name for backend in build_compare_backends()}


def test_compare_backends_skip_t1_by_default() -> None:
    names = {backend.name for backend in build_compare_backends()}

    assert TIER1_BACKEND not in names
    assert TIER2_BACKEND in names


def test_compare_backends_can_include_t1_for_ablation() -> None:
    names = {backend.name for backend in build_compare_backends(include_t1=True)}

    assert TIER1_BACKEND in names


def test_all_flash_strategy_gets_t1_ablation_pool() -> None:
    names = {backend.name for backend in build_backends_for_strategy("all_flash")}

    assert TIER1_BACKEND in names


def test_compare_backends_can_opt_into_gpt53_regular_t4(monkeypatch) -> None:
    monkeypatch.setenv("BF_T4_PROVIDER", "gpt53_codex")

    names = {backend.name for backend in build_compare_backends()}

    assert TIER4_GPT53_BACKEND in names
    assert TIER4_BACKEND not in names
    assert TIER5_BACKEND not in names


def test_compare_backends_can_opt_into_qwen_max_regular_t4(monkeypatch) -> None:
    monkeypatch.setenv("BF_T4_PROVIDER", "qwen_max")

    names = {backend.name for backend in build_compare_backends()}

    assert TIER4_QWEN_MAX_BACKEND in names
    assert TIER4_BACKEND not in names
    assert TIER4_GPT53_BACKEND not in names
    assert TIER5_BACKEND not in names


def test_budget_only_cannot_route_to_gpt55_ceiling() -> None:
    ctx = build_routing_context("budget_only", build_compare_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name != TIER5_BACKEND
    assert backend.name != TIER1_BACKEND
    assert backend.tier <= 4


def test_all_tier2_still_selects_t2_when_t1_is_absent() -> None:
    ctx = build_routing_context("all_tier2", build_compare_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER2_BACKEND


def test_all_pro_still_selects_t3_when_t1_is_absent() -> None:
    ctx = build_routing_context("all_pro", build_compare_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER3_BACKEND


def test_all_gpt55_uses_explicit_ceiling_pool() -> None:
    ctx = build_routing_context("all_gpt55", build_ceiling_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER5_BACKEND


def test_all_gpt53_uses_explicit_gpt53_backend() -> None:
    ctx = build_routing_context("all_gpt53", build_ceiling_backends(), budget_pressure=0.01)

    backend = choose_backend(ctx, _turn(), {})

    assert backend.name == TIER4_GPT53_BACKEND

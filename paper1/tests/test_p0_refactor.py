"""Tests for P0 refactors: ModelCatalog, strategy fixes, RouterDecision, ProtocolAdapter."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.defaults import ModelCatalog, TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND
from budgetflow.types import Backend, Stage, TurnInfo


def _test_backends():
    return [
        Backend(name="tier1", tier=1, cost_per_input_token=0.001, cost_per_output_token=0.004,
                rpm_limit=0, concurrency_limit=0, mean_output_tokens=512, progress_score=0.1, latency_ms=300),
        Backend(name="tier2", tier=2, cost_per_input_token=0.002, cost_per_output_token=0.008,
                rpm_limit=0, concurrency_limit=0, mean_output_tokens=768, progress_score=0.2, latency_ms=600),
        Backend(name="tier3", tier=3, cost_per_input_token=0.003, cost_per_output_token=0.012,
                rpm_limit=0, concurrency_limit=0, mean_output_tokens=1024, progress_score=0.3, latency_ms=900),
    ]


class TestModelCatalog:
    def test_cheapest_returns_lowest_tier(self):
        backends = _test_backends()
        b = ModelCatalog.cheapest(backends)
        assert b.name == "tier1"
        assert b.tier == 1

    def test_strongest_returns_highest_tier(self):
        backends = _test_backends()
        b = ModelCatalog.strongest(backends)
        assert b.name == "tier3"
        assert b.tier == 3

    def test_tier_n_returns_exact_tier(self):
        backends = _test_backends()
        b = ModelCatalog.tier(backends, 2)
        assert b.name == "tier2"
        assert b.tier == 2

    def test_tier_missing_returns_last(self):
        backends = _test_backends()
        b = ModelCatalog.tier(backends, 99)
        assert b.tier == 3

    def test_protocol_for_tool_call(self):
        assert ModelCatalog.protocol_for("tier2") == "tool_call"

    def test_protocol_for_text_regex(self):
        assert ModelCatalog.protocol_for("tier3") == "text_regex"

    def test_protocol_for_unknown_backend(self):
        assert ModelCatalog.protocol_for("nonexistent") == "tool_call"


class TestAllProSelectsStrongest:
    def test_all_pro_picks_tier3_not_tier2(self):
        from budgetflow.adapter.strategies import choose_backend, build_routing_context
        backends = _test_backends()[1:]  # T2, T3 only
        ctx = build_routing_context("all_pro", backends)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=1.0, context_len=100)
        backend = choose_backend(ctx, turn, {b.name: 1.0 for b in backends})
        assert backend.tier == 3
        assert backend.name == "tier3"

    def test_all_tier2_picks_tier2(self):
        from budgetflow.adapter.strategies import choose_backend, build_routing_context
        backends = _test_backends()
        ctx = build_routing_context("all_tier2", backends)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=1.0, context_len=100)
        backend = choose_backend(ctx, turn, {b.name: 1.0 for b in backends})
        assert backend.tier == 2
        assert backend.name == "tier2"


class TestBudgetOnlyRouter:
    def test_budget_only_single_backend_returns_it(self):
        from budgetflow.adapter.strategies import choose_backend, build_routing_context
        backends = _test_backends()[:1]  # T1 only
        ctx = build_routing_context("budget_only", backends)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=1.0, context_len=100)
        backend = choose_backend(ctx, turn, {b.name: 1.0 for b in backends})
        assert backend.tier == 1


class TestRouterDecision:
    def test_all_pro_records_decision(self):
        from budgetflow.adapter.strategies import choose_backend, build_routing_context
        backends = _test_backends()[1:]
        ctx = build_routing_context("all_pro", backends)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=1.0, context_len=100)
        choose_backend(ctx, turn, {b.name: 1.0 for b in backends})
        assert ctx.last_decision is not None
        assert ctx.last_decision.branch == "all_pro"
        assert ctx.last_decision.backend.tier == 3

    def test_budget_only_records_reason(self):
        from budgetflow.adapter.strategies import choose_backend, build_routing_context
        backends = _test_backends()[1:]
        ctx = build_routing_context("budget_only", backends)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=1.0, context_len=100)
        choose_backend(ctx, turn, {b.name: 1.0 for b in backends})
        assert ctx.last_decision is not None
        assert ctx.last_decision.branch == "budget_only"
        assert ctx.last_decision.backend.tier in {2, 3}


class TestProtocolAdapter:
    def test_tier3_is_text_regex(self):
        from budgetflow.adapter.protocol_adapter import ActionProtocolAdapter
        d = ActionProtocolAdapter.resolve("tier3")
        assert d.protocol == "text_regex"
        assert d.parser == "parse_regex_actions"
        assert d.reason == "tier_config"

    def test_tier2_is_tool_call(self):
        from budgetflow.adapter.protocol_adapter import ActionProtocolAdapter
        d = ActionProtocolAdapter.resolve("tier2")
        assert d.protocol == "tool_call"
        assert d.parser == "parse_toolcall_actions"


class TestRequiredBackends:
    def test_all_pro_requires_t3(self):
        from budgetflow.experiments.compare_config import CompareStrategy, required_backends_for_strategies
        strategies = (CompareStrategy("all_pro", "all_pro", None),)
        required = required_backends_for_strategies(strategies)
        assert "tier3" in required
        assert "tier2" not in required  # all_pro no longer requires T2

    def test_all_tier2_requires_t2(self):
        from budgetflow.experiments.compare_config import CompareStrategy, required_backends_for_strategies
        strategies = (CompareStrategy("all_tier2", "all_tier2", None),)
        required = required_backends_for_strategies(strategies)
        assert "tier2" in required
        assert "tier3" not in required

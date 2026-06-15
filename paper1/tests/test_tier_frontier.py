"""Tier frontier calibration tests.

The reference tier is the second-cheapest (enterprise default T2) when >=3
tiers exist, falling back to cheapest for 2-tier catalogs.

frontier_score() replaces the old binary early_allow_strongest gate.
Score < 1.0: T3 justified; 1.0-2.0: marginal; > 2.0: T3 cost not justified.
"""

import sys

import pytest

sys.path.insert(0, "src")


def _backends():
    from budgetflow.types import Backend

    return [
        Backend("tier1", 1, 0.0003, 0.0015, 100, 20, 500, 0.15, 500),
        Backend("tier2", 2, 0.00028, 0.00112, 100, 35, 1100, 0.24, 1000),
        Backend("tier3", 3, 0.000294, 0.001793, 50, 5, 1200, 0.25, 2000),
    ]


def _backends_expensive_t3():
    from budgetflow.types import Backend

    return [
        Backend("tier1", 1, 0.0003, 0.0015, 100, 20, 500, 0.15, 500),
        Backend("tier2", 2, 0.00028, 0.00112, 100, 35, 1100, 0.24, 1000),
        Backend("tier3", 3, 0.008, 0.050, 50, 5, 1200, 0.25, 2000),
    ]


def _backends_weak_t3():
    from budgetflow.types import Backend

    return [
        Backend("tier1", 1, 0.0003, 0.0015, 100, 20, 500, 0.15, 500),
        Backend("tier2", 2, 0.00028, 0.00112, 100, 35, 1100, 0.65, 1000),
        Backend("tier3", 3, 0.000294, 0.001793, 50, 5, 1200, 0.25, 2000),
    ]


class TestTierFrontierCalibration:
    def test_reference_is_second_cheapest_with_three_tiers(self):
        """Default catalog: reference = tier2, frontier score < 2.0 for repair."""
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier.from_catalog()
        assert frontier is not None
        assert frontier.reference_tier == 2
        assert frontier.strongest_tier == 3
        # Default catalog: T3 input 0.294/0.28 ≈ 1.05, output 1.793/1.12 ≈ 1.60
        assert frontier.strongest_output_ratio > 1.5
        assert frontier.strongest_output_ratio < 1.7
        assert "strongest_vs_reference" in frontier.reason or "cost_ratio" in frontier.reason
        assert "cheapest" not in frontier.reason

    def test_t3x2_catalog_reference_t2_high_frontier_score(self):
        """T3x2 catalog: reference = tier2, T3/T2 output ≈ 3.20, frontier score >= 2.0."""
        from pathlib import Path
        from budgetflow.model_tiers import init_catalog
        from budgetflow.tier_frontier import TierFrontier

        t3x2_path = Path(__file__).resolve().parents[1] / "docs" / "config" / "model_tiers.t3x2.json"
        if not t3x2_path.exists():
            pytest.skip("model_tiers.t3x2.json not found")
        init_catalog(t3x2_path)
        frontier = TierFrontier.from_catalog()
        assert frontier is not None
        assert frontier.reference_tier == 2
        assert frontier.strongest_tier == 3
        # T3x2: T3 output 3.586 / T2 output 1.12 ≈ 3.20
        assert frontier.strongest_output_ratio > 3.0
        assert frontier.strongest_output_ratio < 3.3
        # High cost ratio should make frontier score >= 2.0
        score = frontier.frontier_score("repair")
        assert score >= 2.0, f"expected frontier score >= 2.0 for T3x2, got {score}"
        assert frontier.max_tier_pressure_threshold() > 0.15

        # Restore default catalog
        from budgetflow.model_tiers import init_catalog as _ic
        default_path = Path(__file__).resolve().parents[1] / "docs" / "config" / "model_tiers.default.json"
        if default_path.exists():
            _ic(default_path)

    def test_two_tier_catalog_fallback_reference_cheapest(self, monkeypatch):
        """2-tier catalog: reference falls back to cheapest tier."""
        from budgetflow.tier_frontier import TierFrontier

        class _TwoTierCatalog:
            configs = [
                type("c1", (), {
                    "tier": 1,
                    "cost_per_input_token": 0.0003,
                    "cost_per_output_token": 0.0015,
                    "display": "tier1",
                    "progress_prior": {"localization": 0.5, "repair": 0.38, "validation": 0.45},
                })(),
                type("c2", (), {
                    "tier": 3,
                    "cost_per_input_token": 0.008,
                    "cost_per_output_token": 0.050,
                    "display": "tier3",
                    "progress_prior": {"localization": 0.68, "repair": 0.68, "validation": 0.66},
                })(),
            ]

        import budgetflow.model_tiers as mt
        monkeypatch.setattr(mt, "MODEL_CATALOG", _TwoTierCatalog())
        frontier = TierFrontier.from_catalog()
        assert frontier is not None
        assert frontier.reference_tier == 1  # cheapest, since only 2 tiers
        assert frontier.strongest_tier == 3
        # T3 26x more expensive → score >= 2.0
        score = frontier.frontier_score("repair")
        assert score >= 2.0, f"expected high frontier score, got {score}"

    def test_expensive_t3_conservative(self):
        """When T3 is expensive vs reference, frontier score >= 2.0."""
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="tier2",
            strongest_display="tier3",
            strongest_input_ratio=28.57,
            strongest_output_ratio=44.64,
            strongest_progress_delta={"localization": 0.01, "repair": 0.03, "validation": 0.03},
            reason="cost_ratio=44.64>=1.8 strongest_too_expensive_vs_reference",
        )
        score = frontier.frontier_score("repair")
        assert score >= 2.0, f"expensive T3 should have score >= 2.0, got {score}"
        assert frontier.max_tier_pressure_threshold() >= 0.15

    def test_weak_t3_stage_returns_cost_ratio(self):
        """Negative progress delta → zero value gain → score = cost_ratio (advisory)."""
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="tier2",
            strongest_display="tier3",
            strongest_input_ratio=1.05,
            strongest_output_ratio=1.60,
            strongest_progress_delta={"localization": -0.40, "repair": 0.03, "validation": 0.03},
            reason="cost_ratio=1.60<1.8; strongest_weaker_in_some_stage_vs_reference",
        )
        # localization delta is negative → value_gain = 0 → score = cost_ratio
        score_loc = frontier.frontier_score("localization")
        assert score_loc == pytest.approx(1.60)  # raw cost ratio, advisory
        # repair has small positive delta → score = cost_ratio / 0.03
        score_repair = frontier.frontier_score("repair")
        # cost_ratio=1.60, delta=0.03 → 1.60/0.03 ≈ 53
        assert score_repair > 10  # weak T3 case, high score

    def test_to_dict_uses_reference_naming(self):
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="qwen3.7-plus",
            strongest_display="GPT-5.4",
            strongest_input_ratio=1.05,
            strongest_output_ratio=1.60,
            strongest_progress_delta={"localization": 0.01, "repair": 0.03, "validation": 0.03},
            reason="frontier_score based on ModelFit progress deltas",
        )
        d = frontier.to_dict()
        assert d["reference_tier"] == 2
        assert d["strongest_tier"] == 3
        assert d["reference_display"] == "qwen3.7-plus"
        assert "cheapest" not in str(d)
        assert d["strongest_progress_delta"]["repair"] == 0.03

    def test_single_tier_returns_none(self, monkeypatch):
        """Catalog with fewer than 2 tiers returns None."""
        from budgetflow.tier_frontier import TierFrontier

        class _SingleTierCatalog:
            configs = [
                type("cfg", (), {
                    "tier": 1,
                    "cost_per_input_token": 0.0003,
                    "cost_per_output_token": 0.0015,
                    "display": "t1",
                    "progress_prior": {"localization": 0.5, "repair": 0.4, "validation": 0.45},
                })(),
            ]

        import budgetflow.model_tiers as mt
        monkeypatch.setattr(mt, "MODEL_CATALOG", _SingleTierCatalog())
        result = TierFrontier.from_catalog()
        assert result is None


class TestTierFrontierIntegration:
    def test_default_catalog_reference_is_t2(self):
        """Default catalog: reference_tier=2, strongest_output_ratio ≈ 1.60."""
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier.from_catalog()
        assert frontier is not None
        assert frontier.reference_tier == 2
        assert frontier.reference_display != frontier.strongest_display
        assert isinstance(frontier.reason, str)
        assert "reference" in frontier.reason or "strongest_vs" in frontier.reason or "cost_ratio" in frontier.reason

    def test_frontier_score_is_positive_float(self):
        """Default catalog gives finite advisory scores for all stages."""
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier.from_catalog()
        assert frontier is not None
        for stage in ("localization", "repair", "validation"):
            score = frontier.frontier_score(stage)
            assert isinstance(score, float)
            assert score > 0


class TestBareT2Baseline:
    def test_bare_t2_baseline_in_default_strategies(self):
        from budgetflow.experiments.compare_config import DEFAULT_STRATEGIES

        names = {s.name for s in DEFAULT_STRATEGIES}
        assert "bare_t2_baseline" in names

    def test_bare_t2_baseline_routing_is_all_tier2(self):
        from budgetflow.experiments.compare_config import DEFAULT_STRATEGIES

        strategy = next(s for s in DEFAULT_STRATEGIES if s.name == "bare_t2_baseline")
        assert strategy.routing == "all_tier2"
        assert strategy.budgeted is True

    def test_choose_backend_all_tier2_returns_tier2(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("all_tier2", _backends())
        turn = TurnInfo(
            workflow_id="test", step_index=0,
            stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000,
        )
        expected = {b.name: b.cost_per_output_token * b.mean_output_tokens for b in _backends()}
        backend = choose_backend(ctx, turn, expected)
        assert backend.tier == 2


class TestMaxTierWithFrontier:
    def test_max_tier_stored_on_context(self):
        """_budgetflow_max_tier stores both before/after on RoutingContext."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("budgetflow_segment", _backends())
        turn = TurnInfo(
            workflow_id="test", step_index=0,
            stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000,
        )
        expected = {b.name: b.cost_per_output_token * b.mean_output_tokens for b in _backends()}
        choose_backend(ctx, turn, expected)
        assert ctx.max_tier is not None
        assert ctx.max_tier_before_frontier is not None
        assert ctx.max_tier >= ctx.max_tier_before_frontier

    def test_max_tier_fields_in_turn_trace_use_reference_naming(self):
        """Router trace fields include reference-named frontier fields."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.adapter.turn_trace import router_trace_fields
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("budgetflow_segment", _backends())
        turn = TurnInfo(
            workflow_id="test", step_index=0,
            stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000,
        )
        expected = {b.name: b.cost_per_output_token * b.mean_output_tokens for b in _backends()}
        choose_backend(ctx, turn, expected)
        fields = router_trace_fields(ctx)
        assert "strongest_vs_reference_cost_ratio" in fields
        assert fields["strongest_vs_reference_cost_ratio"] is not None
        # Old naming must not appear
        assert "strongest_vs_cheapest_cost_ratio" not in fields

    def test_max_tier_frontier_uses_current_turn_stage(self):
        """Validation-stage cap must not be computed from repair frontier."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.tier_frontier import TierFrontier
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("budgetflow_segment", _backends())
        ctx.tier_frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="T2",
            strongest_display="T3",
            strongest_input_ratio=1.0,
            strongest_output_ratio=1.0,
            strongest_progress_delta={
                "localization": 0.01,
                "repair": 1.00,
                "validation": 0.01,
            },
            reason="test",
        )
        turn = TurnInfo(
            workflow_id="test",
            step_index=0,
            stage=Stage.VALIDATION,
            w_i=1.0,
            context_len=1000,
        )
        expected = {b.name: 0.01 for b in _backends()}

        choose_backend(ctx, turn, expected)

        assert ctx.max_tier == 2

    def test_non_budgetflow_strategies_have_frontier_but_no_max_tier(self):
        """Non-budgetflow strategies have frontier calibration but no max_tier."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.adapter.turn_trace import router_trace_fields
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("all_flash", _backends())
        turn = TurnInfo(
            workflow_id="test", step_index=0,
            stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000,
        )
        expected = {b.name: b.cost_per_output_token * b.mean_output_tokens for b in _backends()}
        choose_backend(ctx, turn, expected)
        fields = router_trace_fields(ctx)
        assert fields["max_tier_before_frontier"] is None
        assert fields["max_tier_after_frontier"] is None
        assert "tier_frontier_active" in fields

    def test_pressure_threshold_in_trace(self):
        """max_tier_pressure_threshold is stored and exposed in traces."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.adapter.turn_trace import router_trace_fields
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("budgetflow_segment", _backends())
        turn = TurnInfo(
            workflow_id="test", step_index=0,
            stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000,
        )
        expected = {b.name: b.cost_per_output_token * b.mean_output_tokens for b in _backends()}
        choose_backend(ctx, turn, expected)
        fields = router_trace_fields(ctx)
        assert "max_tier_pressure_threshold" in fields
        assert fields["max_tier_pressure_threshold"] is not None
        assert isinstance(fields["max_tier_pressure_threshold"], float)

    def test_value_aware_threshold_matches_frontier(self):
        """Value-aware strategy uses frontier threshold, not hardcoded value."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("budgetflow_segment", _backends())
        turn = TurnInfo(
            workflow_id="test", step_index=0,
            stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000,
        )
        expected = {b.name: b.cost_per_output_token * b.mean_output_tokens for b in _backends()}
        choose_backend(ctx, turn, expected)
        from budgetflow.tier_frontier import TierFrontier
        frontier = TierFrontier.from_catalog()
        assert frontier is not None
        expected_threshold = frontier.max_tier_pressure_threshold()
        assert ctx.max_tier_pressure_threshold == expected_threshold

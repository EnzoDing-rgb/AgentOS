"""Tier frontier calibration tests.

The reference tier is the second-cheapest (enterprise default T2) when >=3
tiers exist, falling back to cheapest for 2-tier catalogs.

frontier_score() replaces the old binary early_allow_strongest gate.
Score < 1.0: T3 strongly justified; 1.0-2.0: frontier-allowed;
> 2.0: T3 cost not justified by catalog ModelFit alone.
"""

import sys
import math

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
        # Default mainline catalog uses normalized experimental units:
        # T3 is fixed at approximately 5x the T2 reference.
        assert frontier.reference_display == "glm-5.1"
        assert frontier.strongest_output_ratio == pytest.approx(5.0)
        assert "cost_ratio" in frontier.reason
        assert "cheapest" not in frontier.reason

    def test_t3x2_catalog_reference_t2_high_frontier_score(self):
        """T3x2 catalog: reference = tier2, T3/T2 output ≈ 2.0."""
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
        # T3x2: normalized diagnostic ratio, not provider billing.
        assert frontier.strongest_output_ratio == pytest.approx(2.0)
        # T3x2 is a loose diagnostic catalog: repair is frontier-allowed.
        score = frontier.frontier_score("repair")
        assert 0.0 < score < 2.0, f"expected frontier-allowed T3x2 repair score, got {score}"

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

    def test_frontier_score_never_returns_nonfinite_for_bad_catalog_values(self):
        """Bad hand-edited catalog ratios should not poison downstream traces."""
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="T2",
            strongest_display="T3",
            strongest_input_ratio=float("inf"),
            strongest_output_ratio=float("inf"),
            strongest_progress_delta={"repair": 0.0},
            reference_runway_turns=35,
            reason="bad catalog",
        )

        assert math.isfinite(frontier.frontier_score("repair"))

    def test_expensive_t3_conservative(self):
        """Very expensive T3 stays above the frontier."""
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="tier2",
            strongest_display="tier3",
            strongest_input_ratio=28.57,
            strongest_output_ratio=44.64,
            strongest_progress_delta={"localization": 0.01, "repair": 0.03, "validation": 0.03},
            reference_runway_turns=35,
            reason="cost_ratio=44.64>=1.8 strongest_too_expensive_vs_reference",
        )
        score = frontier.frontier_score("repair")
        assert score >= 20.0, f"expensive T3 should have a high score, got {score}"

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
            reference_runway_turns=35,
            reason="cost_ratio=1.60<1.8; strongest_weaker_in_some_stage_vs_reference",
        )
        # localization delta is negative → value_gain = 0 → score = cost_ratio
        score_loc = frontier.frontier_score("localization")
        assert score_loc == pytest.approx(1.60)  # raw cost ratio, advisory
        # repair has small positive delta, scaled into normalized value units.
        score_repair = frontier.frontier_score("repair")
        assert score_repair < score_loc
        assert score_repair == pytest.approx((1.60 - 1.0) / (0.03 * 35.0))

    def test_to_dict_uses_reference_naming(self):
        from budgetflow.tier_frontier import TierFrontier

        frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="glm-5.1",
            strongest_display="GPT-5.4",
            strongest_input_ratio=1.05,
            strongest_output_ratio=1.60,
            strongest_progress_delta={"localization": 0.01, "repair": 0.03, "validation": 0.03},
            reference_runway_turns=35,
            reason="frontier_score based on ModelFit progress deltas",
        )
        d = frontier.to_dict()
        assert d["reference_tier"] == 2
        assert d["strongest_tier"] == 3
        assert d["reference_display"] == "glm-5.1"
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

    def test_budget_depletion_alone_does_not_open_strongest_tier(self):
        """Budget pressure is scarcity, not an unconditional strongest-tier trigger."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.allocation import AllocationContext
        from budgetflow.tier_frontier import TierFrontier
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("value_aware_task_level", _backends(), budget_pressure=1.0)
        ctx.tier_frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="T2",
            strongest_display="T3",
            strongest_input_ratio=10.0,
            strongest_output_ratio=10.0,
            strongest_progress_delta={
                "localization": 0.01,
                "repair": 0.01,
                "validation": 0.01,
            },
            reference_runway_turns=35,
            reason="expensive strongest",
        )
        turn = TurnInfo(
            workflow_id="test",
            step_index=0,
            stage=Stage.REPAIR,
            w_i=3.0,
            context_len=1000,
        )
        # Use realistic per-turn costs reflecting actual ~5x T3/T2 price ratio.
        # When T3 per-turn cost is 5x T2, the tiny 0.24→0.25 catalog fit delta
        # does NOT make T3 cheaper in total — T2 is correctly cheaper.
        # This verifies budget pressure is not by itself a strongest-tier trigger.
        expected = {
            "tier2": 0.0009 * 2000 + 0.0045 * 1024,
            "tier3": 0.0045 * 2000 + 0.0225 * 1024,
        }

        backend = choose_backend(ctx, turn, expected)

        assert ctx.max_tier == 2
        assert backend.tier <= 2

    def test_task_level_frontier_uses_task_aggregate_not_current_stage(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.allocation import AllocationContext
        from budgetflow.tier_frontier import TierFrontier
        from budgetflow.types import Stage, TurnInfo

        frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="T2",
            strongest_display="T3",
            strongest_input_ratio=3.0,
            strongest_output_ratio=3.0,
            strongest_progress_delta={
                "localization": 0.01,
                "repair": 0.03,
                "validation": 0.03,
            },
            reference_runway_turns=35,
            reason="current t3x3 scale",
        )
        turn = TurnInfo(
            workflow_id="test",
            step_index=0,
            stage=Stage.REPAIR,
            w_i=3.0,
            context_len=1000,
        )
        expected = {b.name: b.cost_per_output_token * b.mean_output_tokens for b in _backends()}

        loose = build_routing_context(
            "value_aware_task_level",
            _backends(),
            budget_pressure=0.01,
            task_value=2.0,
            median_task_value=1.0,
            allocation=AllocationContext(task_value=2.0, model_fit={"tier2": 0.50, "tier3": 0.518}),
        )
        loose.tier_frontier = frontier
        choose_backend(loose, turn, expected)

        tight = build_routing_context(
            "value_aware_task_level",
            _backends(),
            budget_pressure=0.80,
            task_value=2.0,
            median_task_value=1.0,
            allocation=AllocationContext(task_value=2.0, model_fit={"tier2": 0.50, "tier3": 0.518}),
        )
        tight.tier_frontier = frontier
        choose_backend(tight, turn, expected)

        assert loose.tier_frontier_score is not None and loose.tier_frontier_score < 2.0
        assert loose.max_tier == 3
        assert tight.tier_frontier_score is not None and tight.tier_frontier_score > 2.0
        assert tight.max_tier == 2

    def test_task_level_frontier_score_stays_finite_for_bad_catalog_values(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.tier_frontier import TierFrontier
        from budgetflow.types import Stage, TurnInfo

        ctx = build_routing_context("value_aware_task_level", _backends(), budget_pressure=0.5)
        ctx.tier_frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="T2",
            strongest_display="T3",
            strongest_input_ratio=float("inf"),
            strongest_output_ratio=float("inf"),
            strongest_progress_delta={"localization": 0.0, "repair": 0.0, "validation": 0.0},
            reference_runway_turns=35,
            reason="bad catalog",
        )
        turn = TurnInfo(
            workflow_id="test",
            step_index=0,
            stage=Stage.REPAIR,
            w_i=3.0,
            context_len=1000,
        )

        choose_backend(ctx, turn, {b.name: 0.01 for b in _backends()})

        assert ctx.tier_frontier_score is not None
        assert math.isfinite(ctx.tier_frontier_score)

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
            strongest_input_ratio=3.0,
            strongest_output_ratio=3.0,
            strongest_progress_delta={
                "localization": 0.01,
                "repair": 1.00,
                "validation": 0.01,
            },
            reference_runway_turns=35,
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

    def test_frontier_score_in_trace(self):
        """tier_frontier_score is stored and exposed in traces."""
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
        assert "tier_frontier_score" in fields
        assert fields["tier_frontier_score"] is not None
        assert isinstance(fields["tier_frontier_score"], float)
        assert "max_tier_pressure_threshold" not in fields

    def test_value_aware_frontier_score_matches_frontier(self):
        """Value-aware strategy uses the current frontier score."""
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
        expected_score = frontier.frontier_score("localization", budget_pressure=ctx.budget_pressure)
        assert ctx.tier_frontier_score == pytest.approx(expected_score)

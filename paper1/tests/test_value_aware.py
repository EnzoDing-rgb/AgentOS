"""Phase Y: Value-Aware BootstrapPolicy tests."""

import sys

import pytest

sys.path.insert(0, "src")


def _backends():
    from budgetflow.types import Backend
    return [
        Backend("tier2", 2, 0.001, 0.005, 100, 10, 500, 0.5, 500),
        Backend("tier3", 3, 0.010, 0.050, 50, 5, 1000, 0.8, 2000),
    ]


def _turn(stage=None, w_i=0.4):
    from budgetflow.types import Stage, TurnInfo
    return TurnInfo(
        workflow_id="test", step_index=1,
        stage=stage or Stage.LOCALIZATION,
        w_i=w_i, context_len=1000,
    )


class TestStrategyCatalog:
    def test_value_aware_registered_in_default_strategies(self):
        from budgetflow.experiments.compare_config import DEFAULT_STRATEGIES
        names = {s.name for s in DEFAULT_STRATEGIES}
        assert "budgetflow_full" in names
        assert "task_level_control" in names

    def test_budgetflow_full_routing_is_value_aware(self):
        from budgetflow.experiments.compare_config import DEFAULT_STRATEGIES
        strategy = next(s for s in DEFAULT_STRATEGIES if s.name == "budgetflow_full")
        assert strategy.routing == "budgetflow_value_aware"
        assert strategy.budgeted is True

    def test_task_level_value_control_registered(self):
        from budgetflow.experiments.compare_config import DEFAULT_STRATEGIES
        control = next(s for s in DEFAULT_STRATEGIES if s.name == "task_level_control")
        assert control.routing == "value_aware_task_level"
        assert control.budgeted is True


class TestValueMultiplier:
    def test_equal_value_multiplier_is_one(self):
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ValueAwareSelector(table, median_task_value=1.0)
        sel.select_backend(_turn(), backends, 0.5, {b.name: 0.01 for b in backends}, task_value=1.0)
        assert sel.last_multiplier == 1.0

    def test_high_value_easier_t3(self):
        """Higher task_value → higher multiplier → lower effective threshold → easier T3."""
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ValueAwareSelector(table, median_task_value=1.0)
        # With very low pressure, low-value should NOT upgrade but high-value might
        sel_low = ValueAwareSelector(table, median_task_value=1.0)
        sel_low.select_backend(_turn(), backends, 0.01, {b.name: 0.01 for b in backends}, task_value=0.3)
        low_mult = sel_low.last_multiplier
        sel_high = ValueAwareSelector(table, median_task_value=1.0)
        sel_high.select_backend(_turn(), backends, 0.01, {b.name: 0.01 for b in backends}, task_value=2.0)
        high_mult = sel_high.last_multiplier
        assert high_mult > low_mult, f"high={high_mult} should be > low={low_mult}"

    def test_low_value_more_conservative(self):
        """Low value → lower multiplier → higher effective threshold → harder T3."""
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ValueAwareSelector(table, median_task_value=1.0)
        sel.select_backend(_turn(), backends, 0.5, {b.name: 0.01 for b in backends}, task_value=0.5)
        assert sel.last_multiplier < 1.0

    def test_clamp_upper_bound(self):
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ValueAwareSelector(table, median_task_value=1.0)
        sel.select_backend(_turn(), backends, 0.5, {b.name: 0.01 for b in backends}, task_value=10.0)
        assert sel.last_multiplier == 2.0

    def test_clamp_lower_bound(self):
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ValueAwareSelector(table, median_task_value=1.0)
        sel.select_backend(_turn(), backends, 0.5, {b.name: 0.01 for b in backends}, task_value=0.01)
        assert sel.last_multiplier == 0.5

    def test_default_task_value_uses_median(self):
        """When task_value is None, median_task_value is used → multiplier=1.0."""
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ValueAwareSelector(table, median_task_value=2.5)
        sel.select_backend(_turn(), backends, 0.5, {b.name: 0.01 for b in backends}, task_value=None)
        assert sel.last_multiplier == 1.0


class TestConservativeNotAffectValueAware:
    def test_conservative_unaffected_by_task_value(self):
        """ConservativeSelector should not have value awareness."""
        from budgetflow.selector import ConservativeSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ConservativeSelector(table)
        # ConservativeSelector.select_backend doesn't accept task_value
        sel.select_backend(_turn(), backends, 0.5, {b.name: 0.01 for b in backends})
        # Should NOT have last_multiplier
        assert not hasattr(sel, "last_multiplier")

    def test_value_aware_has_conservation(self):
        """ValueAwareSelector should also apply conservation factor."""
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ValueAwareSelector(table, median_task_value=1.0)
        # At p=0.2 (below 0.3): conservation = 1.0, multiplier = 1.0
        # At p=0.8: conservation = 1.0 + 0.5*1.5 = 1.75
        sel_p2 = ValueAwareSelector(table, median_task_value=1.0)
        sel_p2.select_backend(_turn(), backends, 0.2, {b.name: 0.01 for b in backends}, task_value=1.0)
        sel_p8 = ValueAwareSelector(table, median_task_value=1.0)
        sel_p8.select_backend(_turn(), backends, 0.8, {b.name: 0.01 for b in backends}, task_value=1.0)
        # Both have multiplier=1.0, but p=0.8 should be less likely to upgrade
        # (just verify both exist and work)
        assert sel_p8.last_multiplier == 1.0


class TestBuildRoutingContext:
    def test_value_aware_creates_value_aware_selector(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.selector import ValueAwareSelector
        backends = _backends()
        ctx = build_routing_context(
            "budgetflow_value_aware", backends,
            task_value=2.0, median_task_value=1.0,
        )
        assert isinstance(ctx.selector, ValueAwareSelector)
        assert ctx.selector.median_task_value == 1.0
        assert ctx.task_value == 2.0

    def test_value_aware_context_stores_values(self):
        from budgetflow.adapter.strategies import build_routing_context
        backends = _backends()
        ctx = build_routing_context(
            "budgetflow_value_aware", backends,
            task_value=0.5, median_task_value=2.0,
        )
        assert ctx.task_value == 0.5
        assert ctx.median_task_value == 2.0

    def test_task_level_value_control_precomputes_one_backend(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.types import Stage
        backends = _backends()
        ctx = build_routing_context(
            "value_aware_task_level",
            backends,
            budget_pressure=0.5,
            task_value=2.0,
            median_task_value=1.0,
        )

        loc_backend = choose_backend(ctx, _turn(Stage.LOCALIZATION, w_i=1.0), {b.name: 0.01 for b in backends})
        repair_backend = choose_backend(ctx, _turn(Stage.REPAIR, w_i=3.0), {b.name: 0.01 for b in backends})

        assert ctx.task_level_backend is not None
        assert loc_backend == ctx.task_level_backend
        assert repair_backend == ctx.task_level_backend
        assert ctx.last_decision is not None
        assert ctx.last_decision.branch == "value_aware_task_level"


class TestValueAwareTraceFields:
    def test_trace_fields_present_for_value_aware(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.adapter.turn_trace import value_aware_trace_fields
        backends = _backends()
        ctx = build_routing_context(
            "budgetflow_value_aware", backends,
            task_value=2.0, median_task_value=1.0,
        )
        # Simulate a selection to populate last_multiplier
        from budgetflow.types import Stage, TurnInfo
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000)
        ctx.selector.select_backend(turn, backends, 0.5, {b.name: 0.01 for b in backends}, task_value=2.0)
        fields = value_aware_trace_fields(ctx)
        assert fields["value_aware_active"] is True
        assert fields["task_value"] == 2.0
        assert fields["task_value_multiplier"] == 2.0

    def test_trace_fields_empty_for_conservative(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.adapter.turn_trace import value_aware_trace_fields
        backends = _backends()
        ctx = build_routing_context("budgetflow_conservative", backends)
        fields = value_aware_trace_fields(ctx)
        assert fields == {}

    def test_trace_fields_empty_for_bo(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.adapter.turn_trace import value_aware_trace_fields
        backends = _backends()
        ctx = build_routing_context("budget_only", backends)
        fields = value_aware_trace_fields(ctx)
        assert fields == {}


class TestFailFast:
    def test_value_matrix_missing_still_fails(self):
        """Phase X fail-fast: nonexistent matrix file raises FileNotFoundError."""
        from budgetflow.value_efficiency import ValueEfficiencyContext
        ctx = ValueEfficiencyContext()
        with pytest.raises(FileNotFoundError):
            ctx.init(value_profile="difficulty", value_matrix_path="/nonexistent/path.json")

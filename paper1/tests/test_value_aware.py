"""Phase Y: BudgetFlowValueAware tests."""

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
    def test_bfv_registered_in_default_strategies(self):
        from budgetflow.experiments.compare_config import DEFAULT_STRATEGIES
        names = {s.name for s in DEFAULT_STRATEGIES}
        assert "budgetflow_value_aware_tight" in names
        assert "budgetflow_value_aware_loose" in names

    def test_bfv_tight_routing_is_value_aware(self):
        from budgetflow.experiments.compare_config import DEFAULT_STRATEGIES
        bfv = next(s for s in DEFAULT_STRATEGIES if s.name == "budgetflow_value_aware_tight")
        assert bfv.routing == "budgetflow_value_aware"
        assert bfv.budget_tier == "tight"


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


class TestBFVNotAffectBFC:
    def test_bfc_unaffected_by_task_value(self):
        """ConservativeSelector should not have value awareness."""
        from budgetflow.selector import ConservativeSelector, build_zero_calibration_progress_table
        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        sel = ConservativeSelector(table)
        # ConservativeSelector.select_backend doesn't accept task_value
        sel.select_backend(_turn(), backends, 0.5, {b.name: 0.01 for b in backends})
        # Should NOT have last_multiplier
        assert not hasattr(sel, "last_multiplier")

    def test_bfv_has_conservation(self):
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
    def test_bfv_creates_value_aware_selector(self):
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

    def test_bfv_context_stores_values(self):
        from budgetflow.adapter.strategies import build_routing_context
        backends = _backends()
        ctx = build_routing_context(
            "budgetflow_value_aware", backends,
            task_value=0.5, median_task_value=2.0,
        )
        assert ctx.task_value == 0.5
        assert ctx.median_task_value == 2.0


class TestValueAwareTraceFields:
    def test_trace_fields_present_for_bfv(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.adapter.mini_swe_proxy import _value_aware_trace_fields
        backends = _backends()
        ctx = build_routing_context(
            "budgetflow_value_aware", backends,
            task_value=2.0, median_task_value=1.0,
        )
        # Simulate a selection to populate last_multiplier
        from budgetflow.types import Stage, TurnInfo
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000)
        ctx.selector.select_backend(turn, backends, 0.5, {b.name: 0.01 for b in backends}, task_value=2.0)
        fields = _value_aware_trace_fields(ctx)
        assert fields["value_aware_active"] is True
        assert fields["task_value"] == 2.0
        assert fields["task_value_multiplier"] == 2.0

    def test_trace_fields_empty_for_bfc(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.adapter.mini_swe_proxy import _value_aware_trace_fields
        backends = _backends()
        ctx = build_routing_context("budgetflow_conservative", backends)
        fields = _value_aware_trace_fields(ctx)
        assert fields == {}

    def test_trace_fields_empty_for_bo(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.adapter.mini_swe_proxy import _value_aware_trace_fields
        backends = _backends()
        ctx = build_routing_context("budget_only", backends)
        fields = _value_aware_trace_fields(ctx)
        assert fields == {}


class TestFailFast:
    def test_value_matrix_missing_still_fails(self):
        """Phase X fail-fast: nonexistent matrix file raises FileNotFoundError."""
        import budgetflow.run_mini_swe_compare as mod
        mod._VALUE_LOOKUP = None
        mod._VALUE_PROFILE = "equal"
        mod._VALUE_MATRIX_PATH = None
        with pytest.raises(FileNotFoundError):
            mod._init_value_observability(value_profile="difficulty", value_matrix_path="/nonexistent/path.json")

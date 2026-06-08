"""PolicyBackend interface and BootstrapPolicy contract tests.

Proves the runtime path goes through BootstrapPolicy, not only that the
class can be instantiated.
"""

import sys

import pytest

sys.path.insert(0, "src")


def _backends():
    from budgetflow.types import Backend

    return [
        Backend("tier1", 1, 0.0005, 0.001, 200, 20, 300, 0.3, 300),
        Backend("tier2", 2, 0.001, 0.005, 100, 10, 500, 0.5, 500),
        Backend("tier3", 3, 0.010, 0.050, 50, 5, 1000, 0.8, 2000),
    ]


def _turn(stage=None, w_i=0.4):
    from budgetflow.types import Stage, TurnInfo

    return TurnInfo(
        workflow_id="test",
        step_index=1,
        stage=stage or Stage.LOCALIZATION,
        w_i=w_i,
        context_len=1000,
    )


class TestPolicyBackendInterface:
    def test_bootstrap_policy_is_policy_backend(self):
        from budgetflow.policy_backend import BootstrapPolicy, PolicyBackend
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        selector = BudgetFlowSelector(table)
        policy = BootstrapPolicy(selector)
        assert isinstance(policy, PolicyBackend)

    def test_bootstrap_policy_estimate_cap_is_pass_through(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        policy = BootstrapPolicy(BudgetFlowSelector(table))

        # Not yet wired into runtime; must return budget_remaining unchanged.
        cap = policy.estimate_cap("task-a", 2.0, 0.75, 1.0)
        assert cap == 0.75

    def test_bootstrap_policy_choose_backend(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        policy = BootstrapPolicy(BudgetFlowSelector(table))

        decision = policy.choose_backend(
            _turn(), backends, budget_pressure=0.01,
            expected_costs={b.name: 0.01 for b in backends},
        )
        assert decision.backend in ("tier1", "tier2", "tier3")
        assert decision.reason != ""
        assert isinstance(decision.scores, dict)

    def test_bootstrap_policy_stores_last_decision(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        policy = BootstrapPolicy(BudgetFlowSelector(table))

        assert policy.last_decision is None
        decision = policy.choose_backend(
            _turn(), backends, budget_pressure=0.01,
            expected_costs={b.name: 0.01 for b in backends},
        )
        assert policy.last_decision is decision

    def test_bootstrap_policy_should_stop_on_exhausted_budget(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        policy = BootstrapPolicy(BudgetFlowSelector(table))

        assert policy.should_stop("task-a", 0.0, 1.0, 5) is True

    def test_bootstrap_policy_should_continue_with_budget(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        policy = BootstrapPolicy(BudgetFlowSelector(table))

        assert policy.should_stop("task-a", 0.3, 1.0, 5) is False

    def test_bootstrap_policy_should_escalate_on_prolonged_stall(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        policy = BootstrapPolicy(BudgetFlowSelector(table))

        assert policy.should_escalate("task-a", "tier2", 0, 8) is True

    def test_bootstrap_policy_should_not_escalate_when_making_progress(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import BudgetFlowSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        policy = BootstrapPolicy(BudgetFlowSelector(table))

        assert policy.should_escalate("task-a", "tier2", 3, 2) is False


class TestBootstrapValueAwarePolicy:
    def test_value_aware_policy_passes_task_value(self):
        from budgetflow.policy_backend import BootstrapPolicy
        from budgetflow.selector import ValueAwareSelector, build_zero_calibration_progress_table

        backends = _backends()
        table = build_zero_calibration_progress_table(backends)
        selector = ValueAwareSelector(table, median_task_value=1.0)
        policy = BootstrapPolicy(selector)

        decision = policy.choose_backend(
            _turn(), backends, budget_pressure=0.5,
            expected_costs={b.name: 0.01 for b in backends},
            task_value=2.0,
        )
        assert decision.backend in ("tier1", "tier2", "tier3")
        assert selector.last_multiplier > 1.0


class TestBootstrapPolicyWiredIntoRouting:
    """Prove that build_routing_context wires BootstrapPolicy for budgetflow
    strategies and that choose_backend routes through it."""

    def test_budgetflow_full_has_bootstrap_policy(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.policy_backend import BootstrapPolicy

        backends = _backends()
        ctx = build_routing_context("budgetflow_full", backends)
        assert ctx.bootstrap_policy is not None
        assert isinstance(ctx.bootstrap_policy, BootstrapPolicy)

    def test_budgetflow_conservative_has_bootstrap_policy(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.policy_backend import BootstrapPolicy

        backends = _backends()
        ctx = build_routing_context("budgetflow_conservative", backends)
        assert ctx.bootstrap_policy is not None
        assert isinstance(ctx.bootstrap_policy, BootstrapPolicy)

    def test_budgetflow_value_aware_has_bootstrap_policy(self):
        from budgetflow.adapter.strategies import build_routing_context
        from budgetflow.policy_backend import BootstrapPolicy

        backends = _backends()
        ctx = build_routing_context("budgetflow_value_aware", backends, task_value=2.0)
        assert ctx.bootstrap_policy is not None
        assert isinstance(ctx.bootstrap_policy, BootstrapPolicy)

    def test_choose_backend_sets_last_policy_decision(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.policy_backend import PolicyDecision
        from budgetflow.types import Stage, TurnInfo

        backends = _backends()
        ctx = build_routing_context("budgetflow_conservative", backends)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000)
        backend = choose_backend(ctx, turn, {b.name: 0.01 for b in backends})
        assert backend is not None
        # Must set last_policy_decision when routing through BootstrapPolicy.
        # Note: max-tier gating may override the policy choice, so
        # last_policy_decision.backend may differ from the returned backend.
        assert ctx.last_policy_decision is not None
        assert isinstance(ctx.last_policy_decision, PolicyDecision)
        assert ctx.last_policy_decision.backend in {b.name for b in backends}
        assert backend.name in {b.name for b in backends}

    def test_choose_backend_requires_policy_for_budgetflow_strategies(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.types import Stage, TurnInfo

        backends = _backends()
        ctx = build_routing_context("budgetflow_conservative", backends)
        ctx.bootstrap_policy = None
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000)

        with pytest.raises(RuntimeError, match="requires a BootstrapPolicy"):
            choose_backend(ctx, turn, {b.name: 0.01 for b in backends})

    def test_choose_backend_preserves_router_decision_semantics(self):
        """RouterDecision fields must stay intact for trace compatibility."""
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.selector import RouterDecision
        from budgetflow.types import Stage, TurnInfo

        backends = _backends()
        ctx = build_routing_context("budgetflow_full", backends)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000)
        backend = choose_backend(ctx, turn, {b.name: 0.01 for b in backends})
        assert backend is not None
        rd = ctx.last_decision
        assert isinstance(rd, RouterDecision)
        assert rd.backend == backend
        assert rd.branch in ("budgetflow_full", "budgetflow_conservative", "budgetflow_value_aware")
        assert rd.pressure is not None
        assert rd.reason != ""

    def test_value_aware_routing_sets_task_value_in_policy_decision(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.types import Stage, TurnInfo

        backends = _backends()
        ctx = build_routing_context("budgetflow_value_aware", backends, task_value=4.0, median_task_value=2.0)
        turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.LOCALIZATION, w_i=0.4, context_len=1000)
        backend = choose_backend(ctx, turn, {b.name: 0.01 for b in backends})
        # Value-aware selector must apply multiplier > 1.0 for high-value task
        assert ctx.selector.last_multiplier > 1.0
        assert backend is not None


class TestWorkflowSegmentTypes:
    def test_workflow_segment_construction(self):
        from budgetflow.types import WorkflowSegment

        ws = WorkflowSegment(name="Context", signals={"feature_a": 0.5})
        assert ws.name == "Context"
        assert ws.signals["feature_a"] == 0.5

    def test_workflow_segment_factories(self):
        from budgetflow.types import WorkflowSegment

        ctx = WorkflowSegment.context()
        act = WorkflowSegment.action()
        ver = WorkflowSegment.verification()

        assert ctx.name == "Context"
        assert act.name == "Action"
        assert ver.name == "Verification"


class TestSegmentAdapter:
    def test_localization_maps_to_context(self):
        from budgetflow.adapters.swebench_segment import SwebenchSegmentAdapter
        from budgetflow.types import Stage, WorkflowSegment

        adapter = SwebenchSegmentAdapter()
        segment = adapter.to_segment(Stage.LOCALIZATION)
        assert segment.name == WorkflowSegment.CONTEXT

    def test_repair_maps_to_action(self):
        from budgetflow.adapters.swebench_segment import SwebenchSegmentAdapter
        from budgetflow.types import Stage, WorkflowSegment

        adapter = SwebenchSegmentAdapter()
        segment = adapter.to_segment(Stage.REPAIR)
        assert segment.name == WorkflowSegment.ACTION

    def test_validation_maps_to_verification(self):
        from budgetflow.adapters.swebench_segment import SwebenchSegmentAdapter
        from budgetflow.types import Stage, WorkflowSegment

        adapter = SwebenchSegmentAdapter()
        segment = adapter.to_segment(Stage.VALIDATION)
        assert segment.name == WorkflowSegment.VERIFICATION

    def test_roundtrip_stage_to_segment_to_stage(self):
        from budgetflow.adapters.swebench_segment import SwebenchSegmentAdapter
        from budgetflow.types import Stage

        adapter = SwebenchSegmentAdapter()
        for stage in Stage:
            segment = adapter.to_segment(stage)
            back = adapter.to_stage(segment)
            assert back == stage, f"Roundtrip failed for {stage}: got {back}"

    def test_segment_from_stage_convenience(self):
        from budgetflow.adapters.swebench_segment import segment_from_stage
        from budgetflow.types import Stage, WorkflowSegment

        segment = segment_from_stage(Stage.REPAIR, priority="high")
        assert segment.name == WorkflowSegment.ACTION
        assert segment.signals["priority"] == "high"


class TestValueAdapter:
    def test_equal_profile_returns_one(self):
        from budgetflow.adapters.swebench_value import SwebenchValueAdapter

        adapter = SwebenchValueAdapter(value_profile="equal")
        estimate = adapter.estimate("task-a")
        assert estimate.value == 1.0
        assert estimate.source == "default_equal"

    def test_median_default_is_one(self):
        from budgetflow.adapters.swebench_value import SwebenchValueAdapter

        adapter = SwebenchValueAdapter(value_profile="equal")
        assert adapter.median_task_value == 1.0

    def test_equal_profile_allows_any_task(self):
        """Equal profile must safely return 1.0 for any task without a matrix."""
        from budgetflow.adapters.swebench_value import SwebenchValueAdapter

        adapter = SwebenchValueAdapter(value_profile="equal")
        value, source = adapter.task_value("nonexistent-task")
        assert value == 1.0
        assert source == "default_equal"

    def test_non_equal_profile_missing_task_fails_fast(self):
        """Non-equal profiles must not silently fallback when task is missing."""
        from budgetflow.adapters.swebench_value import SwebenchValueAdapter

        adapter = SwebenchValueAdapter(value_profile="difficulty")
        with pytest.raises(ValueError, match="not found in value matrix"):
            adapter.estimate("nonexistent-task")

    def test_non_equal_profile_missing_in_lookup_fails_fast(self):
        """When a matrix is loaded but task is absent, non-equal must fail."""
        import json
        import tempfile
        import os
        from budgetflow.adapters.swebench_value import SwebenchValueAdapter

        matrix = {
            "tasks": {
                "task-a": {"values": {"difficulty": 2.5}},
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(matrix, f)
            path = f.name
        try:
            adapter = SwebenchValueAdapter(value_profile="difficulty", value_matrix_path=path)
            # task-a is in the matrix; should work
            est = adapter.estimate("task-a")
            assert est.value == 2.5
            # task-b is NOT in the matrix; must fail
            with pytest.raises(ValueError, match="not found in value matrix"):
                adapter.estimate("task-b")
        finally:
            os.unlink(path)


class TestCostAdapter:
    def test_cost_estimate_for_known_backend(self):
        from budgetflow.adapters.swebench_cost import SwebenchCostAdapter

        adapter = SwebenchCostAdapter()
        estimate = adapter.estimate("tier2", input_tokens=1000, expected_output_tokens=500)
        assert estimate.usd > 0
        assert "tier_catalog" in estimate.source

    def test_cost_estimate_for_unknown_backend_fails_fast(self):
        """Unknown backend must fail fast, not silently return zero cost."""
        from budgetflow.adapters.swebench_cost import SwebenchCostAdapter

        adapter = SwebenchCostAdapter()
        with pytest.raises(ValueError, match="unknown backend"):
            adapter.estimate("nonexistent_backend", input_tokens=1000, expected_output_tokens=500)

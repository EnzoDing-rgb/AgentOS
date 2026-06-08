"""Tests for frozen router plan and mechanism-first strategies."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


_SAMPLE_PLAN = {
    "meta": {"name": "test_plan", "created": "2026-06-08"},
    "plan": {
        "task_a": {"preferred_model": "tier2", "base_cap": 0.30, "priority": 1},
        "task_b": {"preferred_model": "tier3", "base_cap": 0.50, "priority": 2},
    },
}


class TestFrozenRouterPlan:
    def test_load_from_file(self):
        from budgetflow.frozen_router import FrozenRouterPlan, load_frozen_plan

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(_SAMPLE_PLAN, f)
            tmp = Path(f.name)
        try:
            plan = load_frozen_plan(tmp)
            assert isinstance(plan, FrozenRouterPlan)
            assert plan.name == "test_plan"
            assert len(plan.plan) == 2
        finally:
            tmp.unlink()

    def test_lookup_found(self):
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan

        plan = FrozenRouterPlan(
            name="test",
            plan={
                "task_a": FrozenPlanEntry("task_a", "tier2", 0.3, 1),
                "task_b": FrozenPlanEntry("task_b", "tier3", 0.5, 2),
            },
        )
        entry = plan.lookup("task_a")
        assert entry is not None
        assert entry.preferred_model == "tier2"
        assert entry.base_cap == 0.3
        assert entry.priority == 1

    def test_lookup_missing(self):
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan

        plan = FrozenRouterPlan(
            name="test",
            plan={"task_a": FrozenPlanEntry("task_a", "tier2", 0.3, 1)},
        )
        assert plan.lookup("unknown") is None

    def test_as_jsonl_record(self):
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan

        plan = FrozenRouterPlan(
            name="test",
            plan={"task_a": FrozenPlanEntry("task_a", "tier2", 0.3, 1)},
        )
        rec = plan.as_jsonl_record("task_a")
        assert rec["frozen_plan_name"] == "test"
        assert rec["frozen_plan_preferred_model"] == "tier2"
        assert rec["frozen_plan_base_cap"] == 0.3
        assert rec["frozen_plan_priority"] == 1

    def test_as_jsonl_record_missing(self):
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan

        plan = FrozenRouterPlan(
            name="test",
            plan={"task_a": FrozenPlanEntry("task_a", "tier2", 0.3, 1)},
        )
        rec = plan.as_jsonl_record("unknown")
        assert rec["frozen_plan_name"] == "test"
        assert rec["frozen_plan_entry"] is None

    def test_load_tasks_alias(self):
        from budgetflow.frozen_router import FrozenRouterPlan, load_frozen_plan

        data = {
            "meta": {"name": "tasks_alias"},
            "tasks": {
                "x": {"preferred_model": "tier1", "base_cap": 0.1, "priority": 1},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp = Path(f.name)
        try:
            plan = load_frozen_plan(tmp)
            assert plan.lookup("x") is not None
        finally:
            tmp.unlink()


class TestMechanismStrategiesRegistered:
    def test_all_three_in_catalog(self):
        from budgetflow.experiments.compare_config import strategy_catalog

        names = {s.name for s in strategy_catalog()}
        assert "bare_strong_model" in names
        assert "enterprise_router_baseline" in names
        assert "budgetflow_same_router" in names

    def test_mechanism_names_helper(self):
        from budgetflow.experiments.compare_config import mechanism_strategy_names

        names = mechanism_strategy_names()
        assert names == {"bare_strong_model", "enterprise_router_baseline", "budgetflow_same_router"}


class TestFrozenPlanRouting:
    def _backends(self):
        from budgetflow.types import Backend

        return [
            Backend("tier2", 2, 0.001, 0.005, 100, 10, 500, 0.5, 500),
            Backend("tier3", 3, 0.010, 0.050, 50, 5, 1000, 0.8, 2000),
        ]

    def test_enterprise_router_uses_frozen_plan(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan
        from budgetflow.types import Stage, TurnInfo

        plan = FrozenRouterPlan(
            name="test",
            plan={"test_task": FrozenPlanEntry("test_task", "tier3", 0.5, 2)},
        )
        ctx = build_routing_context(
            "enterprise_router",
            self._backends(),
            budget_pressure=0.1,
            frozen_plan=plan,
        )
        turn = TurnInfo(
            workflow_id="test_task", step_index=1,
            stage=Stage.REPAIR, w_i=1.0, context_len=1000,
        )
        backend = choose_backend(ctx, turn, {"tier2": 0.01, "tier3": 0.05})
        assert backend.tier == 3
        assert ctx.last_decision.branch == "enterprise_router"

    def test_bare_strong_ignores_frozen_plan(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan
        from budgetflow.types import Stage, TurnInfo

        plan = FrozenRouterPlan(
            name="test",
            plan={"test_task": FrozenPlanEntry("test_task", "tier2", 0.3, 1)},
        )
        ctx = build_routing_context(
            "bare_strong",
            self._backends(),
            budget_pressure=0.1,
            frozen_plan=plan,
        )
        turn = TurnInfo(
            workflow_id="test_task", step_index=1,
            stage=Stage.REPAIR, w_i=1.0, context_len=1000,
        )
        backend = choose_backend(ctx, turn, {"tier2": 0.01, "tier3": 0.05})
        # bare_strong always picks strongest
        assert backend.tier == 3
        assert ctx.last_decision.branch == "bare_strong"

    def test_budgetflow_same_router_keeps_frozen_plan_model(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan
        from budgetflow.types import Backend, Stage, TurnInfo

        # Use 3 backends so second_cheapest is tier2, strongest is tier3
        backends = [
            Backend("tier1", 1, 0.0001, 0.0005, 200, 20, 300, 0.2, 200),
            Backend("tier2", 2, 0.001, 0.005, 100, 10, 500, 0.5, 500),
            Backend("tier3", 3, 0.010, 0.050, 50, 5, 1000, 0.8, 2000),
        ]
        plan = FrozenRouterPlan(
            name="test",
            plan={"test_task": FrozenPlanEntry("test_task", "tier3", 0.5, 2)},
        )
        ctx = build_routing_context(
            "budgetflow_same_router",
            backends,
            budget_pressure=0.1,
            frozen_plan=plan,
        )
        turn = TurnInfo(
            workflow_id="test_task", step_index=1,
            stage=Stage.REPAIR, w_i=1.0, context_len=1000,
        )
        backend = choose_backend(ctx, turn, {b.name: 0.01 for b in backends})
        assert ctx.last_decision.branch == "budgetflow_same_router"
        assert backend.tier == 3

    def test_frozen_plan_missing_entry_falls_back_to_cheapest(self):
        from budgetflow.adapter.strategies import build_routing_context, choose_backend
        from budgetflow.frozen_router import FrozenPlanEntry, FrozenRouterPlan
        from budgetflow.types import Stage, TurnInfo

        plan = FrozenRouterPlan(name="test", plan={})
        ctx = build_routing_context(
            "enterprise_router",
            self._backends(),
            budget_pressure=0.1,
            frozen_plan=plan,
        )
        turn = TurnInfo(
            workflow_id="unknown_task", step_index=1,
            stage=Stage.REPAIR, w_i=1.0, context_len=1000,
        )
        backend = choose_backend(ctx, turn, {"tier2": 0.01, "tier3": 0.05})
        assert backend.tier == 2  # cheapest

    def test_observability_policy_kind_for_new_strategies(self):
        from budgetflow.experiment_observability import enrich_routing_observability

        record = {"routing": "bare_strong"}
        enrich_routing_observability(record)
        assert record["policy_kind"] == "bare_harness"
        assert record["policy_role"] == "bare_strongest_baseline"

        record = {"routing": "enterprise_router"}
        enrich_routing_observability(record)
        assert record["policy_kind"] == "bare_harness"
        assert record["policy_role"] == "enterprise_router_baseline"

        record = {"routing": "budgetflow_same_router"}
        enrich_routing_observability(record)
        assert record["policy_kind"] == "mechanism"
        assert record["policy_role"] == "mechanism_with_frozen_router"

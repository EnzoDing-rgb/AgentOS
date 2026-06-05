"""Phase V focused tests: BudgetOnlyT2Router + ConservativeSelector."""

import sys

import pytest

sys.path.insert(0, "src")

from budgetflow.adapter.strategies import build_routing_context, choose_backend
from budgetflow.policies import BudgetOnlyStepRouter, BudgetOnlyT2Router
from budgetflow.selector import BudgetFlowSelector, ConservativeSelector, SelectionDecision
from budgetflow.types import Backend, ProgressTable, Stage, TurnInfo


def _make_backends(n: int = 3) -> list[Backend]:
    configs = [
        ("flash", 1, 0.0, 0.0),
        ("plus", 2, 0.005, 0.015),
        ("pro", 3, 0.02, 0.06),
    ]
    return [
        Backend(
            name=name, tier=tier, cost_per_input_token=cin, cost_per_output_token=cout,
            rpm_limit=100, concurrency_limit=10, mean_output_tokens=4096 * tier,
            progress_score=0.3 * tier, latency_ms=200 * tier,
        )
        for name, tier, cin, cout in configs[:n]
    ]


def _dummy_turn(stage=Stage.REPAIR, w_i=1.0) -> TurnInfo:
    return TurnInfo(workflow_id="test", step_index=1, stage=stage, w_i=w_i, context_len=5000, tool_name="bash")


def _dummy_progress_table(backends: list[Backend]) -> ProgressTable:
    return {
        Stage.LOCALIZATION: {b.name: 0.1 * b.tier for b in backends},
        Stage.REPAIR: {b.name: 0.05 * b.tier for b in backends},
        Stage.VALIDATION: {b.name: 0.15 * b.tier for b in backends},
    }


# ── BudgetOnlyT2Router ──────────────────────────────────────────────

class TestBudgetOnlyT2Router:
    def test_always_cheapest_tier(self):
        """BudgetOnlyT2Router never escalates, always picks lowest tier."""
        router = BudgetOnlyT2Router()
        backends = _make_backends(3)
        turn = _dummy_turn()
        for pressure in (0.0, 0.01, 0.2, 0.5, 0.8, 1.0, 1.5):
            decision = router.choose_backend(turn, backends, budget_pressure=pressure)
            assert decision.backend.tier == 1, f"p={pressure}: expected T1, got tier {decision.backend.tier}"
            assert decision.branch == "budget_only_t2"

    def test_works_with_two_backends(self):
        router = BudgetOnlyT2Router()
        backends = _make_backends(2)
        decision = router.choose_backend(_dummy_turn(), backends, budget_pressure=0.0)
        assert decision.backend.tier == 1

    def test_works_with_single_backend(self):
        router = BudgetOnlyT2Router()
        backends = _make_backends(1)
        decision = router.choose_backend(_dummy_turn(), backends, budget_pressure=0.0)
        assert decision.backend.tier == 1


# ── ConservativeSelector vs BudgetFlowSelector ──────────────────────

class TestConservativeVsBudgetFlow:
    def test_identical_at_zero_pressure(self):
        """At p=0, both selectors should pick the default (T1, no upgrade)."""
        bt = _make_backends(3)
        table = _dummy_progress_table(bt)
        bf = BudgetFlowSelector(table)
        cons = ConservativeSelector(table)
        turn = _dummy_turn()
        costs = {b.name: b.tier * 0.02 for b in bt}
        bf_sel = bf.select_backend(turn, bt, budget_pressure=0.0, expected_costs=costs)
        cons_sel = cons.select_backend(turn, bt, budget_pressure=0.0, expected_costs=costs)
        assert bf_sel.backend.tier == cons_sel.backend.tier

    def test_conservative_more_restrained_at_high_pressure(self):
        """At p=0.8, conservative should be at MOST as aggressive as full."""
        bt = _make_backends(3)
        table = _dummy_progress_table(bt)
        bf = BudgetFlowSelector(table)
        cons = ConservativeSelector(table)
        turn = _dummy_turn()
        costs = {b.name: b.tier * 0.02 for b in bt}
        bf_sel = bf.select_backend(turn, bt, budget_pressure=0.8, expected_costs=costs)
        cons_sel = cons.select_backend(turn, bt, budget_pressure=0.8, expected_costs=costs)
        # Conservative should never go to a HIGHER tier than full at same pressure
        assert cons_sel.backend.tier <= bf_sel.backend.tier, (
            f"Conservative (tier {cons_sel.backend.tier}) should not exceed "
            f"BudgetFlow Full (tier {bf_sel.backend.tier}) at p=0.8"
        )

    def test_no_conservation_below_03(self):
        """Below p=0.3, conservation factor is 1.0 (no change)."""
        bt = _make_backends(3)
        table = _dummy_progress_table(bt)
        bf = BudgetFlowSelector(table)
        cons = ConservativeSelector(table)
        turn = _dummy_turn()
        costs = {b.name: b.tier * 0.02 for b in bt}
        for p in (0.0, 0.1, 0.2, 0.29):
            bf_sel = bf.select_backend(turn, bt, budget_pressure=p, expected_costs=costs)
            cons_sel = cons.select_backend(turn, bt, budget_pressure=p, expected_costs=costs)
            assert bf_sel.backend.tier == cons_sel.backend.tier, (
                f"Should be identical at p={p} (below 0.3)"
            )

    def test_conservation_grows_with_pressure(self):
        """At p=1.0, conservation factor ≈3.1, making T3 very hard."""
        bt = _make_backends(3)
        table = _dummy_progress_table(bt)
        cons = ConservativeSelector(table)
        turn = _dummy_turn()
        costs = {b.name: b.tier * 0.02 for b in bt}
        sel = cons.select_backend(turn, bt, budget_pressure=1.0, expected_costs=costs)
        # At p=1.0 with dummy progress, the large delta_cost should prevent T3
        assert sel.backend.tier <= 2, (
            f"Conservative at p=1.0 should resist T3 escalation, got tier {sel.backend.tier}"
        )

    def test_negative_delta_cost_always_upgrades(self):
        """If delta_cost <= 0, always upgrade regardless of conservation."""
        bt = _make_backends(3)
        table = _dummy_progress_table(bt)
        cons = ConservativeSelector(table)
        turn = _dummy_turn()
        # Make T2 cheaper than T1 — selector checks T1→T2 first
        costs = {"flash": 0.10, "plus": 0.05, "pro": 0.03}
        sel = cons.select_backend(turn, bt, budget_pressure=1.0, expected_costs=costs)
        # T2 is cheaper than T1 → immediate upgrade to T2. Then T3 cheaper than T2 → upgrade to T3.
        assert sel.backend.tier == 3, (
            f"Negative delta_cost should force upgrade through tiers, got tier {sel.backend.tier}"
        )


# ── Strategy dispatch ───────────────────────────────────────────────

class TestNewStrategyDispatch:
    def test_budget_only_t2_strategy(self):
        bt = _make_backends(3)
        ctx = build_routing_context("budget_only_t2", bt, budget_pressure=0.01)
        turn = _dummy_turn()
        costs = {b.name: b.tier * 0.02 for b in bt}
        backend = choose_backend(ctx, turn, expected_costs=costs)
        assert backend.tier == 1
        assert ctx.last_decision.branch == "budget_only_t2"

    def test_budget_only_t2_strategy_high_pressure(self):
        bt = _make_backends(3)
        ctx = build_routing_context("budget_only_t2", bt, budget_pressure=0.9)
        turn = _dummy_turn()
        costs = {b.name: b.tier * 0.02 for b in bt}
        backend = choose_backend(ctx, turn, expected_costs=costs)
        assert backend.tier == 1  # Never escalates

    def test_budgetflow_conservative_strategy(self):
        bt = _make_backends(3)
        ctx = build_routing_context("budgetflow_conservative", bt, budget_pressure=0.3)
        turn = _dummy_turn()
        costs = {b.name: b.tier * 0.02 for b in bt}
        backend = choose_backend(ctx, turn, expected_costs=costs)
        assert ctx.last_decision.branch == "budgetflow_conservative"

    def test_budgetflow_conservative_uses_conservative_selector(self):
        bt = _make_backends(3)
        ctx = build_routing_context("budgetflow_conservative", bt, budget_pressure=0.5)
        from budgetflow.selector import ConservativeSelector
        assert isinstance(ctx.selector, ConservativeSelector)

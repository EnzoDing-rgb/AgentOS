"""Tests for task-level expected-total-cost tier selection.

Verifies the generalizable mechanism: task-level tier choice compares
expected total cost (not per-step cost), so a weaker tier that needs many
more turns is correctly seen as more expensive in total.
"""

from __future__ import annotations

import math
import sys

import pytest

sys.path.insert(0, "src")


# ── helpers ────────────────────────────────────────────────────────────────


def _backends(
    t2_progress=0.24,
    t3_progress=0.25,
    t2_cost_input=0.0009,
    t2_cost_output=0.0045,
    t3_cost_input=0.0045,
    t3_cost_output=0.0225,
    t2_tier=2,
    t3_tier=3,
):
    from budgetflow.types import Backend

    return [
        Backend(
            name="tier2",
            tier=t2_tier,
            cost_per_input_token=t2_cost_input,
            cost_per_output_token=t2_cost_output,
            rpm_limit=100,
            concurrency_limit=20,
            mean_output_tokens=1024,
            progress_score=t2_progress,
            latency_ms=4200,
        ),
        Backend(
            name="tier3",
            tier=t3_tier,
            cost_per_input_token=t3_cost_input,
            cost_per_output_token=t3_cost_output,
            rpm_limit=100,
            concurrency_limit=20,
            mean_output_tokens=1024,
            progress_score=t3_progress,
            latency_ms=1200,
        ),
    ]


def _three_backends():
    from budgetflow.types import Backend

    return [
        Backend("tier1", 1, 0.0003, 0.0015, 100, 20, 768, 0.15, 500),
        Backend("tier2", 2, 0.0009, 0.0045, 100, 35, 1024, 0.24, 4200),
        Backend("tier3", 3, 0.0045, 0.0225, 50, 5, 1024, 0.25, 1200),
    ]


def _task_level_ctx(
    backends,
    *,
    budget_pressure=0.3,
    task_value=1.0,
    median_task_value=1.0,
    allocation=None,
):
    from budgetflow.adapter.strategies import build_routing_context

    return build_routing_context(
        "value_aware_task_level",
        list(backends),
        budget_pressure=budget_pressure,
        task_value=task_value,
        median_task_value=median_task_value,
        allocation=allocation,
    )


def _turn(stage=None, w_i=1.0):
    from budgetflow.types import Stage, TurnInfo

    return TurnInfo(
        workflow_id="test",
        step_index=1,
        stage=stage or Stage.LOCALIZATION,
        w_i=w_i,
        context_len=1000,
    )


def _per_turn_costs(backends):
    """Approximate per-turn costs for each backend."""
    return {
        b.name: b.cost_per_input_token * 2000 + b.cost_per_output_token * b.mean_output_tokens
        for b in backends
    }


def _runtime_like_costs():
    return {"tier2": 0.00556, "tier3": 0.02788}


def _trusted_allocation(**kwargs):
    from budgetflow.allocation import AllocationContext

    confidence = dict(kwargs.pop("confidence", {"model_fit": "medium"}))
    kwargs.setdefault("effort_source", "unit_test")
    kwargs.setdefault("model_fit_source", "unit_test")
    return AllocationContext(confidence=confidence, **kwargs)


# ── expected-total-cost helper ─────────────────────────────────────────────


class TestExpectedTotalCost:
    def test_t2_more_expensive_in_total_when_low_fit(self):
        """When T2 model_fit is much lower than T3, expected total T2 cost > T3."""
        from budgetflow.adapter.strategies import _expected_total_cost, _tier_model_fit_rate

        # T2 fit=0.10 (very weak on this task), T3 fit=0.68 (strong)
        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=50.0,
            model_fit={"tier2": 0.10, "tier3": 0.68},
        )
        backends = _backends(t2_progress=0.10, t3_progress=0.68)
        ctx = _task_level_ctx(backends, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])

        # T2: 50/0.10 = 500 turns * per_turn_cost
        # T3: 50/0.68 ≈ 74 turns * per_turn_cost
        # T3 per-turn is ~5x T2, but T2 needs ~6.8x more turns → T2 total > T3
        assert t2_total > t3_total, (
            f"T2 expected total ${t2_total:.4f} should exceed T3 ${t3_total:.4f} "
            f"when T2 fit is much lower"
        )

    def test_t2_cheaper_in_total_when_similar_fit(self):
        """When model_fit values are similar, T2's lower per-turn price wins."""
        from budgetflow.adapter.strategies import _expected_total_cost

        alloc = _trusted_allocation(
            task_value=1.0,
            task_effort=30.0,
            model_fit={"tier2": 0.60, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.60, t3_progress=0.65)
        ctx = _task_level_ctx(backends, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])

        # Similar fit → T2 cheaper because per-turn is ~5x cheaper
        assert t2_total < t3_total, (
            f"T2 expected total ${t2_total:.4f} should be less than T3 ${t3_total:.4f} "
            f"when fits are similar"
        )

    def test_falls_back_to_catalog_progress_when_no_allocation(self):
        """Without AllocationContext, uses catalog progress_score."""
        from budgetflow.adapter.strategies import _expected_total_cost

        backends = _backends()
        ctx = _task_level_ctx(backends)
        per_turn = _per_turn_costs(backends)
        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        assert t2_total > 0
        assert math.isfinite(t2_total)

    def test_falls_back_to_frontier_runway_when_no_effort(self):
        """Without task_effort, uses frontier reference_runway_turns."""
        from budgetflow.adapter.strategies import _expected_total_cost

        backends = _backends()
        ctx = _task_level_ctx(backends)
        # ctx has tier_frontier with reference_runway_turns
        per_turn = _per_turn_costs(backends)
        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        # Frontier reference_runway_turns is 35 for default catalog
        # expected_turns = 35 / 0.24 ≈ 145.8
        # per_turn ≈ 0.0009 * 2000 + 0.0045 * 1024 ≈ 1.8 + 4.608 ≈ 6.408
        # total ≈ 145.8 * 6.408 ≈ 934
        expected_min = 100  # generous lower bound
        assert t2_total > expected_min, f"expected > ${expected_min}, got ${t2_total:.4f}"

    def test_zero_fit_guarded(self):
        """Zero model_fit rate is clamped to avoid division by zero."""
        from budgetflow.adapter.strategies import _expected_total_cost, _tier_model_fit_rate

        alloc = _trusted_allocation(
            task_effort=10.0,
            model_fit={"tier2": 0.0},
        )
        backends = _backends(t2_progress=0.0)
        ctx = _task_level_ctx(backends, allocation=alloc)
        per_turn = _per_turn_costs(backends)
        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        assert math.isfinite(t2_total)
        assert t2_total > 0


# ── task-level backend selection ───────────────────────────────────────────


class TestChooseTaskLevelBackend:
    def test_budget_plan_preferred_model_fixes_task_level_backend(self):
        """Compiler task-level model plan wins at task start and stays fixed."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
            task_level_preferred_model="tier2",
        )
        backends = _backends(t2_progress=0.08, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=alloc)

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 2
        assert ctx.task_level_backend is backend
        assert ctx.last_decision is not None
        assert ctx.last_decision.reason == "bf_task_fixed_budget_plan_model"
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.reason == "task_level_fixed_budget_plan_model"

    def test_chooses_t3_when_t2_total_cost_exceeds_t3(self):
        """Core fix: when T2 expected total cost > T3, task-level chooses T3."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        # Simulate a task where T2 has much lower fit → many more turns → higher total cost
        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.08, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.3, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        # Verify T2 total cost > T3 total cost
        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
        assert t2_total > t3_total, f"precondition: T2 total ${t2_total:.4f} > T3 ${t3_total:.4f}"

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 3, (
            f"expected T3 when T2 total cost (${t2_total:.4f}) > T3 (${t3_total:.4f}), "
            f"got {backend.name}"
        )
        assert ctx.task_level_backend is not None
        assert ctx.task_level_backend.tier == 3

    def test_chooses_t2_for_low_value_simple_task(self):
        """Low-value, low-effort task with similar fit → T2 stays cheaper."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        alloc = _trusted_allocation(
            task_value=0.5,
            task_effort=10.0,
            model_fit={"tier2": 0.60, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.60, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.3, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
        assert t2_total < t3_total, f"precondition: T2 total ${t2_total:.4f} < T3 ${t3_total:.4f}"

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 2, (
            f"expected T2 for simple task, got {backend.name}"
        )

    def test_high_value_high_effort_chooses_t3_under_budget(self):
        """High-value, high-effort task: T3 total cost dominates T2, choose T3."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        # T3 per-step is ~5x T2, so T2 needs >5x more turns for T3 to dominate.
        # t2_fit=0.10, t3_fit=0.65 → turn_ratio = 6.5x > 5x price ratio.
        alloc = _trusted_allocation(
            task_value=3.0,
            task_effort=60.0,
            model_fit={"tier2": 0.10, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.10, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.4, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
        assert t2_total > t3_total, (
            f"precondition: T2 total ${t2_total:.2f} > T3 total ${t3_total:.2f}"
        )

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 3, (
            f"expected T3 for high-value high-effort task, got {backend.name}"
        )

    def test_locks_same_backend_across_turns(self):
        """Once chosen, task_level_backend is locked for subsequent turns."""
        from budgetflow.adapter.strategies import choose_backend
        from budgetflow.types import Stage

        backends = _backends()
        ctx = _task_level_ctx(backends, budget_pressure=0.3)
        per_turn = _per_turn_costs(backends)

        loc = choose_backend(ctx, _turn(Stage.LOCALIZATION), per_turn)
        repair = choose_backend(ctx, _turn(Stage.REPAIR), per_turn)

        assert loc is repair
        assert ctx.task_level_backend is loc

    def test_max_tier_respected(self):
        """When frontier caps max_tier at 2 with 3+ tiers, T3 is blocked."""
        from budgetflow.adapter.strategies import choose_backend, _task_level_max_tier
        from budgetflow.tier_frontier import TierFrontier

        alloc = _trusted_allocation(
            task_value=0.5,
            task_effort=80.0,
            model_fit={"tier1": 0.10, "tier2": 0.20, "tier3": 0.22},
        )
        backends = _three_backends()
        ctx = _task_level_ctx(backends, budget_pressure=0.9, allocation=alloc)

        # Force max_tier=2: extreme cost ratio + tiny progress delta + high pressure
        ctx.tier_frontier = TierFrontier(
            reference_tier=2,
            strongest_tier=3,
            reference_display="T2",
            strongest_display="T3",
            strongest_input_ratio=100.0,
            strongest_output_ratio=100.0,
            strongest_progress_delta={"localization": 0.001, "repair": 0.001, "validation": 0.001},
            reference_runway_turns=35,
            reason="extremely expensive T3",
        )
        max_tier = _task_level_max_tier(ctx)
        assert max_tier == 2, f"precondition: max_tier should be 2, got {max_tier}"

        per_turn = _per_turn_costs(backends)
        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier <= 2

    def test_task_level_uses_expected_total_cost_not_per_step(self):
        """Regression: verify delta_total_cost is used, not per-step delta_cost.

        When T2 per-step is cheaper but total cost is higher, T3 is chosen.
        """
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        # T2 per-step ≈ $6.41, T3 per-step ≈ $32.04  (T3 ~5x more per step)
        # But T2 fit=0.08, T3 fit=0.65 → T2 needs ~8x more turns
        # T2 total: 80/0.08 * 6.41 = 1000 * 6.41 = $6410
        # T3 total: 80/0.65 * 32.04 = 123 * 32.04 = $3941
        # T3 IS cheaper in total despite being 5x more per step
        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.08, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        # Verify per-step costs: T2 is cheaper per step
        assert per_turn["tier2"] < per_turn["tier3"], (
            "precondition: T2 per-step must be cheaper than T3"
        )
        # Verify total costs: T2 is more expensive in total
        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
        assert t2_total > t3_total, (
            f"precondition: T2 total ${t2_total:.2f} > T3 total ${t3_total:.2f}"
        )

        # The old per-step logic would choose T2 (cheaper per step).
        # The new total-cost logic must choose T3.
        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 3, (
            f"per-step T2=${per_turn['tier2']:.4f} < T3=${per_turn['tier3']:.4f} "
            f"but total T2=${t2_total:.2f} > T3=${t3_total:.2f}; "
            f"should choose T3, got {backend.name}"
        )

    def test_low_value_task_stays_t2_when_total_cost_favors_t2(self):
        """Low-value, low-effort task: T2 cheaper in total, stays T2."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.5,
            task_effort=10.0,
            model_fit={"tier2": 0.55, "tier3": 0.60},
        )
        backends = _backends(t2_progress=0.55, t3_progress=0.60)
        ctx = _task_level_ctx(backends, budget_pressure=0.5, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 2, f"low-value simple task should stay T2, got {backend.name}"

    def test_three_tier_task_level_expected_cost(self):
        """With three tiers and large T3 fit advantage, T3 dominates in total cost."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        # T3 per-turn is ~18x T1 and ~5x T2. T3 needs enough fit advantage to
        # overcome this: fit_ratio must exceed price_ratio for each comparison.
        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=30.0,
            model_fit={"tier1": 0.02, "tier2": 0.05, "tier3": 0.60},
        )
        backends = _three_backends()
        ctx = _task_level_ctx(backends, budget_pressure=0.2, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        t1_total = _expected_total_cost(ctx, "tier1", 1, per_turn["tier1"])
        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])

        assert t3_total < t1_total, f"T3 ${t3_total:.2f} should be < T1 ${t1_total:.2f}"
        assert t3_total < t2_total, f"T3 ${t3_total:.2f} should be < T2 ${t2_total:.2f}"

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 3, (
            f"T1 total ${t1_total:.2f}, T2 total ${t2_total:.2f}, "
            f"T3 total ${t3_total:.2f}; expected T3, got {backend.name}"
        )

    def test_task_level_reference_starts_at_t2_not_cheapest_t1(self):
        """Current task-level policy chooses between T2 and T3, not T1."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.5,
            task_effort=20.0,
            model_fit={"tier1": 0.65, "tier2": 0.65, "tier3": 0.70},
        )
        backends = _three_backends()
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 2

    def test_low_confidence_model_fit_does_not_drive_t3_choice(self):
        """Low-confidence fit stays observable but task-level falls back to catalog prior."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost, _tier_model_fit_rate

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
            confidence={"model_fit": "low"},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.25)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        assert _tier_model_fit_rate(ctx, 2, "tier2") == pytest.approx(0.24)
        assert _tier_model_fit_rate(ctx, 3, "tier3") == pytest.approx(0.25)
        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
        assert t2_total < t3_total

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 2

    def test_high_value_high_effort_does_not_start_t3_without_fit_gap(self):
        """Task-start routing needs an expected value gain, not only value/effort."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 1.0, "tier3": 1.0},
        )
        backends = _backends(t2_progress=0.60, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.35, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 2
        assert ctx.last_decision is not None
        assert "task_start" not in ctx.last_decision.reason
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.scores["task_value"] == pytest.approx(2.0)
        assert ctx.last_policy_decision.scores["task_effort"] == pytest.approx(80.0)
        assert ctx.last_policy_decision.scores["fit_gain"] == pytest.approx(0.0)

    def test_initial_task_router_does_not_depend_on_task_identity(self):
        """The same abstract signals give the same tier for different workflow IDs."""
        from budgetflow.adapter.strategies import choose_backend

        alloc_a = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 0.24, "tier3": 0.65},
            planned_task_budget=10000.0,
        )
        alloc_b = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 0.24, "tier3": 0.65},
            planned_task_budget=10000.0,
        )
        backends = _backends(t2_progress=0.60, t3_progress=0.65)
        ctx_a = _task_level_ctx(backends, budget_pressure=0.35, allocation=alloc_a)
        ctx_b = _task_level_ctx(backends, budget_pressure=0.35, allocation=alloc_b)
        per_turn = _per_turn_costs(backends)

        backend_a = choose_backend(ctx_a, _turn(), per_turn)
        other_task = _turn()
        object.__setattr__(other_task, "workflow_id", "different__task-999")
        backend_b = choose_backend(ctx_b, other_task, per_turn)

        assert backend_a.tier == backend_b.tier
        assert ctx_a.last_policy_decision.scores == ctx_b.last_policy_decision.scores

    def test_task_budget_pressure_blocks_t3_when_budget_is_too_tight(self):
        """A planned task budget can veto T3 while preserving task-level fixed routing."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            planned_task_budget=0.05,
            model_fit={"tier2": 1.0, "tier3": 1.0},
        )
        backends = _backends(t2_progress=0.60, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.35, allocation=alloc)
        per_turn = _per_turn_costs(backends)
        assert per_turn["tier3"] > alloc.planned_task_budget

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 2
        assert ctx.last_policy_decision.scores["budget_allows_strongest"] == 0.0

    def test_planned_task_budget_can_frontload_t3_despite_small_fit_delta(self):
        """Regression for 4x25: task budget runway must affect task-start tier choice.

        The failed run had workload fit tier2=0.81/tier3=0.85. The old marginal
        Yield/$ formula treated that tiny delta as a reason to pick T2 for every
        task, even when the pre-registered per-task budget could afford the
        Strongest Model expected total cost.
        """
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.91,
            task_effort=126.6339,
            planned_task_budget=6.4057,
            model_fit={"tier2": 0.81, "tier3": 0.85},
        )
        backends = _backends(t2_progress=0.81, t3_progress=0.85)
        ctx = _task_level_ctx(backends, budget_pressure=0.33, allocation=alloc)
        per_turn = _runtime_like_costs()

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.scores["budget_allows_strongest"] == 1.0
        assert ctx.last_policy_decision.scores["planned_task_budget"] == pytest.approx(6.4057)

    def test_marginal_yield_per_dollar_can_choose_t3_when_t3_costs_more(self):
        """High-value tasks can choose T3 by marginal Yield/$, not only cost dominance."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        alloc = _trusted_allocation(
            task_value=4.0,
            task_effort=70.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.24, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _runtime_like_costs()

        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
        assert t3_total > t2_total, "precondition: this is value gain, not cost dominance"

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["rule"] in {"marginal_expected_value_per_dollar", "planned_task_budget_frontier"}
        assert scores["marginal_yield_per_dollar"] > scores["budget_pressure_threshold"]

    def test_marginal_yield_uses_task_extra_cost_not_cost_ratio(self):
        """Medium-value tasks can choose T3 when extra expected value pays for extra cost."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        alloc = _trusted_allocation(
            task_value=1.3,
            task_effort=21.0,
            planned_task_budget=1.0,
            model_fit={"tier2": 0.67, "tier3": 1.0},
        )
        backends = _backends(t2_progress=0.67, t3_progress=1.0)
        ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=alloc)
        per_turn = _runtime_like_costs()

        t2_total = _expected_total_cost(ctx, "tier2", 2, per_turn["tier2"])
        t3_total = _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"])
        assert t3_total > t2_total

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["rule"] in {"marginal_expected_value_per_dollar", "planned_task_budget_frontier"}
        assert scores["marginal_yield_per_dollar"] > scores["budget_pressure_threshold"]
        assert scores["extra_expected_cost"] == pytest.approx(t3_total - t2_total)
        assert scores["marginal_yield_per_dollar"] == pytest.approx(
            scores["expected_value_gain"] / scores["extra_unit_cost"]
        )

    def test_marginal_yield_per_dollar_stays_t2_when_value_gain_is_small(self):
        """Low-value tasks stay T2 when T3's extra cost buys little expected value."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost

        alloc = _trusted_allocation(
            task_value=0.5,
            task_effort=70.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.24, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        assert _expected_total_cost(ctx, "tier3", 3, per_turn["tier3"]) > _expected_total_cost(
            ctx, "tier2", 2, per_turn["tier2"]
        )

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 2
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["rule"] == "marginal_expected_value_per_dollar"
        assert scores["marginal_yield_per_dollar"] < scores["budget_pressure_threshold"]

    def test_task_start_marginal_yield_uses_unit_extra_cost(self):
        """Same value/fit/cost signals should not become worse only because effort is higher."""
        from budgetflow.adapter.strategies import choose_backend

        backends = _backends(t2_progress=0.67, t3_progress=1.0)
        per_turn = _runtime_like_costs()

        low_effort = _trusted_allocation(
            task_value=1.3,
            task_effort=21.0,
            planned_task_budget=10.0,
            model_fit={"tier2": 0.67, "tier3": 1.0},
        )
        high_effort = _trusted_allocation(
            task_value=1.3,
            task_effort=80.0,
            planned_task_budget=10.0,
            model_fit={"tier2": 0.67, "tier3": 1.0},
        )
        low_ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=low_effort)
        high_ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=high_effort)

        assert choose_backend(low_ctx, _turn(), per_turn).tier == 3
        assert choose_backend(high_ctx, _turn(), per_turn).tier == 3
        assert low_ctx.last_policy_decision is not None
        assert high_ctx.last_policy_decision is not None
        assert high_ctx.last_policy_decision.scores["marginal_yield_per_dollar"] == pytest.approx(
            low_ctx.last_policy_decision.scores["marginal_yield_per_dollar"]
        )
        assert high_ctx.last_policy_decision.scores["extra_expected_cost"] > (
            low_ctx.last_policy_decision.scores["extra_expected_cost"]
        )

    def test_missing_expected_costs_do_not_make_t3_look_free(self):
        """Runtime should stay T2 if cost estimates are unavailable at task start."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=3.0,
            task_effort=70.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.24, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)

        backend = choose_backend(ctx, _turn(), {})

        assert backend.tier == 2
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.scores["cost_estimate_available"] == 0.0


# ── budget compiler cold-start with model-fit scaling ──────────────────────


class TestBudgetCompilerFitScaling:
    def test_cold_start_reference_scale_is_strategy_independent(self):
        """Compiler cold-start scale does not preselect a runtime policy tier."""
        from budgetflow.experiments.budget_binding import _cold_start_cost_estimate

        first = _cold_start_cost_estimate(50.0)
        second = _cold_start_cost_estimate(50.0)

        assert first > 0
        assert second == first

    def test_cold_start_with_large_fit_gap_increases_reference_projection(self):
        """When reference fit is much lower than strongest, cold-start projection rises."""
        from budgetflow.experiments.budget_binding import _cold_start_cost_estimate

        catalog_cost = _cold_start_cost_estimate(50.0)
        fit_scaled_cost = _cold_start_cost_estimate(50.0, fit_overrides={2: 0.05, 3: 0.65})

        assert catalog_cost > 0
        assert fit_scaled_cost > catalog_cost
        assert fit_scaled_cost / catalog_cost > 2.0, (
            f"fit scaling should increase reference projection; "
            f"catalog=${catalog_cost:.4f}, fit_scaled=${fit_scaled_cost:.4f}"
        )


# ── censored rows increase projected T2 cost ───────────────────────────────


class TestCensoredCostProjection:
    def test_censored_t2_floor_increases_projected_cost(self):
        """Budget-exhausted T2 rows are censored floors, not full costs."""
        from budgetflow.experiments.budget_binding import _load_historical_cost_signals

        import json
        from pathlib import Path
        import tempfile

        catalog = {
            "catalog_revision": "test",
            "catalog_content_hash": "test",
        }
        # Inject compatible catalog
        import budgetflow.model_tiers as mt
        original_info = {
            "catalog_revision": mt.catalog_revision(),
            "catalog_content_hash": mt._catalog_content_hash,
        }
        try:
            mt._catalog_revision = "test"
            mt._catalog_content_hash = "test"

            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                f.write(
                    json.dumps({
                        "strategy": "budgetflow_task_level",
                        "instance_id": "task-x",
                        "total_cost": 2.30,
                        "budget_mode": "shared_batch_hard_budget",
                        "catalog": catalog,
                        "score_status": "true_fail",
                        "exit_status": "BudgetFlowBudgetError",
                        "exit_reason": "budget_exhausted",
                        "harness_trust": "trusted",
                        "row_finished_at": 1,
                    })
                    + "\n"
                )
                jsonl_path = Path(f.name)

            signals = _load_historical_cost_signals(jsonl_path)
            assert "budgetflow_task_level" in signals.censored_task_costs_by_strategy
            assert signals.censored_task_costs_by_strategy["budgetflow_task_level"]["task-x"] == 2.30
            assert signals.censored_spend_floor_by_strategy["budgetflow_task_level"] == 2.30
            assert signals.censored_row_counts["budgetflow_task_level"] == 1
            # Censored rows do NOT enter observed_costs
            assert signals.observed_costs == {}

            jsonl_path.unlink()
        finally:
            mt._catalog_revision = original_info["catalog_revision"]
            mt._catalog_content_hash = original_info["catalog_content_hash"]

    def test_censored_floor_adds_runway_for_next_projection(self):
        """Projected cost for censored task = censored_floor + baseline (runway)."""
        from budgetflow.experiments.budget_binding import calibrate_budget

        import json
        from pathlib import Path
        import tempfile

        catalog = {
            "catalog_revision": "test",
            "catalog_content_hash": "test",
        }
        import budgetflow.model_tiers as mt
        original_info = {
            "catalog_revision": mt.catalog_revision(),
            "catalog_content_hash": mt._catalog_content_hash,
        }
        try:
            mt._catalog_revision = "test"
            mt._catalog_content_hash = "test"

            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
                f.write(
                    json.dumps({
                        "strategy": "budgetflow_task_level",
                        "instance_id": "task-x",
                        "total_cost": 2.30,
                        "budget_mode": "shared_batch_hard_budget",
                        "catalog": catalog,
                        "score_status": "true_fail",
                        "exit_status": "BudgetFlowBudgetError",
                        "exit_reason": "budget_exhausted",
                        "harness_trust": "trusted",
                        "row_finished_at": 1,
                    })
                    + "\n"
                )
                jsonl_path = Path(f.name)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(json.dumps({
                    "tasks": {
                        "task-x": {"task_effort": {"bootstrap_heuristic": 30.0}},
                    }
                }))
                vm_path = Path(f.name)

            plan = calibrate_budget(
                ["task-x"],
                historical_jsonl=jsonl_path,
                value_matrix_path=vm_path,
                strategies=("budgetflow_task_level",),
                target_utilization=0.90,
            )
            projected = plan.projected_spend_by_strategy["budgetflow_task_level"]
            # Censored floor ($2.30) + baseline runway → projected > $2.30
            assert projected > 2.30, (
                f"projected ${projected:.4f} should exceed censored floor $2.30"
            )
            assert plan.censored_spend_floor_by_strategy == {"budgetflow_task_level": 2.30}

            jsonl_path.unlink()
            vm_path.unlink()
        finally:
            mt._catalog_revision = original_info["catalog_revision"]
            mt._catalog_content_hash = original_info["catalog_content_hash"]

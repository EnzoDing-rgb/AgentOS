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
    t2_cost_input=0.9 / 1_000_000,
    t2_cost_output=4.5 / 1_000_000,
    t3_cost_input=4.5 / 1_000_000,
    t3_cost_output=22.5 / 1_000_000,
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
        Backend("tier1", 1, 0.3 / 1_000_000, 1.5 / 1_000_000, 100, 20, 768, 0.15, 500),
        Backend("tier2", 2, 0.9 / 1_000_000, 4.5 / 1_000_000, 100, 35, 1024, 0.24, 4200),
        Backend("tier3", 3, 4.5 / 1_000_000, 22.5 / 1_000_000, 50, 5, 1024, 0.25, 1200),
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


def _turn(stage=None, w_i=1.0, context_len=1000):
    from budgetflow.types import Stage, TurnInfo

    return TurnInfo(
        workflow_id="test",
        step_index=1,
        stage=stage or Stage.LOCALIZATION,
        w_i=w_i,
        context_len=context_len,
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





# ── task-level backend selection ───────────────────────────────────────────


class TestChooseTaskLevelBackend:
    def test_task_level_runtime_decision_is_not_compiler_assigned(self):
        """Task-level routing uses runtime AllocationContext signals."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.08, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=alloc)

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.task_level_backend is backend
        assert ctx.last_decision is not None
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.reason != "task_level_fixed_budget_plan_model"

    def test_chooses_t3_when_t2_total_cost_exceeds_t3(self):
        """Core fix: when T2 expected total cost > T3, task-level chooses T3."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.08, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.3, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 3, (
            f"expected T3 when T2 fit is much lower than T3, "
            f"got {backend.name}"
        )
        assert ctx.task_level_backend is not None
        assert ctx.task_level_backend.tier == 3

    def test_chooses_t2_for_low_value_simple_task(self):
        """Low-value, low-effort task with similar fit → T2 stays cheaper."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.5,
            task_effort=10.0,
            model_fit={"tier2": 0.60, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.60, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.3, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 2, (
            f"expected T2 for simple task, got {backend.name}"
        )

    def test_high_value_high_effort_chooses_t3_under_budget(self):
        """High-value, high-effort task: T3 total cost dominates T2, choose T3."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=3.0,
            task_effort=60.0,
            model_fit={"tier2": 0.10, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.10, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.4, allocation=alloc)
        per_turn = _per_turn_costs(backends)

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
        """Regression: T3 chosen when T2 per-step cheaper but total cost higher."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=80.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.08, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        assert per_turn["tier2"] < per_turn["tier3"], (
            "precondition: T2 per-step must be cheaper than T3"
        )

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 3, (
            f"per-step T2=${per_turn['tier2']:.4f} < T3=${per_turn['tier3']:.4f} "
            f"but should choose T3, got {backend.name}"
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
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0,
            task_effort=30.0,
            model_fit={"tier1": 0.02, "tier2": 0.05, "tier3": 0.60},
        )
        backends = _three_backends()
        ctx = _task_level_ctx(backends, budget_pressure=0.2, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 3, (
            f"expected T3 with large fit advantage, got {backend.name}"
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
        from budgetflow.adapter.strategies import choose_backend, _tier_model_fit_rate

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

        backend = choose_backend(ctx, _turn(), per_turn)
        assert backend.tier == 2

    def test_cold_start_effortful_task_starts_strongest_without_trusted_fit(self):
        """Cold-start task-level should lean Strongest on effortful SWE tasks.

        Without trusted ModelFit, flat catalog priors (T2=0.24, T3=0.25) are
        not evidence that the cheaper-per-turn tier is cheaper in total.  The
        task-level frontier should probe Strongest when the task has meaningful
        effort and the planned task budget can absorb the projected Strongest
        start.
        """
        from budgetflow.adapter.strategies import choose_backend
        from budgetflow.allocation import AllocationContext

        alloc = AllocationContext(
            task_value=1.0,
            task_effort=21.0,
            planned_task_budget=4.0,
            effort_source="unit_test",
            model_fit_source="catalog_progress_prior",
            confidence={"model_fit": "none"},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.25)
        ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=alloc)

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        assert ctx.last_decision.reason == "bf_task_start_uncertain_frontier_probe"
        assert ctx.last_policy_decision.scores["has_trusted_model_fit"] == 0.0

    def test_cold_start_near_effort_boundary_starts_strongest_without_trusted_fit(self):
        """Cold-start effort gates should tolerate small Task Effort estimator noise."""
        from budgetflow.adapter.strategies import choose_backend
        from budgetflow.allocation import AllocationContext

        alloc = AllocationContext(
            task_value=1.0,
            task_effort=19.5,
            planned_task_budget=4.0,
            effort_source="unit_test",
            model_fit_source="catalog_progress_prior",
            confidence={"model_fit": "none"},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.25)
        ctx = _task_level_ctx(backends, budget_pressure=0.45, allocation=alloc)

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        assert ctx.last_decision.reason == "bf_task_start_uncertain_frontier_probe"

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
        assert ctx.last_decision.reason == "bf_task_start_reference_frontier"
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

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 2
        assert ctx.last_policy_decision.scores["budget_allows_strongest"] == 0.0
        assert ctx.last_policy_decision.scores["budget_soft_allows_strongest"] == 0.0
        assert ctx.last_policy_decision.scores["planned_task_budget"] == pytest.approx(0.05)
        assert ctx.last_policy_decision.scores["effective_task_budget"] == pytest.approx(0.05)
        assert ctx.last_decision.reason == "bf_task_start_reference_frontier"

    def test_soft_budget_gate_allows_high_value_cold_start_t3_probe(self):
        """High-value cold-start tasks can probe T3 when forecast coverage is reasonable."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=1.5,
            task_effort=23.1727,
            planned_task_budget=2.4936,
            effective_task_budget=1.078647,
            model_fit=None,
            confidence={"model_fit": "none"},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.35)
        ctx = _task_level_ctx(
            backends,
            budget_pressure=0.020295,
            median_task_value=1.0,
            allocation=alloc,
        )

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["budget_allows_strongest"] == 1.0
        assert scores["planned_task_budget"] == pytest.approx(2.4936)
        assert scores["effective_task_budget"] == pytest.approx(1.078647)
        assert scores["budget_soft_allows_strongest"] == 1.0
        assert scores["strongest_budget_coverage"] >= 0.50
        assert scores["marginal_yield_per_dollar"] >= scores["t3_acceptance_threshold"]
        assert ctx.last_decision.reason == "bf_task_start_uncertain_frontier_probe"

    def test_critical_value_probe_can_buy_minimum_t3_window_under_prorated_budget(self):
        """Critical tasks can buy a small T3 probe even when full-cost forecasts are conservative."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.5,
            task_effort=50.8644,
            planned_task_budget=2.1906,
            effective_task_budget=0.7507,
            model_fit=None,
            confidence={"model_fit": "none"},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.35)
        ctx = _task_level_ctx(
            backends,
            budget_pressure=0.0639,
            median_task_value=1.0,
            allocation=alloc,
        )

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["budget_allows_strongest"] == 0.0
        assert scores["strongest_budget_coverage"] < scores["strongest_min_budget_coverage"]
        assert scores["budget_allows_strongest_probe"] == 1.0
        assert scores["critical_value_probe"] == 1.0
        assert scores["rule"] == "critical_value_probe"
        assert ctx.last_decision.reason == "bf_task_start_critical_value_probe"

    def test_planned_task_budget_does_not_override_small_fit_delta(self):
        """Task runway is necessary but not enough to buy Strongest Model turns."""
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

        assert backend.tier == 2
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.scores["budget_allows_strongest"] == 1.0
        assert ctx.last_policy_decision.scores["planned_task_budget"] == pytest.approx(6.4057)
        assert ctx.last_policy_decision.scores["effective_task_budget"] == pytest.approx(6.4057)
        assert ctx.last_policy_decision.scores["fit_gain"] == pytest.approx(0.04)
        assert ctx.last_policy_decision.scores["paid_upgrade_candidate"] == 0.0
        assert ctx.last_decision.reason == "bf_task_start_reference_frontier"

    def test_effective_task_budget_is_not_a_hard_t3_veto_when_planned_runway_supports_probe(self):
        """Live runway is pressure, not a T3 veto when planned runway supports a probe."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=1.5,
            task_effort=26.9418,
            planned_task_budget=1.5446,
            effective_task_budget=0.12339578305573606,
            model_fit=None,
            confidence={"model_fit": "none"},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.35)
        ctx = _task_level_ctx(
            backends,
            budget_pressure=1.0368203490851284,
            median_task_value=1.0,
            allocation=alloc,
        )

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert ctx.last_policy_decision.scores["budget_allows_strongest"] == 0.0
        assert scores["planned_task_budget"] == pytest.approx(1.5446)
        assert scores["effective_task_budget"] == pytest.approx(0.12339578305573606)
        assert scores["strongest_budget_coverage"] >= scores["strongest_min_budget_coverage"]
        assert scores["budget_allows_strongest_probe"] == 1.0
        assert scores["high_pressure_efficiency_probe"] == 1.0
        assert ctx.last_decision.reason == "bf_task_start_high_pressure_efficiency_probe"

    def test_zero_effective_task_budget_vetoes_t3_cost_dominance(self):
        """A task with no runway must not project a strongest-tier start."""
        from budgetflow.task_level_routing import task_start_tier_decision

        tier, reason, scores = task_start_tier_decision(
            task_value=2.5,
            task_effort=40.0,
            tier2_fit=0.30,
            tier3_fit=0.95,
            tier2_per_turn_cost=0.01,
            tier3_per_turn_cost=0.02,
            budget_pressure=1.0,
            planned_task_budget=0.0,
            effective_task_budget=0.0,
            median_task_value=1.0,
            has_trusted_model_fit=True,
            is_cold_start=False,
        )

        assert tier == 2
        assert reason == "reference_frontier"
        assert scores["budget_soft_allows_strongest"] == 0.0

    def test_decisive_marginal_yield_can_override_low_task_budget_coverage(self):
        """Task cap coverage is a runway signal, not a veto over decisive Claim-1 value."""
        from budgetflow.task_level_routing import task_start_tier_decision

        tier, reason, scores = task_start_tier_decision(
            task_value=1.0,
            task_effort=54.8672,
            tier2_fit=0.205221,
            tier3_fit=0.711557,
            tier2_per_turn_cost=0.0055079983,
            tier3_per_turn_cost=0.027539997,
            budget_pressure=0.01,
            planned_task_budget=0.648961,
            effective_task_budget=0.648961,
            median_task_value=1.0,
            has_trusted_model_fit=True,
            is_cold_start=False,
        )

        assert tier == 3
        assert reason == "decisive_marginal_yield_budget_override"
        assert scores["budget_allows_strongest"] == 0.0
        assert scores["strongest_budget_coverage"] < scores["strongest_min_budget_coverage"]
        assert scores["budget_soft_allows_strongest"] == 1.0
        assert scores["decisive_marginal_budget_override"] == 1.0
        assert scores["marginal_yield_per_dollar"] >= scores["t3_acceptance_threshold"] * 3.0

    def test_marginal_yield_per_dollar_can_choose_t3_when_t3_costs_more(self):
        """High-value tasks can choose T3 by marginal Yield/$, not only cost dominance."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=4.0,
            task_effort=70.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.24, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _runtime_like_costs()

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["rule"] == "marginal_expected_value_per_dollar"
        assert scores["marginal_yield_per_dollar"] > scores["budget_pressure_threshold"]

    def test_marginal_yield_uses_task_extra_cost_not_cost_ratio(self):
        """Medium-value tasks can choose T3 when extra expected value pays for extra cost."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=1.3,
            task_effort=21.0,
            planned_task_budget=1.0,
            model_fit={"tier2": 0.67, "tier3": 1.0},
        )
        backends = _backends(t2_progress=0.67, t3_progress=1.0)
        ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=alloc)
        per_turn = _runtime_like_costs()

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["rule"] == "marginal_expected_value_per_dollar"
        assert scores["marginal_yield_per_dollar"] > scores["budget_pressure_threshold"]
        assert scores["extra_expected_cost"] > 0
        assert scores["marginal_yield_per_dollar"] > 0

    def test_t3_price_is_not_counted_twice_in_marginal_threshold(self):
        """Extra unit cost already prices T3; threshold should not multiply price ratio again."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=1.0,
            task_effort=35.0,
            planned_task_budget=10.0,
            model_fit={"tier2": 0.67, "tier3": 1.0},
        )
        backends = _backends(t2_progress=0.67, t3_progress=1.0)
        ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=alloc)

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["extra_unit_cost"] > 0
        assert scores["marginal_yield_per_dollar"] >= scores["t3_acceptance_threshold"]

    def test_near_boundary_marginal_yield_stays_t2(self):
        """Near-threshold T3 starts stay on T2 instead of flipping on cost noise."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.67,
            task_effort=20.3949,
            planned_task_budget=2.3246,
            model_fit={"tier2": 0.261034, "tier3": 0.541978},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.25)
        ctx = _task_level_ctx(
            backends,
            budget_pressure=0.01,
            median_task_value=0.62,
            allocation=alloc,
        )

        backend = choose_backend(
            ctx,
            _turn(),
            {"tier2": 0.0056493, "tier3": 0.0282465},
        )

        assert backend.tier == 2
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["marginal_yield_per_dollar"] > scores["budget_pressure_threshold"]
        assert scores["paid_upgrade_candidate"] == 0.0
        assert scores["criticality_or_effort_gate"] == 0.0

    def test_decisive_marginal_yield_still_starts_t3(self):
        """A clear T3 opportunity still starts on T3 after the ambiguity band."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.90,
            task_effort=24.7926,
            planned_task_budget=3.4289,
            model_fit={"tier2": 0.261034, "tier3": 0.541978},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.25)
        ctx = _task_level_ctx(
            backends,
            budget_pressure=0.08823291505893546,
            median_task_value=0.68,
            allocation=alloc,
        )

        backend = choose_backend(
            ctx,
            _turn(),
            {"tier2": 0.0057186, "tier3": 0.028593},
        )

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["marginal_yield_per_dollar"] >= scores["t3_acceptance_threshold"]

    def test_task_start_decision_uses_normalized_cost_not_turn_token_noise(self):
        """Task-start tier choice must match compiler projection cost semantics."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.67,
            task_effort=24.7926,
            planned_task_budget=3.4289,
            model_fit={"tier2": 0.261034, "tier3": 0.541978},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.25)
        ctx = _task_level_ctx(
            backends,
            budget_pressure=0.09713827781595223,
            median_task_value=0.68,
            allocation=alloc,
        )

        backend = choose_backend(
            ctx,
            _turn(context_len=1234),
            {"tier2": 0.0057186, "tier3": 0.028593},
        )

        assert backend.tier == 2
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["paid_upgrade_candidate"] == 0.0
        assert scores["criticality_or_effort_gate"] == 0.0

    def test_marginal_yield_per_dollar_stays_t2_when_value_gain_is_small(self):
        """Low-value tasks stay T2 when T3's extra cost buys little expected value."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=0.1,
            task_effort=70.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.24, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.24, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.1, allocation=alloc)
        per_turn = _per_turn_costs(backends)

        backend = choose_backend(ctx, _turn(), per_turn)

        assert backend.tier == 2
        assert ctx.last_policy_decision is not None
        scores = ctx.last_policy_decision.scores
        assert scores["paid_upgrade_candidate"] == 0.0
        assert scores["criticality_or_effort_gate"] == 0.0

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
        assert high_ctx.last_policy_decision.scores["marginal_yield_per_dollar"] > (
            low_ctx.last_policy_decision.scores["marginal_yield_per_dollar"]
        )
        assert high_ctx.last_policy_decision.scores["extra_expected_cost"] > (
            low_ctx.last_policy_decision.scores["extra_expected_cost"]
        )


    def test_missing_tier_backend_fails_fast(self):
        """A strategy requiring a missing tier should not silently route elsewhere."""
        from budgetflow.adapter.strategies import choose_backend

        ctx = _task_level_ctx(_backends())
        ctx.strategy = "all_flash"

        with pytest.raises(KeyError, match="missing backend for tier T1"):
            choose_backend(ctx, _turn(), _runtime_like_costs())


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

    def test_compiler_projection_matches_effortful_cold_start_probe(self):
        """Compiler projection should mirror runtime's cold-start Strongest probe."""
        from budgetflow.experiments.budget_binding import _project_task_level_choice_cost

        choice, projected_cost, routing_reason, routing_scores = _project_task_level_choice_cost(
            "task-a",
            {
                "task-a": {
                    "task_value": 1.0,
                    "task_effort": 21.0,
                }
            },
            reference_cost=0.20,
            strongest_cost=0.80,
            planned_task_budget=4.0,
            fit_overrides=None,
            budget_pressure=0.01,
        )

        assert choice == 3
        assert projected_cost == pytest.approx(0.80)
        assert routing_reason == "uncertain_frontier_probe"
        assert isinstance(routing_scores, dict)
        assert routing_scores.get("rule") == "uncertain_frontier_probe"
        assert routing_scores.get("task_budget_headroom") > 0

    def test_compiler_projection_matches_near_boundary_cold_start_probe(self):
        """Compiler mirror should not diverge from runtime on soft effort boundary."""
        from budgetflow.experiments.budget_binding import _project_task_level_choice_cost

        choice, projected_cost, routing_reason, routing_scores = _project_task_level_choice_cost(
            "task-a",
            {
                "task-a": {
                    "task_value": 1.0,
                    "task_effort": 19.5,
                }
            },
            reference_cost=0.20,
            strongest_cost=0.80,
            planned_task_budget=4.0,
            fit_overrides=None,
            budget_pressure=0.45,
        )

        assert choice == 3
        assert projected_cost == pytest.approx(0.80)
        assert routing_reason == "uncertain_frontier_probe"
        assert isinstance(routing_scores, dict)
        assert routing_scores.get("rule") == "uncertain_frontier_probe"


# ── observability seam tests ────────────────────────────────────────────────


class TestObservabilitySeams:
    def test_t3_acceptance_margin_uses_correct_constant(self):
        """t3_acceptance_margin must be TASK_START_T3_ACCEPTANCE_MARGIN (0.10), not the cold-start tolerance."""
        from budgetflow.task_level_routing import _scores

        result = _scores(
            value=1.0, effort=20.0, value_ratio=1.0, budget_pressure=0.0,
            budget_allows=True, has_trusted_model_fit=True,
            t2_fit=0.24, t3_fit=0.35, fit_gain=0.11,
            reference_cost=1.0, strongest_cost=2.0,
            t2_unit_cost=0.05, t3_unit_cost=0.10, extra_unit_cost=0.05,
            effort_multiplier=1.0, marginal_yield=5.0,
            threshold=3.0, acceptance_threshold=3.5,
            paid_upgrade_candidate=True, decisive_fit_gate=False,
            metadata_gate=True,
            planned_task_budget=10.0,
            effective_task_budget=10.0,
            headroom=8.0, headroom_fraction=0.8,
            budget_coverage=1.0, effective_budget_coverage=1.0,
            budget_soft_allows=True,
            rule="marginal_expected_value_per_dollar",
        )
        assert result["t3_acceptance_margin"] == 0.10

    def test_last_policy_decision_reason_is_real_routing_reason(self):
        """last_policy_decision.reason must carry the actual routing reason, not a generic label."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0, task_effort=80.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
        )
        backends = _backends(t2_progress=0.08, t3_progress=0.65)
        ctx = _task_level_ctx(backends, budget_pressure=0.01, allocation=alloc)

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 3
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.reason == "marginal_yield_per_dollar"
        assert ctx.last_policy_decision.scores["pre_cap_selected_tier"] == pytest.approx(3.0)
        assert ctx.last_policy_decision.scores["final_selected_tier"] == pytest.approx(3.0)
        assert ctx.last_policy_decision.confidence["pre_cap_reason"] == "marginal_yield_per_dollar"

    def test_last_policy_decision_explains_max_tier_cap(self):
        """If the safety cap blocks T3, the task-start observability must say so."""
        from budgetflow.adapter.strategies import choose_backend

        alloc = _trusted_allocation(
            task_value=2.0, task_effort=80.0,
            planned_task_budget=10000.0,
            model_fit={"tier2": 0.08, "tier3": 0.65},
        )
        backends = _three_backends()
        ctx = _task_level_ctx(backends, budget_pressure=1.5, allocation=alloc)
        ctx.tier_frontier = None

        backend = choose_backend(ctx, _turn(), _runtime_like_costs())

        assert backend.tier == 2
        assert ctx.last_policy_decision is not None
        assert ctx.last_policy_decision.reason == "max_tier_cap_reference_frontier"
        assert ctx.last_policy_decision.scores["pre_cap_selected_tier"] == pytest.approx(3.0)
        assert ctx.last_policy_decision.scores["final_selected_tier"] == pytest.approx(2.0)
        assert ctx.last_policy_decision.confidence["pre_cap_reason"] == "marginal_yield_per_dollar"

    def test_runtime_compiler_parity_cold_start_probe(self):
        """Runtime and compiler must agree: cold start without ModelFit → uncertain_frontier_probe."""
        from budgetflow.task_level_routing import task_start_tier_decision
        from budgetflow.experiments.budget_binding import _project_task_level_choice_cost

        runtime_tier, runtime_reason, runtime_scores = task_start_tier_decision(
            task_value=1.0, task_effort=21.0,
            tier2_fit=0.24, tier3_fit=0.35,
            tier2_per_turn_cost=0.01, tier3_per_turn_cost=0.04,
            budget_pressure=0.01,
            planned_task_budget=4.0,
            effective_task_budget=4.0,
            has_trusted_model_fit=False, is_cold_start=True,
        )

        compiler_tier, _, compiler_reason, compiler_scores = _project_task_level_choice_cost(
            "task-x",
            {"task-x": {"task_value": 1.0, "task_effort": 21.0}},
            reference_cost=0.20, strongest_cost=0.80,
            planned_task_budget=4.0, fit_overrides=None,
            budget_pressure=0.01,
        )

        assert runtime_tier == compiler_tier == 3
        assert runtime_reason == compiler_reason == "uncertain_frontier_probe"
        assert runtime_scores["rule"] == compiler_scores["rule"] == "uncertain_frontier_probe"

    def test_compiler_projection_preserves_zero_task_budget(self):
        """Compiler dry-run must not turn a zero effective cap into unlimited budget."""
        from budgetflow.experiments.budget_binding import _project_task_level_choice_cost

        tier, _, reason, scores = _project_task_level_choice_cost(
            "task-x",
            {"task-x": {"task_value": 2.5, "task_effort": 60.0}},
            reference_cost=0.20,
            strongest_cost=0.80,
            planned_task_budget=0.0,
            fit_overrides=None,
            budget_pressure=1.5,
        )

        assert tier == 2
        assert reason == "reference_frontier"
        assert scores["planned_task_budget"] == pytest.approx(0.0)
        assert scores["effective_task_budget"] == pytest.approx(0.0)
        assert scores["budget_allows_strongest"] == 0.0
        assert scores["budget_allows_strongest_probe"] == 0.0
        assert scores["budget_soft_allows_strongest"] == 0.0


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
                        "task-x": {"task_effort": {"final_task_effort": 30.0}},
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

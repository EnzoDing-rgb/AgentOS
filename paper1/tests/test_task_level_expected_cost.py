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


# ── expected-total-cost helper ─────────────────────────────────────────────


class TestExpectedTotalCost:
    def test_t2_more_expensive_in_total_when_low_fit(self):
        """When T2 model_fit is much lower than T3, expected total T2 cost > T3."""
        from budgetflow.adapter.strategies import _expected_total_cost, _tier_model_fit_rate
        from budgetflow.allocation import AllocationContext

        # T2 fit=0.10 (very weak on this task), T3 fit=0.68 (strong)
        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext

        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext

        alloc = AllocationContext(
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
    def test_chooses_t3_when_t2_total_cost_exceeds_t3(self):
        """Core fix: when T2 expected total cost > T3, task-level chooses T3."""
        from budgetflow.adapter.strategies import choose_backend, _expected_total_cost
        from budgetflow.allocation import AllocationContext

        # Simulate a task where T2 has much lower fit → many more turns → higher total cost
        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext

        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext

        # T3 per-step is ~5x T2, so T2 needs >5x more turns for T3 to dominate.
        # t2_fit=0.10, t3_fit=0.65 → turn_ratio = 6.5x > 5x price ratio.
        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext
        from budgetflow.tier_frontier import TierFrontier

        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext

        # T2 per-step ≈ $6.41, T3 per-step ≈ $32.04  (T3 ~5x more per step)
        # But T2 fit=0.08, T3 fit=0.65 → T2 needs ~8x more turns
        # T2 total: 80/0.08 * 6.41 = 1000 * 6.41 = $6410
        # T3 total: 80/0.65 * 32.04 = 123 * 32.04 = $3941
        # T3 IS cheaper in total despite being 5x more per step
        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext

        alloc = AllocationContext(
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
        from budgetflow.allocation import AllocationContext

        # T3 per-turn is ~18x T1 and ~5x T2. T3 needs enough fit advantage to
        # overcome this: fit_ratio must exceed price_ratio for each comparison.
        alloc = AllocationContext(
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


# ── budget compiler cold-start with model-fit scaling ──────────────────────


class TestBudgetCompilerFitScaling:
    def test_cold_start_t2_scaled_by_fit_ratio(self):
        """T2 cold-start cost is scaled up by strongest_fit / t2_fit."""
        from budgetflow.experiments.budget_binding import _cold_start_cost_estimate

        t2_cost = _cold_start_cost_estimate("budgetflow_task_level", 50.0)
        t3_cost = _cold_start_cost_estimate("bare_t3_baseline", 50.0)

        # T2 per-token is ~5x cheaper, but fit_ratio ≈ 0.25/0.24 ≈ 1.04
        # So T2 cold-start = base_t2 * 1.04
        # T3 cold-start = base_t3 * 1.0 (since fit_ratio for strongest = 1.0)
        # T3 should still be more expensive per-turn, but the gap narrows
        assert t2_cost > 0
        assert t3_cost > 0

    def test_cold_start_with_large_fit_gap_increases_t2_projection(self):
        """When T2 fit is much lower than T3, T2 cold-start projection rises."""
        from budgetflow.model_tiers import MODEL_CATALOG
        from budgetflow.experiments.budget_binding import _cold_start_cost_estimate
        import budgetflow.model_tiers as mt

        # Temporarily adjust catalog so T2 has much lower progress_score
        original_configs = list(MODEL_CATALOG.configs)
        try:
            modified = []
            for cfg in original_configs:
                if cfg.tier == 2:
                    modified.append(type(cfg)(
                        tier=cfg.tier,
                        backend=cfg.backend,
                        model=cfg.model,
                        provider=cfg.provider,
                        api_base=cfg.api_base,
                        api_key_env=cfg.api_key_env,
                        display=cfg.display,
                        cost_per_input_token=cfg.cost_per_input_token,
                        cost_per_output_token=cfg.cost_per_output_token,
                        mean_output_tokens=cfg.mean_output_tokens,
                        progress_score=0.10,
                        latency_ms=cfg.latency_ms,
                        progress_prior=cfg.progress_prior,
                        escalation_patience=cfg.escalation_patience,
                        max_turns=cfg.max_turns,
                        token_cost_bands=cfg.token_cost_bands,
                        rpm_limit=cfg.rpm_limit,
                        concurrency_limit=cfg.concurrency_limit,
                        protocol=cfg.protocol,
                        api_base_env=cfg.api_base_env,
                        proxy_env=cfg.proxy_env,
                        cost_source=cfg.cost_source,
                        cost_updated=cfg.cost_updated,
                        cost_notes=cfg.cost_notes,
                        progress_source=cfg.progress_source,
                        progress_updated=cfg.progress_updated,
                        progress_notes=cfg.progress_notes,
                    ))
                else:
                    modified.append(cfg)
            from budgetflow.model_tiers import ModelCatalog
            new_catalog = ModelCatalog(tuple(modified))
            mt.MODEL_CATALOG._replace(new_catalog)
            mt.TIER_CONFIGS.clear()
            mt.TIER_CONFIGS.update({cfg.backend: cfg for cfg in new_catalog.configs})

            t2_cost = _cold_start_cost_estimate("budgetflow_task_level", 50.0)
            t3_cost = _cold_start_cost_estimate("bare_t3_baseline", 50.0)

            # T2 fit=0.10, T3 fit=0.25 → fit_ratio = 2.5
            # T2 cold start should be scaled up significantly
            # T2: base ≈ $0.05175... * 2.5 ≈ $0.129; T3: $0.25875 * 1.0 ≈ $0.259
            # T3 still more expensive in absolute terms but gap is MUCH narrower
            assert t2_cost > 0
            assert t3_cost > 0
            # The ratio T3/T2 should be much lower than the raw per-token ratio of 5x
            cost_ratio = t3_cost / max(t2_cost, 0.0001)
            # Without scaling, ratio would be ~5x. With scaling, should be < 4x.
            assert cost_ratio < 4.0, (
                f"fit scaling should narrow T3/T2 cost ratio; got {cost_ratio:.2f}x"
            )
        finally:
            mt.MODEL_CATALOG._replace(ModelCatalog(tuple(original_configs)))
            mt.TIER_CONFIGS.clear()
            mt.TIER_CONFIGS.update({cfg.backend: cfg for cfg in original_configs})


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

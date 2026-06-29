from __future__ import annotations

import pytest

try:
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
except ImportError:
    BudgetFlowLitellmModel = None


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_gold_edit_stop_loss_grace_does_not_depend_on_patch_prep() -> None:
    model = object.__new__(BudgetFlowLitellmModel)
    model.agent_gold_edited = True
    model.agent_phase = "edit_gold"
    model._gold_edit_stop_loss_grace_turns = 0

    assert model._defer_gold_edit_stop_loss(True) is False
    assert model._defer_gold_edit_stop_loss(True) is False
    assert model._defer_gold_edit_stop_loss(True) is True


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_rescue_strongest_turn_is_not_immediately_downgraded() -> None:
    from budgetflow.types import Backend

    model = object.__new__(BudgetFlowLitellmModel)
    tier2 = Backend(
        name="tier2",
        tier=2,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.5,
        latency_ms=1,
    )
    tier3 = Backend(
        name="tier3",
        tier=3,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.7,
        latency_ms=1,
    )
    model.routing = type("Routing", (), {
        "strategy": "budgetflow_segment",
        "backends": [tier2, tier3],
    })()
    model._no_progress_on_current_tier = 99
    model._turns_on_current_tier = 99

    selected = model._apply_progress_escalation(tier3, protect_strongest_this_turn=True)

    assert selected is tier3
    assert model._no_progress_on_current_tier == 0
    assert model._turns_on_current_tier == 0


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_effective_task_budget_blocks_next_provider_call() -> None:
    from budgetflow.adapter.errors import BudgetFlowBudgetError
    from budgetflow.allocation import AllocationContext
    from budgetflow.governor import BudgetGovernor, GovernorConfig
    from budgetflow.ledger import WorkflowLedgerStore
    from budgetflow.types import Backend

    tier2 = Backend(
        name="tier2",
        tier=2,
        cost_per_input_token=0.001,
        cost_per_output_token=0.001,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.5,
        latency_ms=1,
    )
    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "task-a"
    model.governor = BudgetGovernor(
        GovernorConfig(total_budget=10.0, default_max_output_tokens=4096),
        WorkflowLedgerStore(),
    )
    model.routing = type("Routing", (), {
        "allocation": AllocationContext(effective_task_budget=0.10),
    })()
    model.step_index = 2
    model._task_spent_budget = 0.10
    model._last_reservation_id = None
    model._last_reserve_out = 0
    model._last_reserved_cost = 0.0
    model._last_reserved_input_tokens = 0
    model._last_reserved_output_tokens = 0
    model._task_budget_settlement_overrun = 0.0

    with pytest.raises(BudgetFlowBudgetError) as excinfo:
        model._reserve_backend(tier2, input_tokens=10)

    assert excinfo.value.exit_reason == "task_budget_exhausted"
    assert model.last_exit_reason == "task_budget_exhausted"
    assert model.last_budget_snapshot["task_budget_cap"] == pytest.approx(0.10)
    assert model.last_budget_snapshot["task_spent_budget"] == pytest.approx(0.10)


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_task_budget_block_updates_exit_snapshot_for_retry_path() -> None:
    from budgetflow.allocation import AllocationContext
    from budgetflow.governor import BudgetGovernor, GovernorConfig
    from budgetflow.ledger import WorkflowLedgerStore
    from budgetflow.types import Backend

    tier2 = Backend(
        name="tier2",
        tier=2,
        cost_per_input_token=0.001,
        cost_per_output_token=0.001,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.5,
        latency_ms=1,
    )
    model = object.__new__(BudgetFlowLitellmModel)
    model.governor = BudgetGovernor(
        GovernorConfig(total_budget=10.0, default_max_output_tokens=4096),
        WorkflowLedgerStore(),
    )
    model.routing = type("Routing", (), {
        "allocation": AllocationContext(effective_task_budget=0.12),
    })()
    model.step_index = 3
    model._task_spent_budget = 0.1199
    model._task_budget_settlement_overrun = 0.0
    model.last_exit_reason = None
    model.last_budget_snapshot = None

    estimate = model.governor.estimate_cost(
        tier2,
        input_tokens=20,
        reserve_output_tokens=model._reserve_output_tokens(tier2, input_tokens=20),
        turn_index=model.step_index,
    )

    assert model._task_budget_block_reason(estimate) == "task_budget_exhausted"
    snapshot = model._task_budget_snapshot()
    assert model.last_exit_reason == "task_budget_exhausted"
    assert model.last_budget_snapshot is snapshot
    assert snapshot["task_budget_cap"] == pytest.approx(0.12)
    assert snapshot["task_spent_budget"] == pytest.approx(0.1199)
    assert snapshot["task_available_budget"] == pytest.approx(0.0001)


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_task_budget_settlement_overrun_is_explicit_budget_exit() -> None:
    from budgetflow.adapter.errors import BudgetFlowBudgetError
    from budgetflow.allocation import AllocationContext
    from budgetflow.exit_reasons import is_budget_exit
    from budgetflow.governor import BudgetGovernor, GovernorConfig
    from budgetflow.ledger import WorkflowLedgerStore
    from budgetflow.types import Backend

    tier2 = Backend(
        name="tier2",
        tier=2,
        cost_per_input_token=0.001,
        cost_per_output_token=0.001,
        rpm_limit=1,
        concurrency_limit=1,
        mean_output_tokens=128,
        progress_score=0.5,
        latency_ms=1,
    )
    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "task-a"
    model.governor = BudgetGovernor(
        GovernorConfig(total_budget=10.0, default_max_output_tokens=4096),
        WorkflowLedgerStore(),
    )
    model.routing = type("Routing", (), {
        "allocation": AllocationContext(effective_task_budget=0.12),
    })()
    model.step_index = 4
    model._task_spent_budget = 0.10
    model._task_budget_settlement_overrun = 0.0
    model._last_reservation_id = None
    model._last_reserve_out = 0
    model._last_reserved_cost = 0.0
    model._last_reserved_input_tokens = 0
    model._last_reserved_output_tokens = 0
    model.last_backend_name = "tier2"

    estimate = model.governor.estimate_cost(
        tier2,
        input_tokens=5,
        reserve_output_tokens=5,
        turn_index=model.step_index,
    )
    reservation = model.governor.reserve("task-a", tier2, estimate)
    assert reservation is not None
    model._last_reservation_id = reservation.reservation_id
    model._last_reserve_out = estimate.reserved_output_tokens
    model._last_reserved_cost = estimate.reserved_cost
    model._last_reserved_input_tokens = estimate.reserved_input_tokens
    model._last_reserved_output_tokens = estimate.reserved_output_tokens

    with pytest.raises(BudgetFlowBudgetError) as excinfo:
        model._settle_reserved_call(
            reservation.reservation_id,
            actual_cost=0.05,
            billable=0.05,
        )

    assert excinfo.value.exit_reason == "task_budget_settlement_overrun"
    assert is_budget_exit(None, "task_budget_settlement_overrun")
    assert model._last_reservation_id is None
    assert model._last_reserve_out == 0
    assert model._last_reserved_cost == pytest.approx(0.0)
    assert model._last_reserved_input_tokens == 0
    assert model._last_reserved_output_tokens == 0
    assert model.last_budget_snapshot["task_budget_cap"] == pytest.approx(0.12)
    assert model.last_budget_snapshot["task_spent_budget"] == pytest.approx(0.15)
    assert model.last_budget_snapshot["task_budget_settlement_overrun"] == pytest.approx(0.03)


@pytest.mark.skipif(BudgetFlowLitellmModel is None, reason="minisweagent not installed")
def test_effective_remaining_budget_uses_task_budget_when_tighter() -> None:
    from budgetflow.allocation import AllocationContext
    from budgetflow.governor import BudgetGovernor, GovernorConfig
    from budgetflow.ledger import WorkflowLedgerStore

    model = object.__new__(BudgetFlowLitellmModel)
    model.governor = BudgetGovernor(
        GovernorConfig(total_budget=10.0, default_max_output_tokens=4096),
        WorkflowLedgerStore(),
    )
    model.routing = type("Routing", (), {
        "allocation": AllocationContext(effective_task_budget=0.35),
    })()
    model._task_spent_budget = 0.20

    assert model._effective_remaining_budget() == pytest.approx(0.15)

from __future__ import annotations

from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent

TEST_FILE_PURPOSES = {
    "test_adaptive_routing.py": "learn-policy-memory",
    "test_allocation_context.py": "allocation-context",
    "test_architecture_boundaries.py": "architecture-boundary",
    "test_auto_budget.py": "cost-memory",
    "test_bash_stage.py": "swebench-adapter",
    "test_budget_binding.py": "budget-calibrator",
    "test_budgetflow_runtime.py": "budgetflow-mechanism",
    "test_compare_readiness.py": "paid-run-gate",
    "test_compare_record_schema.py": "evidence-schema",
    "test_compare_setup.py": "experiment-setup",
    "test_experiment_observability.py": "evidence-schema",
    "test_frozen_router.py": "frozen-router-plan",
    "test_failure_classification.py": "failure-diagnosis",
    "test_gpt54_text_parser.py": "runtime-adapter",
    "test_learn_policy.py": "learn-policy-interface",
    "test_learning_context.py": "learn-policy-memory",
    "test_local_harness_pytest_nodes.py": "swebench-adapter",
    "test_policy_backend.py": "policy-interface",
    "test_policy_memory.py": "learn-policy-memory",
    "test_policy_parallelism.py": "experiment-setup",
    "test_provider_billing_retry.py": "provider-infra",
    "test_protocol_retry.py": "parser-protocol",
    "test_provider_fallback.py": "provider-infra",
    "test_recost.py": "cost-sensitivity",
    "test_run_guards.py": "stop-loss",
    "test_run_observability_audit.py": "evidence-audit",
    "test_run_series.py": "run-identity",
    "test_runner_exit_status.py": "runtime-adapter",
    "test_runtime_paths.py": "runtime-paths",
    "test_stall_guard.py": "stop-loss",
    "test_swebench_adapters.py": "swebench-adapter",
    "test_tier_frontier.py": "tier-frontier-calibration",
    "test_trace_fields.py": "decision-observability",
    "test_test_inventory.py": "test-audit",
    "test_value_aware.py": "bootstrap-policy",
    "test_value_efficiency.py": "yield-metrics",
    "test_value_matrix_bootstrap.py": "value-adapter",
}


def test_every_active_test_file_has_a_current_purpose() -> None:
    files = {path.name for path in TEST_DIR.glob("test_*.py")}

    assert files == set(TEST_FILE_PURPOSES)


def test_test_inventory_has_no_retired_categories() -> None:
    retired = {"legacy", "snapshot-only", "old-terminology"}

    assert not (set(TEST_FILE_PURPOSES.values()) & retired)

"""Shared experiment-row schema helpers.

This module does not decide whether a policy is good. It only makes the row
schema explicit so checker, summary, and offline analysis read the same fields.
"""

from __future__ import annotations


def enrich_routing_observability(record: dict, *, policy_memory_source: str = "") -> dict:
    """Add standard routing-learning fields to a completed task row."""
    routing = str(record.get("routing") or "")
    prior = record.get("routing_prior_summary") or {}
    objective = str(record.get("value_objective") or "")
    if not objective:
        profile = str(record.get("task_value_profile") or "equal")
        if profile == "equal":
            objective = "t2_equal_value_ablation"
        elif profile == "cold_start_difficulty":
            objective = "t1_cold_start_value_diagnostic"
        else:
            objective = "t1_value_efficiency"

    if routing == "budgetflow_value_aware":
        if objective == "t1_value_efficiency":
            policy_family = "bfv_t1_value_aware"
        elif objective == "t1_cold_start_value_diagnostic":
            policy_family = "bfv_cold_start_value_diagnostic"
        else:
            policy_family = "bfv_equal_value_ablation"
    elif routing == "value_aware_task_level":
        policy_family = (
            "bfv_cold_start_task_level_control"
            if objective == "t1_cold_start_value_diagnostic"
            else "bfv_t1_value_aware_task_level_control"
        )
    elif routing in {"budgetflow_conservative", "budgetflow_full", "budgetflow_equal_weight", "stage_blind"}:
        policy_family = "bfc_t2_mechanism"
    elif routing == "budget_only":
        policy_family = "bo_baseline"
    else:
        policy_family = routing or "unknown"

    record["routing_objective"] = objective
    record["routing_policy_family"] = policy_family
    record["routing_policy_memory_source"] = (
        str(prior.get("policy_memory_source") or policy_memory_source or "")
    )
    record["routing_learned_action"] = str(prior.get("learned_action") or "none")
    record["routing_imitation_active"] = bool(record.get("routing_imitation_active", False))
    record["routing_imitation_source"] = str(record.get("routing_imitation_source") or "")
    record["routing_decision_schema"] = "v1"
    return record

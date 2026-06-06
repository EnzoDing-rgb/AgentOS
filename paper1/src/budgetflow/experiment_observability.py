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
        objective = "t2_equal_value_ablation" if str(record.get("task_value_profile") or "equal") == "equal" else "t1_value_efficiency"

    if routing == "budgetflow_value_aware":
        policy_family = (
            "bfv_t1_value_aware"
            if objective == "t1_value_efficiency"
            else "bfv_equal_value_ablation"
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

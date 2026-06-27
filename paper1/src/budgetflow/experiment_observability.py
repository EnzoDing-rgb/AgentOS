"""Shared experiment-row schema helpers.

This module does not decide whether a policy is good. It only makes the row
schema explicit so checker, summary, and offline analysis read the same fields.
"""

from __future__ import annotations

from .routing_sets import ADAPTIVE_ROUTINGS


def enrich_routing_observability(record: dict, *, policy_memory_source: str = "") -> dict:
    """Add standard routing-learning fields to a completed task row."""
    routing = str(record.get("routing") or "")
    prior = record.get("routing_prior_summary") or {}
    objective = str(record.get("value_objective") or "")
    if not objective:
        primary_claim1 = bool(record.get("task_value_primary_claim1", False))
        objective = "claim1_value_efficiency" if primary_claim1 else "value_source_diagnostic"

    policy_kind = _policy_kind(routing)
    policy_role = _policy_role(routing)
    policy_family = f"{policy_kind}:{policy_role}"

    record["routing_objective"] = objective
    record["routing_policy_family"] = policy_family
    record["policy_kind"] = policy_kind
    record["policy_role"] = policy_role
    record["routing_policy_memory_source"] = (
        str(prior.get("policy_memory_source") or policy_memory_source or "")
    )
    record["routing_learned_action"] = str(prior.get("learned_action") or "none")
    record["routing_learned_action_segment"] = str(record.get("routing_prior_segment") or "")
    repair_prior = record.get("routing_repair_prior_summary") or {}
    record["routing_repair_learned_action"] = str(repair_prior.get("learned_action") or "")
    record["routing_repair_learned_action_segment"] = str(record.get("routing_repair_prior_segment") or "")
    record["routing_imitation_active"] = bool(record.get("routing_imitation_active", False))
    record["routing_imitation_source"] = str(record.get("routing_imitation_source") or "")
    record["routing_decision_schema"] = "v1"
    return record


def _policy_kind(routing: str) -> str:
    if routing in {"budgetflow_same_router"}:
        return "mechanism"
    if routing in {"bare_t3", "enterprise_router", "routellm_learned_router"}:
        return "bare_harness"
    if routing in ADAPTIVE_ROUTINGS:
        return "bootstrap"
    if routing in {"budget_only", "budget_only_t2", "all_flash", "all_tier2", "all_t3", "all_pro", "workflow_level"}:
        return "fixed_baseline"
    return "unknown"


def _policy_role(routing: str) -> str:
    roles = {
        "bare_t3": "bare_t3_baseline",
        "enterprise_router": "enterprise_router_baseline",
        "routellm_learned_router": "routellm_learned_router_baseline",
        "budgetflow_same_router": "mechanism_with_frozen_router",
        "segment_value_aware": "value_aware_segment",
        "budgetflow_conservative": "conservative_segment",
        "budgetflow_segment": "full_segment",
        "budgetflow_equal_weight": "equal_weight_segment",
        "stage_blind": "no_segment_control",
        "value_aware_task_level": "value_aware_task_level_main_policy",
        "budget_only": "budget_only_control",
        "budget_only_t2": "budget_only_mid_tier_control",
        "all_flash": "static_cheap_control",
        "all_tier2": "static_mid_tier_control",
        "all_t3": "static_strongest_control",
        "all_pro": "static_strongest_control",
        "workflow_level": "workflow_level_control",
    }
    return roles.get(routing, routing or "unknown")

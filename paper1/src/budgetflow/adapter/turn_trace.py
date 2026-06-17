from __future__ import annotations

import json
from typing import Any

from ..adapters import SwebenchCostAdapter
from ..routing_sets import ADAPTIVE_ROUTINGS
from .bash_stage import extract_trace_file_paths
from ..model_tiers import MODEL_CATALOG, tier_confidence, token_cost_rates
from .protocol_adapter import ActionProtocolAdapter
from .stall_guard import stall_guard_enabled


def progress_state(value: bool | None) -> str:
    """Normalize optional progress evidence into an auditable three-state field."""
    if value is True:
        return "progress"
    if value is False:
        return "no_progress"
    return "unknown"


def build_turn_trace(
    *,
    step_index: int,
    agent_phase: str | None,
    stage,
    workflow_segment=None,
    bash_command: str | None,
    input_tokens: int,
    expected_costs: dict[str, float],
    base_pressure: float,
    effective_pressure: float,
    backend_chosen: str,
    escalated_backend: str,
    final_backend: str,
    backend_tier: int,
    reserve_out: int,
    adaptive,
    no_progress_streak: int,
    no_progress_on_tier: int,
    turns_on_tier: int,
    has_progress: bool | None,
    progress_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
    prompt_tokens_source: str = "unknown",
    completion_tokens_source: str = "unknown",
    cost_mode: str = "unknown",
    cost_fallback_reason: str = "",
    actual_cost: float,
    billable: float,
    response_ok: bool,
    error_type: str | None,
    action_has_progress: bool | None = None,
    action_progress_reason: str | None = None,
    action_digest: str | None = None,
    action_touched_file_paths: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    cost_source: str | None = None,
    cost_updated: str | None = None,
    cost_notes: str | None = None,
    cost_estimate_source: str | None = None,
    cost_estimate_confidence: dict[str, float | str | bool] | None = None,
    cost_estimate_usd: float | None = None,
    progress_source: str | None = None,
    progress_updated: str | None = None,
    progress_notes: str | None = None,
    cost_input_per_1m: float | None = None,
    cost_output_per_1m: float | None = None,
    cost_band_input_tokens: int | None = None,
    turn_cache_input_fraction: float | None = None,
    turn_cache_policy: dict[str, float | int] | None = None,
    progress_prior: dict[str, float] | None = None,
    protocol: str | None = None,
    parser: str | None = None,
    assistant_content_head: str | None = None,
    tool_call_summary: dict | None = None,
    parser_input_snippet: str | None = None,
    parser_error_type: str | None = None,
    parser_error_message: str | None = None,
    parser_error_action_count: int | None = None,
    provider_status_code: int | None = None,
    provider_error_body: str | None = None,
    provider_request_id: str | None = None,
    provider_error_kind: str | None = None,
    provider_retryable: bool | None = None,
    reservation_id: str | None = None,
    reserved_cost: float | None = None,
    reservation_released: bool = False,
    reservation_settled: bool = False,
    router_reason: str | None = None,
    router_scores: dict[str, float] | None = None,
    router_pressure: float | None = None,
    router_branch: str | None = None,
    policy_type: str | None = None,
    policy_name: str | None = None,
    memory_mode: str | None = None,
    policy_decision: dict | None = None,
    gold_edit_guard_turns: int = 0,
    gold_edit_guard_limit: int | None = None,
    gold_edit_guard_active: bool = False,
    value_triggered_escalation_active: bool = False,
    value_triggered_escalation_turns_remaining: int = 0,
    value_triggered_escalation_opened: bool = False,
    value_triggered_escalation_reason: str | None = None,
    value_triggered_escalation_action: str | None = None,
    value_triggered_escalation_window: int | None = None,
    touched_file_paths: list[str] | None = None,
    task_value: float | None = None,
    task_value_multiplier: float | None = None,
    value_aware_active: bool = False,
    catalog_revision: str = "",
    catalog_path: str = "",
    tier_frontier_active: bool | None = None,
    tier_frontier_reason: str | None = None,
    strongest_vs_reference_cost_ratio: float | None = None,
    strongest_progress_delta: dict[str, float] | None = None,
    max_tier_before_frontier: int | None = None,
    max_tier_after_frontier: int | None = None,
    tier_frontier_score: float | None = None,
    stall_guard_enabled: bool = False,
    protocol_retry_used: bool = False,
    protocol_retry_success: bool = False,
    protocol_retry_reason: str = "",
    protocol_retry_attempts: int = 0,
    protocol_retry_limit: int | None = None,
) -> dict:
    """Build the per-turn observability record persisted in compare JSONL."""
    trace: dict[str, Any] = {
        "step": step_index,
        "agent_phase": agent_phase,
        "stage": stage.name if stage else None,
        "workflow_segment": getattr(workflow_segment, "name", None),
        "segment_signals": dict(getattr(workflow_segment, "signals", {}) or {}),
        "bash_digest": (bash_command or "")[:120],
        "touched_file_paths": touched_file_paths or [],
        "input_tokens": input_tokens,
        "expected_costs": expected_costs,
        "base_pressure": round(base_pressure, 4),
        "effective_pressure": round(effective_pressure, 4),
        "backend_chosen": backend_chosen,
        "escalated_backend": escalated_backend if escalated_backend != backend_chosen else None,
        "final_backend": final_backend,
        "backend_tier": backend_tier,
        "reserve_output_tokens": reserve_out,
        "no_progress_streak": no_progress_streak,
        "no_progress_on_tier": no_progress_on_tier,
        "turns_on_tier": turns_on_tier,
        "has_progress": has_progress,
        "progress_state": progress_state(has_progress),
        "progress_reason": progress_reason,
        "action_has_progress": action_has_progress,
        "action_progress_state": progress_state(action_has_progress),
        "action_progress_reason": action_progress_reason,
        "action_digest": (action_digest or "")[:300],
        "action_touched_file_paths": action_touched_file_paths or [],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "prompt_tokens_source": prompt_tokens_source,
        "completion_tokens_source": completion_tokens_source,
        "usage_source": (
            "provider"
            if prompt_tokens_source == "provider" and completion_tokens_source == "provider"
            else "estimated"
        ),
        "cost_mode": cost_mode,
        "cost_fallback_reason": cost_fallback_reason,
        "actual_cost": round(actual_cost, 6),
        "billable_cost": round(billable, 6),
        "response_ok": response_ok,
        "error_type": error_type,
        "provider": provider,
        "model": model,
        "cost_source": cost_source,
        "cost_updated": cost_updated,
        "cost_notes": cost_notes,
        "cost_estimate_source": cost_estimate_source,
        "cost_estimate_confidence": cost_estimate_confidence,
        "cost_estimate_usd": cost_estimate_usd,
        "progress_source": progress_source,
        "progress_updated": progress_updated,
        "progress_notes": progress_notes,
        "cost_input_per_1m": cost_input_per_1m,
        "cost_output_per_1m": cost_output_per_1m,
        "cost_band_input_tokens": cost_band_input_tokens,
        "turn_cache_input_fraction": turn_cache_input_fraction,
        "turn_cache_policy": turn_cache_policy,
        "progress_prior": progress_prior,
        "protocol": protocol,
        "parser": parser,
        "assistant_content_head": assistant_content_head,
        "tool_call_summary": tool_call_summary,
        "parser_input_snippet": parser_input_snippet,
        "parser_error_type": parser_error_type,
        "parser_error_message": parser_error_message,
        "parser_error_action_count": parser_error_action_count,
        "provider_status_code": provider_status_code,
        "provider_error_body": provider_error_body,
        "provider_request_id": provider_request_id,
        "provider_error_kind": provider_error_kind,
        "provider_retryable": provider_retryable,
        "reservation_id": reservation_id,
        "reserved_cost": reserved_cost,
        "reservation_released": reservation_released,
        "reservation_settled": reservation_settled,
        "router_reason": router_reason,
        "router_scores": router_scores,
        "router_pressure": router_pressure,
        "router_branch": router_branch,
        "policy_type": policy_type,
        "policy_name": policy_name,
        "memory_mode": memory_mode,
        "policy_decision": policy_decision,
        "gold_edit_guard_turns": gold_edit_guard_turns,
        "gold_edit_guard_limit": gold_edit_guard_limit,
        "gold_edit_guard_active": gold_edit_guard_active,
        "value_triggered_escalation_active": value_triggered_escalation_active,
        "value_triggered_escalation_turns_remaining": value_triggered_escalation_turns_remaining,
        "value_triggered_escalation_opened": value_triggered_escalation_opened,
        "value_triggered_escalation_reason": value_triggered_escalation_reason,
        "value_triggered_escalation_action": value_triggered_escalation_action,
        "value_triggered_escalation_window": value_triggered_escalation_window,
        "task_value": task_value,
        "task_value_multiplier": task_value_multiplier,
        "value_aware_active": value_aware_active,
        "catalog_revision": catalog_revision,
        "catalog_path": catalog_path,
        "tier_frontier_active": tier_frontier_active,
        "tier_frontier_reason": tier_frontier_reason,
        "strongest_vs_reference_cost_ratio": strongest_vs_reference_cost_ratio,
        "strongest_progress_delta": strongest_progress_delta,
        "max_tier_before_frontier": max_tier_before_frontier,
        "max_tier_after_frontier": max_tier_after_frontier,
        "tier_frontier_score": tier_frontier_score,
        "stall_guard_enabled": stall_guard_enabled,
        "protocol_retry_used": protocol_retry_used,
        "protocol_retry_success": protocol_retry_success,
        "protocol_retry_reason": protocol_retry_reason,
        "protocol_retry_attempts": protocol_retry_attempts,
        "protocol_retry_limit": protocol_retry_limit,
    }
    if adaptive is not None:
        trace["adaptive_ttl"] = getattr(adaptive, "ttl_steps_remaining", None)
        trace["adaptive_floor"] = adaptive.min_tier_for_reserve()
        trace["adaptive_boost"] = getattr(adaptive, "pressure_boost", None)
        rescue = getattr(adaptive, "rescue", None)
        if rescue is not None:
            trace["rescue_evidence_turns"] = getattr(rescue, "evidence_turns", None)
            trace["rescue_window_remaining"] = getattr(rescue, "window_remaining", None)
            trace["rescue_window_opened"] = getattr(rescue, "window_opened", None)
        trace["strongest_starter_action"] = getattr(adaptive, "strongest_starter_action", None)
        trace["strongest_starter_window_remaining"] = getattr(
            adaptive, "strongest_starter_window_remaining", None
        )
        trace["strongest_starter_window_opened"] = getattr(
            adaptive, "strongest_starter_window_opened", None
        )
        trace["strongest_starter_applied"] = getattr(
            adaptive, "strongest_starter_applied_this_turn", None
        )
    return trace


def router_trace_fields(routing) -> dict[str, Any]:
    decision = routing.last_decision
    if decision is None:
        return {}
    policy_decision = getattr(routing, "last_policy_decision", None)
    policy_type = _policy_type_for_routing(routing)
    policy_name = getattr(getattr(routing, "bootstrap_policy", None), "name", None) or str(getattr(routing, "strategy", ""))
    memory_mode = str(getattr(getattr(routing, "adaptive", None), "memory_mode", "off") or "off")
    fields = {
        "router_reason": decision.reason,
        "router_scores": decision.scores,
        "router_pressure": decision.pressure,
        "router_branch": decision.branch,
        "policy_type": policy_type,
        "policy_name": policy_name,
        "memory_mode": memory_mode,
        "policy_decision": {
            "backend": getattr(policy_decision, "backend", decision.backend.name),
            "reason": getattr(policy_decision, "reason", decision.reason),
            "scores": getattr(policy_decision, "scores", decision.scores),
            "budget_pressure": decision.pressure,
            "router_branch": decision.branch,
            "memory_mode": memory_mode,
        },
    }
    frontier = getattr(routing, "tier_frontier", None)
    if frontier is not None:
        fields["tier_frontier_active"] = True  # frontier is always active, advisory score replaces binary gate
        fields["tier_frontier_reason"] = frontier.reason
        fields["strongest_vs_reference_cost_ratio"] = round(
            max(frontier.strongest_input_ratio, frontier.strongest_output_ratio), 4
        )
        fields["strongest_progress_delta"] = {
            k: round(v, 4) for k, v in frontier.strongest_progress_delta.items()
        }
    fields["max_tier_before_frontier"] = getattr(routing, "max_tier_before_frontier", None)
    fields["max_tier_after_frontier"] = getattr(routing, "max_tier", None)
    score = getattr(routing, "tier_frontier_score", None)
    fields["tier_frontier_score"] = round(score, 4) if isinstance(score, (int, float)) else None
    fields["stall_guard_enabled"] = stall_guard_enabled(str(getattr(routing, "strategy", "") or ""))
    return fields


def _policy_type_for_routing(routing) -> str:
    strategy = str(getattr(routing, "strategy", "") or "")
    if getattr(routing, "bootstrap_policy", None) is not None:
        return "bootstrap"
    if strategy in ADAPTIVE_ROUTINGS:
        return "bootstrap"
    if strategy in {
        "all_flash",
        "all_tier2",
        "all_t3",
        "all_pro",
        "budget_only",
        "budget_only_t2",
        "workflow_level",
    }:
        return "fixed_baseline"
    return "unknown"


def value_aware_trace_fields(routing) -> dict[str, Any]:
    if routing.strategy not in {"segment_value_aware", "value_aware_task_level"}:
        return {}
    multiplier = getattr(routing.selector, "last_multiplier", 1.0)
    return {
        "task_value": routing.task_value,
        "task_value_multiplier": multiplier,
        "value_aware_active": True,
    }


def provider_trace_fields(backend_name: str) -> dict[str, Any]:
    cfg = MODEL_CATALOG.config_for(backend_name)
    if cfg is None:
        return {}
    confidence = tier_confidence(backend_name)
    from ..model_tiers import catalog_revision as _catalog_revision, catalog_path as _catalog_path
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "catalog_revision": _catalog_revision(),
        "catalog_path": str(_catalog_path()) if _catalog_path() else "",
        **confidence,
    }


def cost_basis_trace_fields(
    backend_name: str,
    input_tokens: int,
    *,
    turn_index: int | None = None,
) -> dict[str, Any]:
    cfg = MODEL_CATALOG.config_for(backend_name)
    if cfg is None:
        return {}
    expected = SwebenchCostAdapter(MODEL_CATALOG).estimate(
        backend_name,
        input_tokens=input_tokens,
        expected_output_tokens=cfg.mean_output_tokens,
        turn_index=turn_index,
    )
    input_rate, output_rate = token_cost_rates(
        backend_name,
        input_tokens,
        turn_index=turn_index,
    )
    cache_policy = cfg.turn_cache_policy
    input_fraction = cache_policy.input_cost_fraction(turn_index)
    stage_priors = {stage: round(value, 4) for stage, value in cfg.progress_prior.items()}
    return {
        "cost_estimate_source": expected.source,
        "cost_estimate_confidence": dict(expected.confidence),
        "cost_estimate_usd": expected.usd,
        "cost_input_per_1m": round(input_rate * 1_000_000, 6),
        "cost_output_per_1m": round(output_rate * 1_000_000, 6),
        "cost_band_input_tokens": input_tokens,
        "turn_cache_input_fraction": round(input_fraction, 4),
        "turn_cache_policy": {
            "input_discount_after_turn": cache_policy.input_discount_after_turn,
            "input_kv_cache_discount": cache_policy.input_kv_cache_discount,
            "min_input_cost_fraction": cache_policy.min_input_cost_fraction,
        },
        "progress_prior": stage_priors,
    }


def protocol_trace_fields(backend_name: str) -> dict[str, Any]:
    decision = ActionProtocolAdapter.resolve(backend_name)
    return {
        "protocol": decision.protocol,
        "parser": decision.parser,
    }


def safe_content_head(response, max_chars: int = 300) -> str | None:
    try:
        content = response.choices[0].message.content or ""
        return content[:max_chars]
    except Exception:
        return None


def tool_call_summary(response) -> dict | None:
    try:
        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            return None
        names = [tc.function.name for tc in tool_calls if hasattr(tc, "function")]
        return {"count": len(tool_calls), "names": names}
    except Exception:
        return None


def parser_input_snippet(response) -> str | None:
    summary = tool_call_summary(response)
    if summary is None:
        return None
    try:
        return json.dumps(summary)
    except Exception:
        return str(summary)


def action_trace_fields(actions: list[dict] | tuple[dict, ...] | None, *, max_chars: int = 300) -> dict:
    commands: list[str] = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        command = action.get("command")
        if isinstance(command, str) and command.strip():
            commands.append(command.strip())
    digest = "\n\n".join(commands)
    return {
        "action_digest": digest[:max_chars],
        "action_touched_file_paths": extract_trace_file_paths(bash_command=digest),
    }


def parser_error_trace_fields(exc: Exception) -> dict:
    payload = exc.args[0] if getattr(exc, "args", None) else None
    if payload is None:
        messages = getattr(exc, "messages", None)
        if isinstance(messages, (list, tuple)) and messages:
            payload = messages[0]
    message = str(exc)
    action_count = None
    if isinstance(payload, dict):
        extra = payload.get("extra") or {}
        if isinstance(extra, dict):
            raw_count = extra.get("n_actions")
            if raw_count is not None:
                try:
                    action_count = int(raw_count)
                except (TypeError, ValueError):
                    action_count = None
        content = payload.get("content")
        if not message and isinstance(content, str):
            message = content
    if not message and action_count is not None:
        message = f"Expected exactly 1 action, found {action_count}."
    return {
        "parser_error_type": type(exc).__name__,
        "parser_error_message": message[:500],
        "parser_error_action_count": action_count,
    }

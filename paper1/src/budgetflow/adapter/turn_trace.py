from __future__ import annotations

import json
from typing import Any

from ..model_tiers import MODEL_CATALOG, tier_provenance, token_cost_rates
from .protocol_adapter import ActionProtocolAdapter


def build_turn_trace(
    *,
    step_index: int,
    agent_phase: str | None,
    stage,
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
    has_progress: bool,
    progress_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
    actual_cost: float,
    billable: float,
    response_ok: bool,
    error_type: str | None,
    action_has_progress: bool | None = None,
    action_progress_reason: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    cost_source: str | None = None,
    cost_updated: str | None = None,
    cost_notes: str | None = None,
    progress_source: str | None = None,
    progress_updated: str | None = None,
    progress_notes: str | None = None,
    cost_input_per_1m: float | None = None,
    cost_output_per_1m: float | None = None,
    cost_band_input_tokens: int | None = None,
    progress_prior: dict[str, float] | None = None,
    text_mode: bool = False,
    protocol: str | None = None,
    parser: str | None = None,
    assistant_content_head: str | None = None,
    tool_call_summary: dict | None = None,
    parser_input_snippet: str | None = None,
    parser_error_type: str | None = None,
    parser_error_message: str | None = None,
    provider_status_code: int | None = None,
    provider_error_body: str | None = None,
    provider_request_id: str | None = None,
    reservation_id: str | None = None,
    reserved_cost: float | None = None,
    reservation_released: bool = False,
    reservation_settled: bool = False,
    router_reason: str | None = None,
    router_scores: dict[str, float] | None = None,
    router_pressure: float | None = None,
    router_branch: str | None = None,
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
) -> dict:
    """Build the per-turn observability record persisted in compare JSONL."""
    trace: dict[str, Any] = {
        "step": step_index,
        "agent_phase": agent_phase,
        "stage": stage.name if stage else None,
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
        "progress_reason": progress_reason,
        "action_has_progress": action_has_progress,
        "action_progress_reason": action_progress_reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "actual_cost": round(actual_cost, 6),
        "billable_cost": round(billable, 6),
        "response_ok": response_ok,
        "error_type": error_type,
        "provider": provider,
        "model": model,
        "cost_source": cost_source,
        "cost_updated": cost_updated,
        "cost_notes": cost_notes,
        "progress_source": progress_source,
        "progress_updated": progress_updated,
        "progress_notes": progress_notes,
        "cost_input_per_1m": cost_input_per_1m,
        "cost_output_per_1m": cost_output_per_1m,
        "cost_band_input_tokens": cost_band_input_tokens,
        "progress_prior": progress_prior,
        "text_mode": text_mode,
        "protocol": protocol,
        "parser": parser,
        "assistant_content_head": assistant_content_head,
        "tool_call_summary": tool_call_summary,
        "parser_input_snippet": parser_input_snippet,
        "parser_error_type": parser_error_type,
        "parser_error_message": parser_error_message,
        "provider_status_code": provider_status_code,
        "provider_error_body": provider_error_body,
        "provider_request_id": provider_request_id,
        "reservation_id": reservation_id,
        "reserved_cost": reserved_cost,
        "reservation_released": reservation_released,
        "reservation_settled": reservation_settled,
        "router_reason": router_reason,
        "router_scores": router_scores,
        "router_pressure": router_pressure,
        "router_branch": router_branch,
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
    return {
        "router_reason": decision.reason,
        "router_scores": decision.scores,
        "router_pressure": decision.pressure,
        "router_branch": decision.branch,
    }


def value_aware_trace_fields(routing) -> dict[str, Any]:
    if routing.strategy not in {"budgetflow_value_aware", "value_aware_task_level"}:
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
    provenance = tier_provenance(backend_name)
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        **provenance,
    }


def cost_basis_trace_fields(backend_name: str, input_tokens: int) -> dict[str, Any]:
    cfg = MODEL_CATALOG.config_for(backend_name)
    if cfg is None:
        return {}
    input_rate, output_rate = token_cost_rates(backend_name, input_tokens)
    stage_priors = {stage: round(value, 4) for stage, value in cfg.progress_prior.items()}
    return {
        "cost_input_per_1m": round(input_rate * 1_000_000, 6),
        "cost_output_per_1m": round(output_rate * 1_000_000, 6),
        "cost_band_input_tokens": input_tokens,
        "progress_prior": stage_priors,
    }


def protocol_trace_fields(backend_name: str, text_mode: bool) -> dict[str, Any]:
    decision = ActionProtocolAdapter.resolve(backend_name)
    return {
        "text_mode": text_mode,
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


def parser_input_snippet(response, text_mode: bool) -> str | None:
    if text_mode:
        return safe_content_head(response, max_chars=500)
    summary = tool_call_summary(response)
    if summary is None:
        return None
    try:
        return json.dumps(summary)
    except Exception:
        return str(summary)

from __future__ import annotations

import logging
import os
from collections import deque
from collections.abc import Callable
from typing import Any

import litellm
from minisweagent.models.utils.actions_toolcall import BASH_TOOL, format_toolcall_observation_messages
from minisweagent.exceptions import FormatError
from minisweagent.models.utils.anthropic_utils import _reorder_anthropic_thinking_blocks
from minisweagent.models.utils.cache_control import set_cache_control
from minisweagent.models.utils.openai_multimodal import expand_multimodal_content
from minisweagent.models.utils.retry import retry

from ..litellm_quiet import configure_litellm_quiet
from ..budget_pressure import live_budget_pressure
from ..defaults import (
    GOLD_EDIT_MID_TIER_REPAIR_TURN_LIMIT,
    GOLD_EDIT_SUBMIT_GRACE_TURNS,
    PRESSURE_MAX,
    STRONGEST_DOWNGRADE_TIER,
    VALUE_TRIGGERED_ESCALATION_DEFAULT_WINDOW_TURNS,
    VALUE_TRIGGERED_ESCALATION_MIN_HEADROOM_FRAC,
    VALUE_TRIGGERED_ESCALATION_MIN_MULTIPLIER,
    tier_escalation_patience,
    tier_max_turns,
)
from ..model_tiers import MODEL_CATALOG, ModelCatalog, estimate_token_cost, load_env_file
from ..console_log import backend_tier_label, bold, dim, routing_stage_label, tag
from ..governor import BudgetGovernor
from ..types import Backend, Stage, TurnInfo, WorkflowSegment, WorkflowStatus
from .errors import BudgetFlowBudgetError, BudgetFlowStagnationError, BudgetFlowUpstreamError
from ..run_guards import get_active_guard, is_fatal_billing_error, record_billing_halt, record_upstream_error
from ..adapters import SwebenchProgressAdapter
from ..routing_sets import (
    ADAPTIVE_ROUTINGS,
    GOLD_EDIT_REPAIR_GUARD_ROUTINGS,
    IN_TASK_SWITCHING_ROUTINGS,
    VALUE_TRIGGERED_ESCALATION_ROUTINGS,
)
from .action_parsing import format_error_stop_after, parse_tool_actions
from .stall_guard import (
    check_agent_loop_stop,
    check_post_patch_stop,
    check_stagnation,
    normalize_bash_command,
    stall_guard_enabled,
)
from .message_utils import estimate_input_tokens, extract_bash_context
from .protocol_adapter import ActionProtocolAdapter
from .strategies import RoutingContext, choose_backend, stage_weight
from .turn_trace import (
    build_turn_trace,
    action_trace_fields,
    cost_basis_trace_fields,
    parser_input_snippet,
    parser_error_trace_fields,
    protocol_trace_fields,
    provider_trace_fields,
    router_trace_fields,
    safe_content_head,
    tool_call_summary,
    value_aware_trace_fields,
)

logger = logging.getLogger("budgetflow_litellm_model")

configure_litellm_quiet()

DEFAULT_LLM_TIMEOUT_S = 90.0
_PROVIDER_UNAVAILABLE_MARKERS = (
    "service temporarily unavailable",
    "serviceunavailableerror",
    "model is not supported",
    "model_not_found",
    "model not found",
    "model unavailable",
    "not available",
    "not provided",
    "no such model",
    "\"code\":404",
    "503",
)


def _llm_timeout_s() -> float:
    raw = os.environ.get("BUDGETFLOW_LLM_TIMEOUT_S", "").strip()
    if not raw:
        return DEFAULT_LLM_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_S
    return max(10.0, value)


def _is_provider_unavailable(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {404, 503}:
        return True
    exc_name = type(exc).__name__
    if exc_name in ("APITimeoutError", "Timeout", "APIConnectionError", "APIStatusError", "_ProviderTimeoutError"):
        return True
    # Unwrap _ProviderTimeoutError to check the original exception
    original = getattr(exc, "original", None)
    if original is not None:
        orig_name = type(original).__name__
        if orig_name in ("APITimeoutError", "Timeout", "ReadTimeout", "ConnectTimeout"):
            return True
    text = f"{exc_name} {exc}".lower()
    if "timeout" in text or "timed out" in text or "connection" in text:
        return True
    return any(marker in text for marker in _PROVIDER_UNAVAILABLE_MARKERS)


def _provider_error_kind(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    text = f"{type(exc).__name__} {exc}".lower()
    if is_fatal_billing_error(text):
        return "billing"
    if status_code in {401, 403} or "unauthorized" in text or "forbidden" in text or "api key" in text:
        return "auth"
    if status_code == 429 or "rate limit" in text or "too many requests" in text:
        return "rate_limit"
    if status_code in {404} or "model_not_found" in text or "model not found" in text or "no such model" in text:
        return "model_unavailable"
    if status_code == 400 or "badrequest" in text:
        return "bad_request"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if status_code in {500, 502, 503, 504} or _is_provider_unavailable(exc):
        return "transient_provider"
    return "unknown_provider"


def _provider_error_retryable(kind: str) -> bool:
    return kind in {"timeout", "rate_limit", "model_unavailable", "transient_provider"}


def _backend_by_configured_tier(backends: list[Backend], tier: int) -> Backend | None:
    return next((backend for backend in backends if backend.tier == tier), None)


def _routing_trigger_source(
    backend_chosen: str,
    final_backend: str,
    override_source: str,
    router_reason: str | None,
) -> str:
    if override_source:
        return override_source
    if final_backend == backend_chosen:
        if router_reason and "task_start" in router_reason:
            return "task_start_routing"
        return "router"
    return "router_override"


def _usage_accounting(response, *, input_tokens: int, fallback_output_tokens: int) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    provider_prompt = getattr(usage, "prompt_tokens", None) if usage is not None else None
    provider_completion = getattr(usage, "completion_tokens", None) if usage is not None else None
    prompt_tokens_source = "provider" if provider_prompt is not None else "estimated_input"
    completion_tokens_source = "provider" if provider_completion is not None else "estimated_output_mean"
    reasons: list[str] = []
    if provider_prompt is None:
        reasons.append("missing_prompt_tokens")
    if provider_completion is None:
        reasons.append("missing_completion_tokens")
    return {
        "prompt_tokens": int(provider_prompt if provider_prompt is not None else input_tokens),
        "completion_tokens": int(provider_completion if provider_completion is not None else fallback_output_tokens),
        "prompt_tokens_source": prompt_tokens_source,
        "completion_tokens_source": completion_tokens_source,
        "usage_source": (
            "provider"
            if prompt_tokens_source == "provider" and completion_tokens_source == "provider"
            else "estimated"
        ),
        "cost_mode": (
            "catalog_provider_usage"
            if prompt_tokens_source == "provider" and completion_tokens_source == "provider"
            else "catalog_estimated_usage"
        ),
        "cost_fallback_reason": ",".join(reasons),
    }


class FatalProviderBillingError(RuntimeError):
    """Provider billing/account errors should bypass mini-SWE retry backoff."""

    def __init__(self, original: Exception) -> None:
        self.original = original
        super().__init__(str(original))


class _ProviderTimeoutError(RuntimeError):
    """Timeout errors should skip tenacity retry and surface as provider failures."""

    def __init__(self, original: Exception) -> None:
        self.original = original
        super().__init__(str(original))


# ── Protocol format retry ──────────────────────────────────────────────────

_FORMAT_RETRY_PROMPT = (
    "Your previous response had invalid action format. "
    "Call exactly one bash tool. Do not answer with a fenced text command."
)


def _format_retry_assistant_message(response) -> dict[str, str]:
    """Return an OpenAI-valid assistant message for protocol retry history."""
    raw = response.choices[0].message.model_dump()
    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        content = "The previous response contained invalid tool calls and was not executed."
    return {"role": "assistant", "content": content}


def _classify_format_reason(exc: Exception, response) -> str:
    """Classify a FormatError into a stable reason code for observability."""
    # Extract action count from FormatError payload
    payload = exc.args[0] if getattr(exc, "args", None) else None
    if payload is None:
        messages = getattr(exc, "messages", None)
        if messages:
            try:
                payload = messages[0]
            except (IndexError, TypeError):
                payload = None
    if isinstance(payload, dict):
        extra = payload.get("extra") or {}
        if isinstance(extra, dict):
            count = extra.get("n_actions")
            if count is not None:
                try:
                    n = int(count)
                    if n == 0:
                        return "found_0_actions"
                    if n >= 2:
                        return "found_2_actions"
                except (TypeError, ValueError):
                    pass

    tool_calls = []
    try:
        tool_calls = response.choices[0].message.tool_calls or []
    except Exception:
        pass
    if not tool_calls:
        return "found_0_actions"
    return "invalid_tool_call"


def _format_error_limit_for(exc: Exception, response, backend_tier: int | None = None) -> tuple[str, int]:
    reason = _classify_format_reason(exc, response)
    return reason, format_error_stop_after(backend_tier, error_reason=reason)


class BudgetFlowLitellmModel:
    """mini-SWE-agent Model: BudgetFlow governor + spark/flash/pro tier pool."""

    def __init__(
        self,
        *,
        workflow_id: str,
        governor: BudgetGovernor,
        routing: RoutingContext,
        default_max_output_tokens: int = 4096,
        cost_tracking: str = "ignore_errors",
        observation_template: str | None = None,
        format_error_template: str | None = None,
        set_cache_control: str | None = None,
        multimodal_regex: str = "",
        progress_refresh: Callable[[], None] | None = None,
        enable_turn_trace: bool = False,
    ) -> None:
        load_env_file()
        self.workflow_id = workflow_id
        self.governor = governor
        self.routing = routing
        self._pressure_init = routing.budget_pressure
        self._pressure_max = routing.pressure_max if routing.pressure_max is not None else PRESSURE_MAX
        self.default_max_output_tokens = default_max_output_tokens
        self.cost_tracking = cost_tracking
        self.observation_template = observation_template or (
            "{% if output.exception_info %}<exception>{{output.exception_info}}</exception>\n{% endif %}"
            "<returncode>{{output.returncode}}</returncode>\n<output>\n{{output.output}}</output>"
        )
        self.format_error_template = format_error_template or "{{ error }}"
        self.set_cache_control = set_cache_control
        self.multimodal_regex = multimodal_regex
        self._api_keys = {config.api_key_env: os.environ.get(config.api_key_env) for config in MODEL_CATALOG.configs}
        missing_keys = sorted(
            {
                MODEL_CATALOG.require_config(b.name).api_key_env
                for b in routing.backends
                if not self._api_keys.get(MODEL_CATALOG.require_config(b.name).api_key_env)
            }
        )
        if missing_keys:
            raise RuntimeError(f"{', '.join(missing_keys)} is missing. Add it to the repo root .env file.")
        self.step_index = 0
        self._no_progress_streak = 0
        self._no_progress_on_current_tier = 0  # consecutive non-progress steps on current tier
        self._turns_on_current_tier = 0  # total turns on current tier (for turn cap)
        self._gold_edit_mid_tier_repair_turns = 0
        self._gold_edit_stop_loss_grace_turns = 0
        self._last_backend_tier: int = 0  # track tier changes to reset patience
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._recent_commands: deque[str] = deque(maxlen=16)
        self._progress_refresh = progress_refresh
        self.backend_picks: list[str] = []
        self.last_routing_stage: str = "localization"
        self.last_backend_name: str = "-"
        self.agent_phase: str | None = None
        self.agent_gold_edited: bool = False
        self.agent_pytest: str | None = None
        self.agent_patch_digest: str | None = None
        self.agent_patch_stable_steps: int = 0
        self.agent_attempted_submit: bool = False
        self.agent_submitted: bool = False
        self.last_exit_reason: str | None = None
        self.last_budget_snapshot: dict[str, float] | None = None
        self._enable_turn_trace: bool = enable_turn_trace
        self.turn_traces: list[dict] = []
        self._last_reservation_id: str | None = None
        self._last_reserve_out: int = 0
        self._format_error_streak: int = 0
        self._provider_usage_turns: int = 0
        self._estimated_usage_turns: int = 0
        self._protocol_retry_used: bool = False
        self._protocol_retry_success: bool = False
        self._protocol_retry_reason: str = ""
        self._protocol_retry_attempts: int = 0
        self._protocol_retry_limit: int = 4
        self._value_triggered_escalation_turns_remaining = 0
        self._value_triggered_escalation_opened = False
        self._value_triggered_escalation_reason: str | None = None
        self._value_triggered_escalation_action = "default"
        self._value_triggered_escalation_window = VALUE_TRIGGERED_ESCALATION_DEFAULT_WINDOW_TURNS
        self._progress_adapter = SwebenchProgressAdapter()
        strongest = ModelCatalog.strongest(routing.backends)
        self.config = type("Config", (), {"model_name": MODEL_CATALOG.require_config(strongest.name).model})()

    def query(self, messages: list[dict[str, str]], **kwargs) -> dict:
        self.step_index += 1
        active_guard = get_active_guard()
        if active_guard is not None and active_guard.is_aborted():
            reason = active_guard.abort_reason() or "global_run_guard"
            self.last_exit_reason = reason
            self.last_budget_snapshot = self.governor.budget_snapshot()
            raise BudgetFlowUpstreamError(
                self.workflow_id,
                exit_reason=reason,
                step_index=self.step_index,
                backend=self.last_backend_name if self.last_backend_name != "-" else None,
                sample="global run guard halted before provider call",
            )
        turn_protocol_retry_used = False
        turn_protocol_retry_success = False
        turn_protocol_retry_reason = ""
        turn_protocol_retry_attempts = 0
        turn_protocol_retry_limit = self._protocol_retry_limit
        should_stop_patch, post_patch_reason = check_post_patch_stop(
            strategy=self.routing.strategy,
            patch_digest=self.agent_patch_digest,
            patch_stable_steps=self.agent_patch_stable_steps,
            agent_pytest=self.agent_pytest,
            agent_phase=self.agent_phase,
            agent_gold_edited=self.agent_gold_edited,
            agent_attempted_submit=self.agent_attempted_submit,
            agent_submitted=self.agent_submitted,
        )
        if should_stop_patch:
            print(
                f"{tag('stop', bold=False)} #{self.step_index} "
                f"reason={post_patch_reason} stable={self.agent_patch_stable_steps} "
                f"pytest={self.agent_pytest}",
                flush=True,
            )
            raise BudgetFlowStagnationError(
                self.workflow_id,
                exit_reason=post_patch_reason,
                step_index=self.step_index,
                no_progress_streak=self.agent_patch_stable_steps,
            )
        bash_command, observation = extract_bash_context(messages)
        progress_signal = self._progress_adapter.signal_from_context(
            bash_command=bash_command,
            observation=observation,
            agent_phase=self.agent_phase,
        )
        stage = progress_signal.stage
        input_tokens = estimate_input_tokens(messages)
        turn = TurnInfo(
            workflow_id=self.workflow_id,
            step_index=self.step_index,
            stage=stage,
            w_i=1.0 if self.routing.strategy in ("stage_blind", "budgetflow_equal_weight") else stage_weight(stage),
            context_len=input_tokens,
            tool_name="bash",
            segment=progress_signal.segment,
        )
        expected_costs = {
            backend.name: self.governor.estimate_cost(
                backend,
                input_tokens=input_tokens,
                max_output_tokens=self.default_max_output_tokens,
                turn_index=self.step_index,
            ).expected_cost
            for backend in self.routing.backends
        }
        base_pressure = live_budget_pressure(
            self.governor,
            init=self._pressure_init,
            pressure_max=self._pressure_max,
        )
        adaptive = self.routing.adaptive
        if adaptive is not None:
            adaptive.on_step()
            self.routing.budget_pressure = adaptive.effective_pressure(base_pressure)
        else:
            self.routing.budget_pressure = base_pressure
        has_progress = progress_signal.has_progress
        progress_reason = progress_signal.progress_reason
        if has_progress is True:
            self._no_progress_streak = 0
            self._no_progress_on_current_tier = 0
        elif has_progress is False:
            self._no_progress_streak += 1
            self._no_progress_on_current_tier += 1
        norm_cmd = normalize_bash_command(bash_command)
        if norm_cmd:
            self._recent_commands.append(norm_cmd)
        should_stop_loop, loop_reason, loop_repeat_cmd = check_agent_loop_stop(
            patch_digest=self.agent_patch_digest,
            patch_stable_steps=self.agent_patch_stable_steps,
            recent_commands=self._recent_commands,
            agent_gold_edited=self.agent_gold_edited,
            agent_attempted_submit=self.agent_attempted_submit,
            agent_submitted=self.agent_submitted,
        )
        if should_stop_loop:
            print(
                f"{tag('stall', bold=False)} #{self.step_index} "
                f"reason={loop_reason} stable={self.agent_patch_stable_steps} "
                f"repeat={loop_repeat_cmd or '-'}",
                flush=True,
            )
            raise BudgetFlowStagnationError(
                self.workflow_id,
                exit_reason=loop_reason,
                step_index=self.step_index,
                repeat_command=loop_repeat_cmd,
                no_progress_streak=self.agent_patch_stable_steps,
            )
        if stall_guard_enabled(self.routing.strategy):
            allocation = self.routing.allocation
            should_stop, stall_reason, repeat_cmd = check_stagnation(
                strategy=self.routing.strategy,
                no_progress_streak=self._no_progress_streak,
                recent_commands=self._recent_commands,
                task_effort=allocation.task_effort if allocation is not None else None,
                task_spent=self.governor.state.spent_budget,
                planned_task_budget=allocation.planned_task_budget if allocation is not None else None,
            )
        else:
            should_stop, stall_reason, repeat_cmd = False, "", None
        if should_stop:
            if self._maybe_open_value_triggered_escalation(stall_reason):
                should_stop = False
            elif self._value_triggered_escalation_turns_remaining > 0:
                should_stop = False
            elif self._value_triggered_escalation_opened:
                self._value_triggered_escalation_reason = f"expired_{stall_reason}"
        if should_stop:
            print(
                f"{tag('stall', bold=False)} #{self.step_index} "
                f"reason={stall_reason} streak={self._no_progress_streak} "
                f"repeat={repeat_cmd or '-'}",
                flush=True,
            )
            raise BudgetFlowStagnationError(
                self.workflow_id,
                exit_reason=stall_reason,
                step_index=self.step_index,
                repeat_command=repeat_cmd,
                no_progress_streak=self._no_progress_streak,
            )

        backend = choose_backend(self.routing, turn, expected_costs)
        backend_chosen = backend.name
        routing_override_source = ""
        # Adaptive starting tier: skip T1/T2 on first step if strategy is on a losing streak
        if self.step_index == 1 and self.routing.adaptive is not None:
            min_start = self.routing.adaptive.starting_tier()
            if backend.tier < min_start:
                backend = ModelCatalog.at_or_above(self.routing.backends, min_start)
                routing_override_source = "adaptive_floor"
                print(
                    f"{tag('adapt', bold=False)} #{self.step_index} "
                    f"starting_tier={min_start} ({backend_tier_label(backend.name)})",
                    flush=True,
                )
        if self.routing.adaptive is not None and self.routing.strategy in IN_TASK_SWITCHING_ROUTINGS:
            forced_start = self.routing.adaptive.consume_strongest_starter_tier(
                ModelCatalog.strongest(self.routing.backends).tier
            )
            if forced_start is not None and backend.tier < forced_start:
                candidate = ModelCatalog.at_or_above(self.routing.backends, forced_start)
                print(
                    f"{tag('adapt', bold=False)} #{self.step_index} "
                    f"strongest_starter_window tier>={forced_start} "
                    f"{backend_tier_label(backend.name)} -> {backend_tier_label(candidate.name)}",
                    flush=True,
                )
                backend = candidate
                routing_override_source = "starter_memory"
        protect_strongest_this_turn = False
        if self.routing.adaptive is not None and self.routing.strategy in IN_TASK_SWITCHING_ROUTINGS:
            forced_tier = self.routing.adaptive.rescue.forced_min_tier(
                segment=progress_signal.segment,
                gold_edited=self.agent_gold_edited,
                current_tier=backend.tier,
                remaining_budget=self.governor.remaining_budget(),
                total_budget=self.governor.state.total_budget,
            )
            if forced_tier is not None and backend.tier < forced_tier:
                ordered = self.routing.backends
                candidate = next((b for b in ordered if b.tier >= forced_tier), ordered[-1])
                print(
                    f"{tag('rescue', bold=False)} #{self.step_index} "
                    f"evidence_window tier>={forced_tier} "
                    f"{backend_tier_label(backend.name)} -> {backend_tier_label(candidate.name)}",
                    flush=True,
                )
                backend = candidate
                routing_override_source = "rescue_window"
                strongest_tier = ModelCatalog.strongest(self.routing.backends).tier
                protect_strongest_this_turn = candidate.tier >= strongest_tier
            stop_loss = self._defer_gold_edit_stop_loss(
                self.routing.adaptive.rescue.should_stop_loss(gold_edited=self.agent_gold_edited)
            )
            if stop_loss:
                exit_reason = "submit_timeout_after_gold_edit"
                print(
                    f"{tag('stop', bold=False)} #{self.step_index} "
                    f"{exit_reason} evidence_turns="
                    f"{self.routing.adaptive.rescue.evidence_turns}",
                    flush=True,
                )
                raise BudgetFlowStagnationError(
                    self.workflow_id,
                    exit_reason=exit_reason,
                    step_index=self.step_index,
                    no_progress_streak=self._no_progress_streak,
                )
        prev_tier = self._last_backend_tier
        before_hook_backend = backend
        backend = self._apply_value_triggered_escalation(backend, stage)
        if backend.name != before_hook_backend.name:
            routing_override_source = "value_escalation"
        before_hook_backend = backend
        backend = self._apply_progress_escalation(
            backend,
            protect_strongest_this_turn=protect_strongest_this_turn,
        )
        if backend.name != before_hook_backend.name:
            routing_override_source = "progress_escalation"
        before_hook_backend = backend
        backend = self._apply_gold_edit_repair_guard(backend, progress_signal.segment)
        if backend.name != before_hook_backend.name:
            routing_override_source = "gold_edit_guard"
        escalated_backend = backend.name
        backend = self._reserve_backend(backend, input_tokens)
        routing_trigger_source = _routing_trigger_source(
            backend_chosen,
            backend.name,
            routing_override_source,
            getattr(getattr(self.routing, "last_decision", None), "reason", None),
        )
        reserve_out = self._last_reserve_out
        if backend.tier != prev_tier and prev_tier > 0:
            self._no_progress_on_current_tier = 0
            self._turns_on_current_tier = 0
        self._last_backend_tier = backend.tier
        self._turns_on_current_tier += 1
        guarded_tier = ModelCatalog.second_cheapest(self.routing.backends).tier
        if (
            self.agent_gold_edited
            and progress_signal.segment.name in (WorkflowSegment.ACTION, WorkflowSegment.VERIFICATION)
            and backend.tier == guarded_tier
        ):
            self._gold_edit_mid_tier_repair_turns += 1
        if backend.tier >= ModelCatalog.strongest(self.routing.backends).tier and self._value_triggered_escalation_turns_remaining > 0:
            self._value_triggered_escalation_turns_remaining -= 1
        self.routing.last_backend = backend
        self.backend_picks.append(backend.name)
        self.last_routing_stage = stage.value
        self.last_backend_name = backend.name
        print(
            f"{tag('route', bold=False)} #{self.step_index} "
            f"{dim(self.workflow_id)} "
            f"strategy={bold(self.routing.strategy)} "
            f"model={backend_tier_label(backend.name)} "
            f"stage={routing_stage_label(stage.value)}",
            flush=True,
        )
        self._refresh_progress()

        model_name, model_kwargs = self._model_config_for(backend)
        try:
            response = self._completion(
                messages,
                backend_name=backend.name,
                model_name=model_name,
                model_kwargs=model_kwargs,
                **kwargs,
            )
        except Exception as exc:
            error_type = type(exc).__name__
            provider_error_kind = _provider_error_kind(exc)
            failed_reservation_id = self._last_reservation_id
            self._release_last_reservation()
            if self._enable_turn_trace:
                self.turn_traces.append(build_turn_trace(
                    step_index=self.step_index,
                    agent_phase=self.agent_phase,
                    stage=stage,
                    workflow_segment=progress_signal.segment,
                    bash_command=bash_command,
                    touched_file_paths=progress_signal.touched_file_paths,
                    input_tokens=input_tokens,
                    expected_costs=expected_costs,
                    base_pressure=base_pressure,
                    effective_pressure=self.routing.budget_pressure,
                    backend_chosen=backend_chosen,
                    escalated_backend=escalated_backend,
                    final_backend=backend.name,
                    backend_tier=backend.tier,
                    routing_trigger_source=routing_trigger_source,
                    reserve_out=reserve_out,
                    adaptive=self.routing.adaptive,
                    no_progress_streak=self._no_progress_streak,
                    no_progress_on_tier=self._no_progress_on_current_tier,
                    turns_on_tier=self._turns_on_current_tier,
                    has_progress=has_progress,
                    progress_reason=progress_reason,
                    action_has_progress=None,
                    action_progress_reason=None,
                    prompt_tokens=0,
                    completion_tokens=0,
                    actual_cost=0.0,
                    billable=0.0,
                    response_ok=False,
                    error_type=error_type,
                    **provider_trace_fields(backend.name),
                    **cost_basis_trace_fields(backend.name, input_tokens, turn_index=self.step_index),
                    **protocol_trace_fields(backend.name),
                    **router_trace_fields(self.routing),
                    **value_aware_trace_fields(self.routing),
                    **self._gold_edit_guard_trace_fields(),
                    provider_status_code=getattr(exc, "status_code", None),
                    provider_error_body=str(exc)[:500],
                    provider_error_kind=provider_error_kind,
                    provider_retryable=_provider_error_retryable(provider_error_kind),
                    reservation_id=failed_reservation_id,
                    reservation_released=True,
                ))
            if not _is_provider_unavailable(exc):
                raise
            self.last_exit_reason = "provider_unavailable"
            self.last_budget_snapshot = self.governor.budget_snapshot()
            print(
                f"{tag('provider', bold=False)} #{self.step_index} unavailable "
                f"{backend_tier_label(backend.name)} fail_fast",
                flush=True,
            )
            raise BudgetFlowUpstreamError(
                self.workflow_id,
                exit_reason="provider_unavailable",
                step_index=self.step_index,
                backend=backend.name,
                sample=str(exc),
            ) from exc
        message = response.choices[0].message.model_dump()
        usage = _usage_accounting(
            response,
            input_tokens=input_tokens,
            fallback_output_tokens=backend.mean_output_tokens,
        )
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        if usage["usage_source"] == "provider":
            self._provider_usage_turns += 1
        else:
            self._estimated_usage_turns += 1
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        actual_cost = estimate_token_cost(
            backend.name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            turn_index=self.step_index,
        )
        reservation_id = self._last_reservation_id
        snap = self.governor.budget_snapshot()
        spend_headroom = max(0.0, snap["total_budget"] - snap["spent_budget"])
        billable = min(actual_cost, spend_headroom)
        self.governor.settle(reservation_id, actual_cost, WorkflowStatus.RUNNING)
        self._last_reservation_id = None
        self._last_reserve_out = 0
        _parse_error: Exception | None = None
        try:
            actions = self._parse_actions(response, backend_tier=backend.tier)
        except FormatError as _fe:
            turn_protocol_retry_reason, turn_protocol_retry_limit = _format_error_limit_for(
                _fe, response, backend.tier
            )
            self._protocol_retry_reason = turn_protocol_retry_reason
            self._protocol_retry_limit = turn_protocol_retry_limit
            if turn_protocol_retry_used:
                _parse_error = _fe
            else:
                # One bounded retry with format correction prompt
                turn_protocol_retry_used = True
                self._protocol_retry_used = True
                # Write turn trace for the failed parse attempt
                if self._enable_turn_trace:
                    _content_head = safe_content_head(response)
                    _parser_snippet = parser_input_snippet(response)
                    _parser_error_fields = parser_error_trace_fields(_fe)
                    _parser_progress_signal = self._progress_adapter.signal_from_context(
                        bash_command=bash_command,
                        observation=observation,
                        agent_phase=self.agent_phase,
                        assistant_content_head=_content_head,
                        parser_input_snippet=_parser_snippet,
                    )
                    self.turn_traces.append(build_turn_trace(
                        step_index=self.step_index,
                        agent_phase=self.agent_phase,
                        stage=stage,
                        workflow_segment=_parser_progress_signal.segment,
                        bash_command=bash_command,
                        touched_file_paths=_parser_progress_signal.touched_file_paths,
                        input_tokens=input_tokens,
                        expected_costs=expected_costs,
                        base_pressure=base_pressure,
                        effective_pressure=self.routing.budget_pressure,
                        backend_chosen=backend_chosen,
                        escalated_backend=escalated_backend,
                        final_backend=backend.name,
                        backend_tier=backend.tier,
                        routing_trigger_source=routing_trigger_source,
                        reserve_out=reserve_out,
                        adaptive=self.routing.adaptive,
                        no_progress_streak=self._no_progress_streak,
                        no_progress_on_tier=self._no_progress_on_current_tier,
                        turns_on_tier=self._turns_on_current_tier,
                        has_progress=has_progress,
                        progress_reason=progress_reason,
                        action_has_progress=None,
                        action_progress_reason=None,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        prompt_tokens_source=usage["prompt_tokens_source"],
                        completion_tokens_source=usage["completion_tokens_source"],
                        cost_mode=usage["cost_mode"],
                        cost_fallback_reason=usage["cost_fallback_reason"],
                        actual_cost=actual_cost,
                        billable=billable,
                        response_ok=True,
                        error_type=type(_fe).__name__,
                        **provider_trace_fields(backend.name),
                        **cost_basis_trace_fields(backend.name, prompt_tokens, turn_index=self.step_index),
                        **protocol_trace_fields(backend.name),
                        **router_trace_fields(self.routing),
                        **value_aware_trace_fields(self.routing),
                        **self._gold_edit_guard_trace_fields(),
                        protocol_retry_used=turn_protocol_retry_used,
                        protocol_retry_success=False,
                        protocol_retry_reason=turn_protocol_retry_reason,
                        protocol_retry_attempts=0,
                        protocol_retry_limit=turn_protocol_retry_limit,
                        assistant_content_head=_content_head,
                        tool_call_summary=tool_call_summary(response),
                        parser_input_snippet=_parser_snippet,
                        **_parser_error_fields,
                        reservation_id=reservation_id,
                        reserved_cost=round(actual_cost, 6),
                        reservation_settled=True,
                    ))
                # Attempt retry
                try:
                    assistant_msg = _format_retry_assistant_message(response)
                    retry_user_msg = {"role": "user", "content": _FORMAT_RETRY_PROMPT}
                    retry_messages = list(messages) + [assistant_msg, retry_user_msg]
                    retry_input_tokens = estimate_input_tokens(retry_messages)
                    # Reserve for retry call
                    retry_estimate = self.governor.estimate_cost(
                        backend,
                        input_tokens=retry_input_tokens,
                        expected_output_tokens=backend.mean_output_tokens,
                        reserve_output_tokens=self.default_max_output_tokens,
                        turn_index=self.step_index,
                    )
                    retry_reservation = self.governor.reserve(self.workflow_id, backend, retry_estimate)
                    if retry_reservation is None:
                        raise BudgetFlowBudgetError(
                            self.workflow_id,
                            exit_reason="budget_exhausted",
                            step_index=self.step_index,
                            backend=backend.name,
                        )
                    self._last_reservation_id = retry_reservation.reservation_id
                    retry_response = self._completion(
                        retry_messages,
                        backend_name=backend.name,
                        model_name=model_name,
                        model_kwargs=model_kwargs,
                        **kwargs,
                    )
                    # Settle retry reservation
                    retry_usage = _usage_accounting(
                        retry_response,
                        input_tokens=retry_input_tokens,
                        fallback_output_tokens=backend.mean_output_tokens,
                    )
                    retry_prompt_tokens = retry_usage["prompt_tokens"]
                    retry_completion_tokens = retry_usage["completion_tokens"]
                    if retry_usage["usage_source"] == "provider":
                        self._provider_usage_turns += 1
                    else:
                        self._estimated_usage_turns += 1
                    retry_actual_cost = estimate_token_cost(
                        backend.name,
                        input_tokens=retry_prompt_tokens,
                        output_tokens=retry_completion_tokens,
                        turn_index=self.step_index,
                    )
                    self.governor.settle(retry_reservation.reservation_id, retry_actual_cost, WorkflowStatus.RUNNING)
                    self._last_reservation_id = None
                    self._last_reserve_out = 0
                    # Parse retry response — must succeed this time
                    actions = self._parse_actions(retry_response, backend_tier=backend.tier)
                    turn_protocol_retry_success = True
                    self._protocol_retry_success = True
                    # Use retry response for the rest of this turn
                    response = retry_response
                    message = retry_response.choices[0].message.model_dump()
                    self._total_prompt_tokens += retry_prompt_tokens
                    self._total_completion_tokens += retry_completion_tokens
                    prompt_tokens += retry_prompt_tokens
                    completion_tokens += retry_completion_tokens
                    actual_cost += retry_actual_cost
                    billable += min(retry_actual_cost, max(0.0, snap["total_budget"] - snap["spent_budget"] - billable))
                    if usage["usage_source"] == "provider" and retry_usage["usage_source"] == "provider":
                        usage["prompt_tokens_source"] = "provider"
                        usage["completion_tokens_source"] = "provider"
                        usage["usage_source"] = "provider"
                        usage["cost_mode"] = "catalog_provider_usage"
                        usage["cost_fallback_reason"] = ""
                    else:
                        usage["prompt_tokens_source"] = "mixed_or_estimated"
                        usage["completion_tokens_source"] = "mixed_or_estimated"
                        usage["usage_source"] = "estimated"
                        usage["cost_mode"] = "catalog_estimated_usage"
                        usage["cost_fallback_reason"] = ",".join(
                            reason
                            for reason in (
                                usage.get("cost_fallback_reason"),
                                retry_usage.get("cost_fallback_reason"),
                            )
                            if reason
                        )
                except Exception as _retry_exc:
                    if self._last_reservation_id is not None:
                        self._release_last_reservation()
                    turn_protocol_retry_success = False
                    self._protocol_retry_success = False
                    _parse_error = _retry_exc
                    if self._enable_turn_trace:
                        _retry_content_head = safe_content_head(retry_response) if "retry_response" in locals() else ""
                        _retry_parser_snippet = (
                            parser_input_snippet(retry_response) if "retry_response" in locals() else ""
                        )
                        _retry_parser_error_fields = parser_error_trace_fields(_retry_exc)
                        _retry_progress_signal = self._progress_adapter.signal_from_context(
                            bash_command=bash_command,
                            observation=observation,
                            agent_phase=self.agent_phase,
                            assistant_content_head=_retry_content_head,
                            parser_input_snippet=_retry_parser_snippet,
                        )
                        self.turn_traces.append(build_turn_trace(
                            step_index=self.step_index,
                            agent_phase=self.agent_phase,
                            stage=stage,
                            workflow_segment=_retry_progress_signal.segment,
                            bash_command=bash_command,
                            touched_file_paths=_retry_progress_signal.touched_file_paths,
                            input_tokens=input_tokens,
                            expected_costs=expected_costs,
                            base_pressure=base_pressure,
                            effective_pressure=self.routing.budget_pressure,
                            backend_chosen=backend_chosen,
                            escalated_backend=escalated_backend,
                            final_backend=backend.name,
                            backend_tier=backend.tier,
                            routing_trigger_source=routing_trigger_source,
                            reserve_out=reserve_out,
                            adaptive=self.routing.adaptive,
                            no_progress_streak=self._no_progress_streak,
                            no_progress_on_tier=self._no_progress_on_current_tier,
                            turns_on_tier=self._turns_on_current_tier,
                            has_progress=has_progress,
                            progress_reason=progress_reason,
                            action_has_progress=None,
                            action_progress_reason=None,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            prompt_tokens_source=usage["prompt_tokens_source"],
                            completion_tokens_source=usage["completion_tokens_source"],
                            cost_mode=usage["cost_mode"],
                            cost_fallback_reason=usage["cost_fallback_reason"],
                            actual_cost=actual_cost,
                            billable=billable,
                            response_ok=True,
                            error_type=type(_retry_exc).__name__,
                            **provider_trace_fields(backend.name),
                            **cost_basis_trace_fields(backend.name, prompt_tokens, turn_index=self.step_index),
                            **protocol_trace_fields(backend.name),
                            **router_trace_fields(self.routing),
                            **value_aware_trace_fields(self.routing),
                            **self._gold_edit_guard_trace_fields(),
                            protocol_retry_used=True,
                            protocol_retry_success=False,
                            protocol_retry_reason=turn_protocol_retry_reason,
                            protocol_retry_attempts=1,
                            protocol_retry_limit=turn_protocol_retry_limit,
                            assistant_content_head=_retry_content_head,
                            tool_call_summary=tool_call_summary(retry_response) if "retry_response" in locals() else None,
                            parser_input_snippet=_retry_parser_snippet,
                            **_retry_parser_error_fields,
                            reservation_id=getattr(locals().get("retry_reservation"), "reservation_id", None),
                            reserved_cost=round(actual_cost, 6),
                            reservation_settled="retry_response" in locals(),
                        ))
                finally:
                    turn_protocol_retry_attempts = 1
                    self._protocol_retry_attempts += 1
        except Exception as exc:
            _parse_error = exc

        if _parse_error is not None:
            if self._enable_turn_trace and not turn_protocol_retry_used:
                # Write turn trace for non-retry parse errors (original path)
                _content_head = safe_content_head(response)
                _parser_snippet = parser_input_snippet(response)
                _parser_error_fields = parser_error_trace_fields(_parse_error)
                _parser_progress_signal = self._progress_adapter.signal_from_context(
                    bash_command=bash_command,
                    observation=observation,
                    agent_phase=self.agent_phase,
                    assistant_content_head=_content_head,
                    parser_input_snippet=_parser_snippet,
                )
                self.turn_traces.append(build_turn_trace(
                    step_index=self.step_index,
                    agent_phase=self.agent_phase,
                    stage=stage,
                    workflow_segment=_parser_progress_signal.segment,
                    bash_command=bash_command,
                    touched_file_paths=_parser_progress_signal.touched_file_paths,
                    input_tokens=input_tokens,
                    expected_costs=expected_costs,
                    base_pressure=base_pressure,
                    effective_pressure=self.routing.budget_pressure,
                    backend_chosen=backend_chosen,
                    escalated_backend=escalated_backend,
                    final_backend=backend.name,
                    backend_tier=backend.tier,
                    routing_trigger_source=routing_trigger_source,
                    reserve_out=reserve_out,
                    adaptive=self.routing.adaptive,
                    no_progress_streak=self._no_progress_streak,
                    no_progress_on_tier=self._no_progress_on_current_tier,
                    turns_on_tier=self._turns_on_current_tier,
                    has_progress=has_progress,
                    progress_reason=progress_reason,
                    action_has_progress=None,
                    action_progress_reason=None,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    prompt_tokens_source=usage["prompt_tokens_source"],
                    completion_tokens_source=usage["completion_tokens_source"],
                    cost_mode=usage["cost_mode"],
                    cost_fallback_reason=usage["cost_fallback_reason"],
                    actual_cost=actual_cost,
                    billable=billable,
                    response_ok=True,
                    error_type=type(_parse_error).__name__,
                    **provider_trace_fields(backend.name),
                    **cost_basis_trace_fields(backend.name, prompt_tokens, turn_index=self.step_index),
                    **protocol_trace_fields(backend.name),
                    **router_trace_fields(self.routing),
                    **value_aware_trace_fields(self.routing),
                    **self._gold_edit_guard_trace_fields(),
                    protocol_retry_used=turn_protocol_retry_used,
                    protocol_retry_success=turn_protocol_retry_success,
                    protocol_retry_reason=turn_protocol_retry_reason,
                    protocol_retry_attempts=turn_protocol_retry_attempts,
                    protocol_retry_limit=turn_protocol_retry_limit,
                    assistant_content_head=_content_head,
                    tool_call_summary=tool_call_summary(response),
                    parser_input_snippet=_parser_snippet,
                    **_parser_error_fields,
                    reservation_id=reservation_id,
                    reserved_cost=round(actual_cost, 6),
                    reservation_settled=True,
                ))
            raise _parse_error
        action_progress = self._progress_adapter.signal_from_actions(actions)
        action_has_progress = action_progress.has_progress
        action_progress_reason = action_progress.progress_reason
        action_fields = action_trace_fields(actions)
        message["extra"] = {
            "actions": actions,
            "response": response.model_dump(),
            "cost": billable,
            "backend": backend.name,
            "stage": stage.value,
        }
        if self._enable_turn_trace:
            content_head = safe_content_head(response)
            parser_snippet = parser_input_snippet(response)
            parser_progress_signal = self._progress_adapter.signal_from_context(
                bash_command=bash_command,
                observation=observation,
                agent_phase=self.agent_phase,
                assistant_content_head=content_head,
                parser_input_snippet=parser_snippet,
            )
            self.turn_traces.append(build_turn_trace(
                step_index=self.step_index,
                agent_phase=self.agent_phase,
                stage=stage,
                workflow_segment=parser_progress_signal.segment,
                bash_command=bash_command,
                touched_file_paths=parser_progress_signal.touched_file_paths,
                input_tokens=input_tokens,
                expected_costs=expected_costs,
                base_pressure=base_pressure,
                effective_pressure=self.routing.budget_pressure,
                backend_chosen=backend_chosen,
                escalated_backend=escalated_backend,
                final_backend=backend.name,
                backend_tier=backend.tier,
                routing_trigger_source=routing_trigger_source,
                reserve_out=reserve_out,
                adaptive=self.routing.adaptive,
                no_progress_streak=self._no_progress_streak,
                no_progress_on_tier=self._no_progress_on_current_tier,
                turns_on_tier=self._turns_on_current_tier,
                has_progress=has_progress,
                progress_reason=progress_reason,
                action_has_progress=action_has_progress,
                action_progress_reason=action_progress_reason,
                **action_fields,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                prompt_tokens_source=usage["prompt_tokens_source"],
                completion_tokens_source=usage["completion_tokens_source"],
                cost_mode=usage["cost_mode"],
                cost_fallback_reason=usage["cost_fallback_reason"],
                actual_cost=actual_cost,
                billable=billable,
                response_ok=True,
                error_type=None,
                **provider_trace_fields(backend.name),
                **cost_basis_trace_fields(backend.name, prompt_tokens, turn_index=self.step_index),
                **protocol_trace_fields(backend.name),
                **router_trace_fields(self.routing),
                **value_aware_trace_fields(self.routing),
                **self._gold_edit_guard_trace_fields(),
                protocol_retry_used=turn_protocol_retry_used,
                protocol_retry_success=turn_protocol_retry_success,
                protocol_retry_reason=turn_protocol_retry_reason,
                protocol_retry_attempts=turn_protocol_retry_attempts,
                protocol_retry_limit=turn_protocol_retry_limit,
                assistant_content_head=content_head,
                tool_call_summary=tool_call_summary(response),
                parser_input_snippet=parser_snippet,
                reservation_id=reservation_id,
                reserved_cost=round(actual_cost, 6),
                reservation_settled=True,
            ))
        return message

    def _defer_gold_edit_stop_loss(self, stop_loss: bool) -> bool:
        if not stop_loss:
            return False
        if not self.agent_gold_edited:
            return True
        if self._gold_edit_stop_loss_grace_turns < GOLD_EDIT_SUBMIT_GRACE_TURNS:
            self._gold_edit_stop_loss_grace_turns += 1
            return False
        return True

    def _refresh_progress(self) -> None:
        if self._progress_refresh is not None:
            self._progress_refresh()

    def _release_last_reservation(self) -> None:
        reservation_id = self._last_reservation_id
        if reservation_id is None:
            return
        try:
            self.governor.release(reservation_id, WorkflowStatus.FAILED)
        finally:
            self._last_reservation_id = None
            self._last_reserve_out = 0
            self.last_budget_snapshot = self.governor.budget_snapshot()

    def _gold_edit_guard_trace_fields(self) -> dict[str, object]:
        active = self._value_triggered_escalation_turns_remaining > 0
        opened = self._value_triggered_escalation_opened
        remaining = self._value_triggered_escalation_turns_remaining
        reason = self._value_triggered_escalation_reason
        return {
            "gold_edit_guard_turns": self._gold_edit_mid_tier_repair_turns,
            "gold_edit_guard_limit": GOLD_EDIT_MID_TIER_REPAIR_TURN_LIMIT,
            "gold_edit_guard_active": self._gold_edit_mid_tier_repair_turns >= GOLD_EDIT_MID_TIER_REPAIR_TURN_LIMIT,
            "value_triggered_escalation_active": active,
            "value_triggered_escalation_turns_remaining": remaining,
            "value_triggered_escalation_opened": opened,
            "value_triggered_escalation_reason": reason,
            "value_triggered_escalation_action": self._value_triggered_escalation_action,
            "value_triggered_escalation_window": self._value_triggered_escalation_window,
        }

    def _task_value_multiplier(self) -> float:
        median = max(0.001, float(getattr(self.routing, "median_task_value", 1.0) or 1.0))
        value = float(getattr(self.routing, "task_value", median) or median)
        return max(0.5, min(2.0, value / median))

    def _refresh_value_triggered_escalation_policy(self) -> None:
        prior = getattr(getattr(self.routing, "adaptive", None), "_prior_summary", None) or {}
        action = str(prior.get("value_triggered_escalation_action") or "default")
        raw_window = prior.get("value_triggered_escalation_window")
        if raw_window is None:
            raw_window = VALUE_TRIGGERED_ESCALATION_DEFAULT_WINDOW_TURNS
        window = int(raw_window)
        self._value_triggered_escalation_action = action
        self._value_triggered_escalation_window = max(0, window)

    def _can_value_triggered_escalation(self) -> bool:
        self._refresh_value_triggered_escalation_policy()
        if self.routing.strategy not in VALUE_TRIGGERED_ESCALATION_ROUTINGS:
            return False
        if self._value_triggered_escalation_opened:
            return False
        if self._value_triggered_escalation_action == "disable_value_triggered_escalation":
            return False
        if self._value_triggered_escalation_window <= 0:
            return False
        if self.agent_gold_edited:
            return False
        if self._task_value_multiplier() < VALUE_TRIGGERED_ESCALATION_MIN_MULTIPLIER:
            return False
        total = float(self.governor.state.total_budget or 0.0)
        if total <= 0:
            return False
        remaining_frac = self.governor.remaining_budget() / total
        return remaining_frac >= VALUE_TRIGGERED_ESCALATION_MIN_HEADROOM_FRAC

    def _maybe_open_value_triggered_escalation(self, stall_reason: str) -> bool:
        if not self._can_value_triggered_escalation():
            return False
        self._value_triggered_escalation_opened = True
        self._value_triggered_escalation_turns_remaining = self._value_triggered_escalation_window
        self._value_triggered_escalation_reason = f"opened_{stall_reason}"
        print(
            f"{tag('value-escalation', bold=False)} #{self.step_index} "
            f"value_multiplier={self._task_value_multiplier():.2f} "
            f"window={self._value_triggered_escalation_window} "
            f"action={self._value_triggered_escalation_action} reason={stall_reason}",
            flush=True,
        )
        return True

    def _apply_value_triggered_escalation(self, backend: Backend, stage) -> Backend:  # noqa: ARG002
        if self._value_triggered_escalation_turns_remaining <= 0:
            return backend
        candidate = ModelCatalog.strongest(self.routing.backends)
        if candidate is None or backend.tier >= candidate.tier:
            return backend
        print(
            f"{tag('value-escalation', bold=False)} #{self.step_index} "
            f"{backend_tier_label(backend.name)} -> {backend_tier_label(candidate.name)} "
            f"remaining={self._value_triggered_escalation_turns_remaining}",
            flush=True,
        )
        self._no_progress_on_current_tier = 0
        self._turns_on_current_tier = 0
        return candidate

    def _reserve_output_tokens(self, backend: Backend, input_tokens: int) -> int:
        remaining = self.governor.remaining_budget()
        if remaining <= 0:
            return 64
        input_cost = estimate_token_cost(
            backend.name,
            input_tokens=input_tokens,
            output_tokens=0,
            turn_index=self.step_index,
        )
        output_budget = remaining - input_cost
        if output_budget <= 0:
            return 64
        output_token_cost = max(
            estimate_token_cost(
                backend.name,
                input_tokens=input_tokens,
                output_tokens=1,
                turn_index=self.step_index,
            ) - input_cost,
            backend.cost_per_output_token,
            1e-12,
        )
        affordable_tokens = output_budget / output_token_cost
        headroom = min(1024, max(backend.mean_output_tokens * 2, 256))
        return max(64, min(headroom, int(affordable_tokens * 0.95)))

    def _apply_progress_escalation(
        self,
        backend: Backend,
        *,
        protect_strongest_this_turn: bool = False,
    ) -> Backend:
        """Per-tier escalation + turn cap + strongest-tier stop-loss.

        Escalation (no-progress streak): "stuck → try better model."
        - move to the next-higher configured tier
        - strongest tier downgrades as stop-loss when it cannot make progress
        - Resets when progress is made.
        """
        if self.routing.strategy not in IN_TASK_SWITCHING_ROUTINGS:
            return backend
        ordered = self.routing.backends
        strongest = ModelCatalog.strongest(ordered)
        if len(ordered) < 2:
            return backend
        if protect_strongest_this_turn and backend.tier >= strongest.tier:
            self._no_progress_on_current_tier = 0
            self._turns_on_current_tier = 0
            return backend

        reason = None
        next_backend = None

        # Check escalation (no-progress streak)
        patience = tier_escalation_patience().get(backend.tier)
        if patience is not None and self._no_progress_on_current_tier >= patience:
            if backend.tier >= strongest.tier:
                next_backend = _backend_by_configured_tier(ordered, STRONGEST_DOWNGRADE_TIER) or ModelCatalog.next_lower(ordered, backend)
                reason = f"strongest-stop-loss streak={self._no_progress_on_current_tier}/{patience}"
            else:
                next_backend = ModelCatalog.next_higher(ordered, backend)
                if next_backend is not None:
                    reason = f"streak={self._no_progress_on_current_tier}/{patience}"

        # Check turn cap
        if reason is None:
            max_turns = tier_max_turns().get(backend.tier)
            if max_turns is not None and self._turns_on_current_tier >= max_turns:
                if backend.tier >= strongest.tier:
                    next_backend = _backend_by_configured_tier(ordered, STRONGEST_DOWNGRADE_TIER) or ModelCatalog.next_lower(ordered, backend)
                    reason = f"strongest-turn-cap turns={self._turns_on_current_tier}/{max_turns}"
                else:
                    next_backend = ModelCatalog.next_higher(ordered, backend)
                    if next_backend is not None:
                        reason = f"turns={self._turns_on_current_tier}/{max_turns}"

        if reason is None or next_backend is None or next_backend.tier == backend.tier:
            return backend

        direction = "downgrade" if next_backend.tier < backend.tier else "upgrade"
        print(
            f"{tag('escalate', bold=False)} #{self.step_index} "
            f"{reason} ({direction}) "
            f"{backend_tier_label(backend.name)} -> {backend_tier_label(next_backend.name)}",
            flush=True,
        )
        self._no_progress_on_current_tier = 0
        self._turns_on_current_tier = 0
        return next_backend

    def _apply_gold_edit_repair_guard(self, backend: Backend, segment: WorkflowSegment) -> Backend:
        """Avoid long second-cheapest-tier repair loops after a gold edit."""
        if self.routing.strategy not in GOLD_EDIT_REPAIR_GUARD_ROUTINGS:
            return backend
        if not self.agent_gold_edited or segment.name not in (WorkflowSegment.ACTION, WorkflowSegment.VERIFICATION):
            return backend
        guarded_tier = ModelCatalog.second_cheapest(self.routing.backends).tier
        if backend.tier != guarded_tier:
            return backend
        if self._gold_edit_mid_tier_repair_turns < GOLD_EDIT_MID_TIER_REPAIR_TURN_LIMIT:
            return backend

        next_backend = next((b for b in self.routing.backends if b.tier > backend.tier), None)
        if next_backend is None:
            print(
                f"{tag('stop', bold=False)} #{self.step_index} "
                f"gold_edit_mid_tier_repair_limit turns={self._gold_edit_mid_tier_repair_turns}/"
                f"{GOLD_EDIT_MID_TIER_REPAIR_TURN_LIMIT} no_higher_tier",
                flush=True,
            )
            raise BudgetFlowStagnationError(
                self.workflow_id,
                exit_reason="gold_edit_mid_tier_repair_limit",
                step_index=self.step_index,
                no_progress_streak=self._gold_edit_mid_tier_repair_turns,
            )

        print(
            f"{tag('guard', bold=False)} #{self.step_index} "
            f"gold_edit_mid_tier_repair_limit turns={self._gold_edit_mid_tier_repair_turns}/"
            f"{GOLD_EDIT_MID_TIER_REPAIR_TURN_LIMIT} "
            f"{backend_tier_label(backend.name)} -> {backend_tier_label(next_backend.name)}",
            flush=True,
        )
        self._no_progress_on_current_tier = 0
        self._turns_on_current_tier = 0
        return next_backend

    def _reserve_backend(self, backend: Backend, input_tokens: int) -> Backend:
        reserve_out = self._reserve_output_tokens(backend, input_tokens)
        estimate = self.governor.estimate_cost(
            backend,
            input_tokens=input_tokens,
            expected_output_tokens=backend.mean_output_tokens,
            reserve_output_tokens=reserve_out,
            turn_index=self.step_index,
        )
        reservation = self.governor.reserve(self.workflow_id, backend, estimate)
        if reservation is not None:
            self._last_reservation_id = reservation.reservation_id
            self._last_reserve_out = reserve_out
            return backend
        snapshot = self.governor.budget_snapshot()
        exit_reason = self.governor.last_reserve_failure or "budget_exhausted"
        self.last_exit_reason = exit_reason
        self.last_budget_snapshot = snapshot
        raise BudgetFlowBudgetError(
            self.workflow_id,
            exit_reason=exit_reason,
            budget_snapshot=snapshot,
            step_index=self.step_index,
            backend=backend.name,
        )

    def _model_config_for(self, backend: Backend) -> tuple[str, dict[str, Any]]:
        return MODEL_CATALOG.litellm_kwargs(backend.name, api_keys=self._api_keys)

    def _completion(
        self,
        messages: list[dict],
        *,
        backend_name: str,
        model_name: str,
        model_kwargs: dict[str, Any],
        **kwargs,
    ):
        prepared = [{k: v for k, v in msg.items() if k != "extra"} for msg in messages]
        prepared = _reorder_anthropic_thinking_blocks(prepared)
        prepared = set_cache_control(prepared, mode=self.set_cache_control)

        def _query():
            kwargs_merged = {**model_kwargs, **kwargs}
            try:
                return litellm.completion(
                    model=model_name,
                    messages=prepared,
                    timeout=_llm_timeout_s(),
                    tools=[BASH_TOOL],
                    **kwargs_merged,
                )
            except Exception as exc:  # noqa: BLE001
                if is_fatal_billing_error(str(exc)):
                    raise FatalProviderBillingError(exc) from exc
                exc_name = type(exc).__name__
                if exc_name in ("APITimeoutError", "Timeout", "ReadTimeout", "ConnectTimeout"):
                    raise _ProviderTimeoutError(exc) from exc
                if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                    raise _ProviderTimeoutError(exc) from exc
                raise

        try:
            for attempt in retry(logger=logger, abort_exceptions=[KeyboardInterrupt, FatalProviderBillingError, _ProviderTimeoutError]):
                with attempt:
                    return _query()
        except FatalProviderBillingError as exc:
            err_msg = str(exc)
            action = record_billing_halt(err_msg, backend=backend_name)
            raise BudgetFlowUpstreamError(
                self.workflow_id,
                exit_reason=action.reason or "billing_guard",
                step_index=self.step_index,
                backend=backend_name,
                sample=err_msg,
            ) from exc.original
        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)
            # Billing errors: halt everything immediately, don't retry.
            if is_fatal_billing_error(err_msg):
                action = record_billing_halt(err_msg, backend=backend_name)
                raise BudgetFlowUpstreamError(
                    self.workflow_id,
                    exit_reason=action.reason or "billing_guard",
                    step_index=self.step_index,
                    backend=backend_name,
                    sample=err_msg,
                ) from exc
            # BadRequestError (400): tag as infra error, let runner fall through to harness eval.
            if "BadRequestError" in type(exc).__name__ or getattr(exc, "status_code", None) == 400:
                raise BudgetFlowUpstreamError(
                    self.workflow_id,
                    exit_reason="infra_error",
                    step_index=self.step_index,
                    backend=backend_name,
                    sample=err_msg,
                ) from exc
            action = record_upstream_error(err_msg, backend=backend_name)
            if action.halt_all:
                raise BudgetFlowUpstreamError(
                    self.workflow_id,
                    exit_reason=action.reason or "upstream_guard",
                    step_index=self.step_index,
                    backend=backend_name,
                    sample=err_msg,
                ) from exc
            raise

    def _parse_actions(self, response, *, backend_tier: int | None = None) -> list[dict]:
        tool_calls = response.choices[0].message.tool_calls or []
        counted_format_error = False
        if not tool_calls:
            class _NoToolCallsFormatError(Exception):
                pass

            reason, stop_after = _format_error_limit_for(_NoToolCallsFormatError(), response, backend_tier)
            self._protocol_retry_reason = reason
            self._protocol_retry_limit = stop_after
            self._format_error_streak += 1
            counted_format_error = True
            if self._format_error_streak >= stop_after:
                raise BudgetFlowStagnationError(
                    self.workflow_id,
                    exit_reason="format_error_no_tool_calls",
                    step_index=self.step_index,
                    no_progress_streak=self._format_error_streak,
                )
        try:
            actions = parse_tool_actions(tool_calls, format_error_template=self.format_error_template)
            self._format_error_streak = 0
            return actions
        except FormatError as exc:
            if not counted_format_error:
                reason, stop_after = _format_error_limit_for(exc, response, backend_tier)
                self._protocol_retry_reason = reason
                self._protocol_retry_limit = stop_after
                self._format_error_streak += 1
            if self._format_error_streak >= stop_after:
                raise BudgetFlowStagnationError(
                    self.workflow_id,
                    exit_reason="format_error_invalid_tool_call",
                    step_index=self.step_index,
                    no_progress_streak=self._format_error_streak,
                )
            raise

    def format_message(self, **kwargs) -> dict:
        return expand_multimodal_content(kwargs, pattern=self.multimodal_regex)

    def format_observation_messages(
        self, message: dict, outputs: list[dict], template_vars: dict | None = None
    ) -> list[dict]:
        actions = message.get("extra", {}).get("actions", [])
        return format_toolcall_observation_messages(
            actions=actions,
            outputs=outputs,
            observation_template=self.observation_template,
            template_vars=template_vars,
            multimodal_regex=self.multimodal_regex,
        )

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return kwargs

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "model_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                    "strategy": self.routing.strategy,
                },
                "backend_picks": list(self.backend_picks),
            }
        }

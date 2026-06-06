from __future__ import annotations

import logging
import os
from collections import deque
from collections.abc import Callable
from typing import Any

import litellm
from minisweagent.models.utils.actions_toolcall import (
    BASH_TOOL,
    format_toolcall_observation_messages,
    parse_toolcall_actions,
)
from minisweagent.exceptions import FormatError
from minisweagent.models.utils.actions_text import (
    format_observation_messages as format_text_observation_messages,
    parse_regex_actions,
)
from minisweagent.models.utils.anthropic_utils import _reorder_anthropic_thinking_blocks
from minisweagent.models.utils.cache_control import set_cache_control
from minisweagent.models.utils.openai_multimodal import expand_multimodal_content
from minisweagent.models.utils.retry import retry

from ..litellm_quiet import configure_litellm_quiet
from ..budget_pressure import live_budget_pressure
from ..deepseek_backend import ensure_aicode007_proxy, ensure_direct_api, load_env_file
from ..defaults import (
    GOLD_EDIT_T2_REPAIR_TURN_LIMIT,
    PRESSURE_MAX,
    STRONGEST_DOWNGRADE_TIER,
    TIER_CONFIGS,
    TIER1_BACKEND,
    TIER3_MODEL,
    TIER_ESCALATION_PATIENCE,
    TIER_MAX_TURNS,
)
from ..console_log import backend_tier_label, bold, dim, routing_stage_label, tag
from ..governor import BudgetGovernor
from ..types import Backend, Stage, TurnInfo, WorkflowStatus
from .errors import BudgetFlowBudgetError, BudgetFlowStagnationError, BudgetFlowUpstreamError
from ..run_guards import is_fatal_billing_error, record_billing_halt, record_upstream_error
from .bash_stage import (
    classify_routing_stage,
    command_counts_as_progress,
    extract_touched_file_paths, extract_trace_file_paths,
)
from .stall_guard import check_stagnation, normalize_bash_command
from .message_utils import estimate_input_tokens, extract_bash_context
from .protocol_adapter import ActionProtocolAdapter
from .strategies import RoutingContext, choose_backend, stage_weight

logger = logging.getLogger("budgetflow_litellm_model")

configure_litellm_quiet()

_DASHSCOPE_BACKENDS = frozenset(
    backend for backend, config in TIER_CONFIGS.items() if config.provider == "dashscope"
)
_AICODE007_BACKENDS = frozenset(
    backend for backend, config in TIER_CONFIGS.items() if config.provider == "aicode007"
)
FORMAT_ERROR_STOP_AFTER = 5
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


def _format_error_stop_after(backend_tier: int | None) -> int:
    return FORMAT_ERROR_STOP_AFTER


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


class FatalProviderBillingError(RuntimeError):
    """Provider billing/account errors should bypass mini-SWE retry backoff."""

    def __init__(self, original: Exception) -> None:
        self.original = original
        super().__init__(str(original))


class _ProviderTimeoutError(RuntimeError):
    """Timeout errors should skip tenacity retry to enable provider fallback."""

    def __init__(self, original: Exception) -> None:
        self.original = original
        super().__init__(str(original))


def _build_turn_trace(
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
    # --- P0 trace extension fields ---
    provider: str | None = None,
    model: str | None = None,
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
    touched_file_paths: list[str] | None = None,
    # --- value-aware routing fields ---
    task_value: float | None = None,
    task_value_multiplier: float | None = None,
    value_aware_active: bool = False,
) -> dict:
    """Build a single turn-trace dict for observability (no side effects)."""
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
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "actual_cost": round(actual_cost, 6),
        "billable_cost": round(billable, 6),
        "response_ok": response_ok,
        "error_type": error_type,
        # P0: provider/model identity
        "provider": provider,
        "model": model,
        # P0: protocol/parser evidence
        "text_mode": text_mode,
        "protocol": protocol,
        "parser": parser,
        "assistant_content_head": assistant_content_head,
        "tool_call_summary": tool_call_summary,
        "parser_input_snippet": parser_input_snippet,
        "parser_error_type": parser_error_type,
        "parser_error_message": parser_error_message,
        # P0: provider error evidence
        "provider_status_code": provider_status_code,
        "provider_error_body": provider_error_body,
        "provider_request_id": provider_request_id,
        # P0: reservation lifecycle
        "reservation_id": reservation_id,
        "reserved_cost": reserved_cost,
        "reservation_released": reservation_released,
        "reservation_settled": reservation_settled,
        # P0: router reasoning
        "router_reason": router_reason,
        "router_scores": router_scores,
        "router_pressure": router_pressure,
        "router_branch": router_branch,
        "gold_edit_guard_turns": gold_edit_guard_turns,
        "gold_edit_guard_limit": gold_edit_guard_limit,
        "gold_edit_guard_active": gold_edit_guard_active,
        # Value-aware routing fields
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
    return trace


def _router_trace_fields(routing) -> dict[str, Any]:
    """Extract router reasoning fields from RoutingContext.last_decision."""
    d = routing.last_decision
    if d is None:
        return {}
    return {
        "router_reason": d.reason,
        "router_scores": d.scores,
        "router_pressure": d.pressure,
        "router_branch": d.branch,
    }


def _value_aware_trace_fields(routing) -> dict[str, Any]:
    """Extract value-aware routing fields when active."""
    if routing.strategy != "budgetflow_value_aware":
        return {}
    multiplier = getattr(routing.selector, "last_multiplier", 1.0)
    return {
        "task_value": routing.task_value,
        "task_value_multiplier": multiplier,
        "value_aware_active": True,
    }


def _provider_trace_fields(backend_name: str) -> dict[str, Any]:
    """Extract provider/model identity from TierConfig."""
    from ..defaults import ModelCatalog
    cfg = ModelCatalog.config_for(backend_name)
    if cfg is None:
        return {}
    return {
        "provider": cfg.provider,
        "model": cfg.model,
    }


def _protocol_trace_fields(backend_name: str, text_mode: bool) -> dict[str, Any]:
    """Extract protocol/parser evidence for trace."""
    decision = ActionProtocolAdapter.resolve(backend_name)
    return {
        "text_mode": text_mode,
        "protocol": decision.protocol,
        "parser": decision.parser,
    }


def _safe_content_head(response, max_chars: int = 300) -> str | None:
    """First *max_chars* of assistant text content, redacted of API keys."""
    try:
        content = response.choices[0].message.content or ""
        return content[:max_chars]
    except Exception:
        return None


def _tool_call_summary(response) -> dict | None:
    """Count + function names of tool calls in response."""
    try:
        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            return None
        names = [tc.function.name for tc in tool_calls if hasattr(tc, "function")]
        return {"count": len(tool_calls), "names": names}
    except Exception:
        return None


def _parser_input_snippet(response, text_mode: bool) -> str | None:
    """What the parser received: text_regex→content head, tool_call→summary JSON."""
    import json
    if text_mode:
        return _safe_content_head(response, max_chars=500)
    tc = _tool_call_summary(response)
    if tc is None:
        return None
    try:
        return json.dumps(tc)
    except Exception:
        return str(tc)


def _try_extract_json_command(content: str) -> str | None:
    """Extract a bash command from {"command": "..."} JSON embedded in prose.

    GPT-5.4 sometimes emits JSON-format commands instead of fenced blocks.
    Returns the unescaped command string, or None if no JSON command found.
    """
    import json
    import re
    # Find {"command": ...} patterns.  Match the string value with \-escapes.
    for m in re.finditer(r'\{"command"\s*:\s*"((?:[^"\\]|\\.)*)"\}', content):
        try:
            return json.loads(m.group(0))["command"]
        except (json.JSONDecodeError, KeyError):
            continue
    # Also try [bash] {"command": "..."} variant
    for m in re.finditer(r'\[bash\]\s*\{[^}]*"command"\s*:\s*"((?:[^"\\]|\\.)*)"[^}]*\}', content):
        try:
            inner = re.search(r'\{[^}]*"command"\s*:\s*"((?:[^"\\]|\\.)*)"[^}]*\}', m.group(0))
            if inner:
                return json.loads(inner.group(0))["command"]
        except (json.JSONDecodeError, KeyError):
            continue
    return None


# Canonical regex for text-mode bash command extraction.
# Matches: ```mswea_bash_command, ```bash, ```sh
_TEXT_ACTION_REGEX = r"```(?:mswea_bash_command|bash|sh)\s*\n(.*?)\n```"


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
        self._api_keys = {config.api_key_env: os.environ.get(config.api_key_env) for config in TIER_CONFIGS.values()}
        missing_keys = sorted(
            {
                TIER_CONFIGS[b.name].api_key_env
                for b in routing.backends
                if b.name in TIER_CONFIGS and not self._api_keys.get(TIER_CONFIGS[b.name].api_key_env)
            }
        )
        if missing_keys:
            raise RuntimeError(f"{', '.join(missing_keys)} is missing. Add it to the repo root .env file.")
        self.step_index = 0
        self._no_progress_streak = 0
        self._no_progress_on_current_tier = 0  # consecutive non-progress steps on current tier
        self._turns_on_current_tier = 0  # total turns on current tier (for turn cap)
        self._gold_edit_t2_repair_turns = 0
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
        self.last_exit_reason: str | None = None
        self.last_budget_snapshot: dict[str, float] | None = None
        self._enable_turn_trace: bool = enable_turn_trace
        self.turn_traces: list[dict] = []
        self._last_reservation_id: str | None = None
        self._last_reserve_out: int = 0
        self._format_error_streak: int = 0
        self._last_text_mode: bool = False
        self._unavailable_backends: set[str] = set()
        self.config = type("Config", (), {"model_name": TIER3_MODEL})()

    def query(self, messages: list[dict[str, str]], **kwargs) -> dict:
        self.step_index += 1
        bash_command, observation = extract_bash_context(messages)
        stage = classify_routing_stage(bash_command, observation, agent_phase=self.agent_phase)
        input_tokens = estimate_input_tokens(messages)
        turn = TurnInfo(
            workflow_id=self.workflow_id,
            step_index=self.step_index,
            stage=stage,
            w_i=1.0 if self.routing.strategy in ("stage_blind", "budgetflow_equal_weight", "budgetflow_auto_v2") else stage_weight(stage),
            context_len=input_tokens,
            tool_name="bash",
        )
        expected_costs = {
            backend.name: self.governor.estimate_cost(
                backend,
                input_tokens=input_tokens,
                max_output_tokens=self.default_max_output_tokens,
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
        phase = (self.agent_phase or "").strip()
        has_progress, progress_reason = command_counts_as_progress(
            bash_command,
            agent_phase=self.agent_phase,
        )
        if has_progress:
            self._no_progress_streak = 0
            self._no_progress_on_current_tier = 0
        else:
            self._no_progress_streak += 1
            self._no_progress_on_current_tier += 1
        norm_cmd = normalize_bash_command(bash_command)
        if norm_cmd:
            self._recent_commands.append(norm_cmd)
        should_stop, stall_reason, repeat_cmd = check_stagnation(
            strategy=self.routing.strategy,
            no_progress_streak=self._no_progress_streak,
            recent_commands=self._recent_commands,
        )
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
        # Adaptive starting tier: skip T1/T2 on first step if strategy is on a losing streak
        if self.step_index == 1 and self.routing.adaptive is not None:
            min_start = self.routing.adaptive.starting_tier()
            if backend.tier < min_start:
                ordered = self.routing.backends
                backend = ordered[min_start - 1]
                print(
                    f"{tag('adapt', bold=False)} #{self.step_index} "
                    f"starting_tier={min_start} ({backend_tier_label(backend.name)})",
                    flush=True,
                )
        if self.routing.adaptive is not None and self.routing.strategy in (
            "budgetflow_full",
            "budgetflow_conservative",
            "budgetflow_value_aware",
            "budgetflow_equal_weight",
            "budgetflow_auto_v2",
            "stage_blind",
        ):
            forced_tier = self.routing.adaptive.rescue.forced_min_tier(
                stage=stage,
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
            if self.routing.adaptive.rescue.should_stop_loss(gold_edited=self.agent_gold_edited):
                print(
                    f"{tag('stop', bold=False)} #{self.step_index} "
                    f"rescue_timeout_gold_edited evidence_turns="
                    f"{self.routing.adaptive.rescue.evidence_turns}",
                    flush=True,
                )
                raise BudgetFlowStagnationError(
                    self.workflow_id,
                    exit_reason="rescue_timeout_gold_edited",
                    step_index=self.step_index,
                    no_progress_streak=self._no_progress_streak,
                )
        prev_tier = self._last_backend_tier
        backend = self._apply_progress_escalation(backend)
        backend = self._apply_gold_edit_repair_guard(backend, stage)
        escalated_backend = backend.name
        response = None
        text_mode = False
        attempted_unavailable: list[str] = []
        for candidate in self._provider_candidates(backend):
            backend = self._reserve_with_downgrade(candidate, input_tokens)
            reserve_out = self._last_reserve_out
            if backend.tier != prev_tier and prev_tier > 0:
                self._no_progress_on_current_tier = 0
                self._turns_on_current_tier = 0
            self._last_backend_tier = backend.tier
            self._turns_on_current_tier += 1
            if self.agent_gold_edited and stage in (Stage.REPAIR, Stage.VALIDATION) and backend.tier == 2:
                self._gold_edit_t2_repair_turns += 1
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
                text_mode = self._use_text_mode(backend.name)
                self._last_text_mode = text_mode
                response = self._completion(
                    messages,
                    backend_name=backend.name,
                    model_name=model_name,
                    model_kwargs=model_kwargs,
                    text_mode=text_mode,
                    **kwargs,
                )
                break
            except Exception as exc:
                error_type = type(exc).__name__
                self._release_last_reservation()
                if self._enable_turn_trace:
                    self.turn_traces.append(_build_turn_trace(
                        step_index=self.step_index,
                        agent_phase=self.agent_phase,
                        stage=stage,
                        bash_command=bash_command,
                        touched_file_paths=extract_trace_file_paths(bash_command=bash_command),
                        input_tokens=input_tokens,
                        expected_costs=expected_costs,
                        base_pressure=base_pressure,
                        effective_pressure=self.routing.budget_pressure,
                        backend_chosen=backend_chosen,
                        escalated_backend=escalated_backend,
                        final_backend=backend.name,
                        backend_tier=backend.tier,
                        reserve_out=reserve_out,
                        adaptive=self.routing.adaptive,
                        no_progress_streak=self._no_progress_streak,
                        no_progress_on_tier=self._no_progress_on_current_tier,
                        turns_on_tier=self._turns_on_current_tier,
                        has_progress=has_progress,
                        progress_reason=progress_reason,
                        prompt_tokens=0,
                        completion_tokens=0,
                        actual_cost=0.0,
                        billable=0.0,
                        response_ok=False,
                        error_type=error_type,
                        **_provider_trace_fields(backend.name),
                        **_protocol_trace_fields(backend.name, text_mode=ActionProtocolAdapter.resolve(backend.name).protocol == "text_regex"),
                        **_router_trace_fields(self.routing),
                        **_value_aware_trace_fields(self.routing),
                        **self._gold_edit_guard_trace_fields(),
                        provider_status_code=getattr(exc, "status_code", None),
                        provider_error_body=str(exc)[:500],
                        reservation_id=self._last_reservation_id,
                        reservation_released=True,
                    ))
                if not _is_provider_unavailable(exc):
                    raise
                self._unavailable_backends.add(backend.name)
                attempted_unavailable.append(backend.name)
                print(
                    f"{tag('provider', bold=False)} #{self.step_index} unavailable "
                    f"{backend_tier_label(backend.name)} -> fallback",
                    flush=True,
                )
                continue
        if response is None:
            self.last_exit_reason = "provider_all_unavailable"
            self.last_budget_snapshot = self.governor.budget_snapshot()
            raise BudgetFlowUpstreamError(
                self.workflow_id,
                exit_reason="provider_all_unavailable",
                step_index=self.step_index,
                backend=",".join(attempted_unavailable) or backend.name,
                sample="all configured backends unavailable",
            )
        message = response.choices[0].message.model_dump()
        prompt_tokens = getattr(response.usage, "prompt_tokens", None) or input_tokens
        completion_tokens = getattr(response.usage, "completion_tokens", None) or backend.mean_output_tokens
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        actual_cost = (
            prompt_tokens * backend.cost_per_input_token
            + completion_tokens * backend.cost_per_output_token
        )
        reservation_id = self._last_reservation_id
        snap = self.governor.budget_snapshot()
        spend_headroom = max(0.0, snap["total_budget"] - snap["spent_budget"])
        billable = min(actual_cost, spend_headroom)
        self.governor.settle(reservation_id, actual_cost, WorkflowStatus.RUNNING)
        self._last_reservation_id = None
        self._last_reserve_out = 0
        try:
            actions = self._parse_actions(response, text_mode=text_mode, backend_tier=backend.tier)
        except Exception as exc:
            if self._enable_turn_trace:
                content_head = _safe_content_head(response)
                parser_snippet = _parser_input_snippet(response, text_mode)
                self.turn_traces.append(_build_turn_trace(
                    step_index=self.step_index,
                    agent_phase=self.agent_phase,
                    stage=stage,
                    bash_command=bash_command,
                    touched_file_paths=extract_trace_file_paths(
                        bash_command=bash_command,
                        assistant_content_head=content_head,
                        parser_input_snippet=parser_snippet,
                    ),
                    input_tokens=input_tokens,
                    expected_costs=expected_costs,
                    base_pressure=base_pressure,
                    effective_pressure=self.routing.budget_pressure,
                    backend_chosen=backend_chosen,
                    escalated_backend=escalated_backend,
                    final_backend=backend.name,
                    backend_tier=backend.tier,
                    reserve_out=reserve_out,
                    adaptive=self.routing.adaptive,
                    no_progress_streak=self._no_progress_streak,
                    no_progress_on_tier=self._no_progress_on_current_tier,
                    turns_on_tier=self._turns_on_current_tier,
                    has_progress=has_progress,
                    progress_reason=progress_reason,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    actual_cost=actual_cost,
                    billable=billable,
                    response_ok=True,
                    error_type=type(exc).__name__,
                    **_provider_trace_fields(backend.name),
                    **_protocol_trace_fields(backend.name, text_mode),
                    **_router_trace_fields(self.routing),
                        **_value_aware_trace_fields(self.routing),
                    **self._gold_edit_guard_trace_fields(),
                    assistant_content_head=content_head,
                    tool_call_summary=_tool_call_summary(response),
                    parser_input_snippet=parser_snippet,
                    parser_error_type=type(exc).__name__,
                    parser_error_message=str(exc)[:500],
                    reservation_id=reservation_id,
                    reserved_cost=round(actual_cost, 6),
                    reservation_settled=True,
                ))
            raise
        message["extra"] = {
            "actions": actions,
            "response": response.model_dump(),
            "cost": billable,
            "backend": backend.name,
            "stage": stage.value,
            "text_mode": text_mode,
        }
        if self._enable_turn_trace:
            content_head = _safe_content_head(response)
            parser_snippet = _parser_input_snippet(response, text_mode)
            self.turn_traces.append(_build_turn_trace(
                step_index=self.step_index,
                agent_phase=self.agent_phase,
                stage=stage,
                bash_command=bash_command,
                touched_file_paths=extract_trace_file_paths(
                    bash_command=bash_command,
                    assistant_content_head=content_head,
                    parser_input_snippet=parser_snippet,
                ),
                input_tokens=input_tokens,
                expected_costs=expected_costs,
                base_pressure=base_pressure,
                effective_pressure=self.routing.budget_pressure,
                backend_chosen=backend_chosen,
                escalated_backend=escalated_backend,
                final_backend=backend.name,
                backend_tier=backend.tier,
                reserve_out=reserve_out,
                adaptive=self.routing.adaptive,
                no_progress_streak=self._no_progress_streak,
                no_progress_on_tier=self._no_progress_on_current_tier,
                turns_on_tier=self._turns_on_current_tier,
                has_progress=has_progress,
                progress_reason=progress_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                actual_cost=actual_cost,
                billable=billable,
                response_ok=True,
                error_type=None,
                **_provider_trace_fields(backend.name),
                **_protocol_trace_fields(backend.name, text_mode),
                **_router_trace_fields(self.routing),
                        **_value_aware_trace_fields(self.routing),
                **self._gold_edit_guard_trace_fields(),
                assistant_content_head=content_head,
                tool_call_summary=_tool_call_summary(response),
                parser_input_snippet=parser_snippet,
                reservation_id=reservation_id,
                reserved_cost=round(actual_cost, 6),
                reservation_settled=True,
            ))
        return message

    def _refresh_progress(self) -> None:
        if self._progress_refresh is not None:
            self._progress_refresh()

    def _provider_candidates(self, backend: Backend) -> list[Backend]:
        ordered = [b for b in self.routing.backends if b.name not in self._unavailable_backends]
        if backend.name in self._unavailable_backends:
            primary = []
        else:
            primary = [backend]
        if self._gold_edit_t2_repair_turns >= GOLD_EDIT_T2_REPAIR_TURN_LIMIT:
            lower = []
        else:
            lower = [b for b in reversed(ordered) if b.tier < backend.tier]
        higher = [b for b in ordered if b.tier > backend.tier]
        seen: set[str] = set()
        candidates: list[Backend] = []
        for candidate in primary + lower + higher:
            if candidate.name not in seen:
                seen.add(candidate.name)
                candidates.append(candidate)
        return candidates

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
        return {
            "gold_edit_guard_turns": self._gold_edit_t2_repair_turns,
            "gold_edit_guard_limit": GOLD_EDIT_T2_REPAIR_TURN_LIMIT,
            "gold_edit_guard_active": self._gold_edit_t2_repair_turns >= GOLD_EDIT_T2_REPAIR_TURN_LIMIT,
        }

    def _reserve_output_tokens(self, backend: Backend, input_tokens: int) -> int:
        remaining = self.governor.remaining_budget()
        if remaining <= 0:
            return 64
        input_cost = input_tokens * backend.cost_per_input_token
        output_budget = remaining - input_cost
        if output_budget <= 0:
            return 64
        affordable_tokens = output_budget / backend.cost_per_output_token
        headroom = min(1024, max(backend.mean_output_tokens * 2, 256))
        return max(64, min(headroom, int(affordable_tokens * 0.95)))

    def _apply_progress_escalation(self, backend: Backend) -> Backend:
        """Per-tier escalation + turn cap + T4 stop-loss.

        Escalation (no-progress streak): "stuck → try better model."
        - T1→T2, T2→T3, T3→T4
        - T4→T2 (stop-loss: best model couldn't save it, fall back)
        - Resets when progress is made.

        Turn cap: "making progress but too slowly → force upgrade."
        - T1:25, T2:40, T3:60 turns
        """
        if self.routing.strategy not in ("budgetflow_full", "budgetflow_conservative", "budgetflow_value_aware", "budgetflow_equal_weight", "budgetflow_auto_v2", "stage_blind"):
            return backend
        ordered = self.routing.backends
        if len(ordered) < 2:
            return backend

        reason = None
        next_backend = None

        # Check escalation (no-progress streak)
        patience = TIER_ESCALATION_PATIENCE.get(backend.tier)
        if patience is not None and self._no_progress_on_current_tier >= patience:
            if backend.tier == 4:
                # T4 stop-loss: downgrade instead of upgrading
                next_backend = ordered[STRONGEST_DOWNGRADE_TIER - 1]  # tier is 1-indexed
                reason = f"T4-stop-loss streak={self._no_progress_on_current_tier}/{patience}"
            else:
                # Find the next-higher-tier backend (not index-based; works for
                # non-contiguous tier pools like [T2, T3]).
                next_backend = next((b for b in ordered if b.tier > backend.tier), None)
                if next_backend is not None:
                    reason = f"streak={self._no_progress_on_current_tier}/{patience}"

        # Check turn cap
        if reason is None:
            max_turns = TIER_MAX_TURNS.get(backend.tier)
            if max_turns is not None and self._turns_on_current_tier >= max_turns:
                if backend.tier == 4:
                    next_backend = ordered[STRONGEST_DOWNGRADE_TIER - 1]
                    reason = f"T4-turn-cap turns={self._turns_on_current_tier}/{max_turns}"
                else:
                    # Find the next-higher-tier backend (not index-based).
                    next_backend = next((b for b in ordered if b.tier > backend.tier), None)
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

    def _apply_gold_edit_repair_guard(self, backend: Backend, stage) -> Backend:
        """Avoid long T2 repair loops after the agent has touched a gold file."""
        if self.routing.strategy not in (
            "budgetflow_full",
            "budgetflow_conservative",
            "budgetflow_value_aware",
            "budgetflow_equal_weight",
            "budgetflow_auto_v2",
            "stage_blind",
            "budget_only",
        ):
            return backend
        if not self.agent_gold_edited or stage not in (Stage.REPAIR, Stage.VALIDATION):
            return backend
        if backend.tier != 2:
            return backend
        if self._gold_edit_t2_repair_turns < GOLD_EDIT_T2_REPAIR_TURN_LIMIT:
            return backend

        next_backend = next((b for b in self.routing.backends if b.tier > backend.tier), None)
        if next_backend is None:
            print(
                f"{tag('stop', bold=False)} #{self.step_index} "
                f"gold_edit_t2_repair_limit turns={self._gold_edit_t2_repair_turns}/"
                f"{GOLD_EDIT_T2_REPAIR_TURN_LIMIT} no_higher_tier",
                flush=True,
            )
            raise BudgetFlowStagnationError(
                self.workflow_id,
                exit_reason="gold_edit_t2_repair_limit",
                step_index=self.step_index,
                no_progress_streak=self._gold_edit_t2_repair_turns,
            )

        print(
            f"{tag('guard', bold=False)} #{self.step_index} "
            f"gold_edit_t2_repair_limit turns={self._gold_edit_t2_repair_turns}/"
            f"{GOLD_EDIT_T2_REPAIR_TURN_LIMIT} "
            f"{backend_tier_label(backend.name)} -> {backend_tier_label(next_backend.name)}",
            flush=True,
        )
        self._no_progress_on_current_tier = 0
        self._turns_on_current_tier = 0
        return next_backend

    def _reserve_with_downgrade(self, backend: Backend, input_tokens: int) -> Backend:
        ordered = self.routing.backends
        start_index = ordered.index(backend)
        min_tier = 1
        adaptive = self.routing.adaptive
        if adaptive is not None and self.routing.strategy in ("budgetflow_full", "budgetflow_conservative", "budgetflow_value_aware", "budgetflow_equal_weight", "budgetflow_auto_v2", "stage_blind"):
            min_tier = adaptive.min_tier_for_reserve()
        reserve_out = None
        last_reason: str | None = None
        candidates = [c for c in ordered[start_index::-1] if c.tier >= min_tier]
        if not candidates:
            candidates = [c for c in ordered if c.tier >= min_tier]
        for candidate in candidates:
            reserve_out = self._reserve_output_tokens(candidate, input_tokens)
            estimate = self.governor.estimate_cost(
                candidate,
                input_tokens=input_tokens,
                expected_output_tokens=candidate.mean_output_tokens,
                reserve_output_tokens=reserve_out,
            )
            reservation = self.governor.reserve(self.workflow_id, candidate, estimate)
            if reservation is not None:
                self._last_reservation_id = reservation.reservation_id
                self._last_reserve_out = reserve_out
                return candidate
            last_reason = self.governor.last_reserve_failure
        snapshot = self.governor.budget_snapshot()
        exit_reason = last_reason or "budget_exhausted"
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
        config = TIER_CONFIGS.get(backend.name)
        if config is None:
            raise ValueError(f"unknown backend: {backend.name}")
        if config.provider == "aicode007":
            ensure_aicode007_proxy()
        if config.provider == "aicode007":
            api_base = os.environ.get("AICODE007_BASE_URL") or config.api_base
        elif config.provider == "xfyun_maas":
            api_base = os.environ.get("XFYUN_MAAS_BASE_URL") or os.environ.get("XFYUN_MAAS_API_BASE") or config.api_base
        else:
            api_base = config.api_base
        return config.model, {
            "temperature": 0.0,
            "parallel_tool_calls": True,
            "drop_params": True,
            "api_base": api_base,
            "api_key": self._api_keys.get(config.api_key_env),
        }

    def _completion(
        self,
        messages: list[dict],
        *,
        backend_name: str,
        model_name: str,
        model_kwargs: dict[str, Any],
        text_mode: bool = False,
        **kwargs,
    ):
        prepared = [{k: v for k, v in msg.items() if k != "extra"} for msg in messages]
        prepared = _reorder_anthropic_thinking_blocks(prepared)
        prepared = set_cache_control(prepared, mode=self.set_cache_control)

        def _query():
            config = TIER_CONFIGS.get(backend_name)
            if config is not None and config.provider == "aicode007":
                ensure_aicode007_proxy()
            kwargs_merged = {**model_kwargs, **kwargs}
            try:
                return litellm.completion(
                    model=model_name,
                    messages=prepared,
                    timeout=_llm_timeout_s(),
                    **({} if text_mode else {"tools": [BASH_TOOL]}),
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

    def _use_text_mode(self, backend_name: str) -> bool:
        decision = ActionProtocolAdapter.resolve(backend_name)
        return decision.protocol == "text_regex"

    def _parse_actions(self, response, *, text_mode: bool = False, backend_tier: int | None = None) -> list[dict]:
        stop_after = _format_error_stop_after(backend_tier)
        if text_mode:
            content = response.choices[0].message.content or ""
            try:
                actions = parse_regex_actions(
                    content,
                    action_regex=_TEXT_ACTION_REGEX,
                    format_error_template=self.format_error_template,
                )
                self._format_error_streak = 0
                return actions
            except FormatError:
                # Fallback: try JSON {"command": "..."} extraction for GPT-5.4
                json_cmd = _try_extract_json_command(content)
                if json_cmd is not None:
                    logger.info(
                        "text_regex fallback: extracted JSON command for %s step=%d",
                        self.workflow_id, self.step_index,
                    )
                    self._format_error_streak = 0
                    return [{"command": json_cmd}]
                self._format_error_streak += 1
                if self._format_error_streak >= stop_after:
                    raise BudgetFlowStagnationError(
                        self.workflow_id,
                        exit_reason="format_error_text_action",
                        step_index=self.step_index,
                        no_progress_streak=self._format_error_streak,
                    )
                raise

        tool_calls = response.choices[0].message.tool_calls or []
        if tool_calls:
            self._format_error_streak = 0
        counted_format_error = False
        if not tool_calls:
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
            return parse_toolcall_actions(tool_calls, format_error_template=self.format_error_template)
        except FormatError:
            if not counted_format_error:
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
        if message.get("extra", {}).get("text_mode"):
            return format_text_observation_messages(
                outputs,
                observation_template=self.observation_template,
                template_vars=template_vars,
                multimodal_regex=self.multimodal_regex,
            )
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

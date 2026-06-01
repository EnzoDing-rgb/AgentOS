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
from minisweagent.models.utils.anthropic_utils import _reorder_anthropic_thinking_blocks
from minisweagent.models.utils.cache_control import set_cache_control
from minisweagent.models.utils.openai_multimodal import expand_multimodal_content
from minisweagent.models.utils.retry import retry

from ..litellm_quiet import configure_litellm_quiet
from ..budget_pressure import live_budget_pressure
from ..deepseek_backend import ensure_aicode007_proxy, ensure_direct_api, load_env_file
from ..defaults import (
    DASHSCOPE_API_BASE,
    AICODE007_API_BASE,
    PRESSURE_MAX,
    T4_DOWNGRADE_TIER,
    TIER1_BACKEND,
    TIER1_MODEL,
    TIER2_BACKEND,
    TIER2_MODEL,
    TIER3_BACKEND,
    TIER3_MODEL,
    TIER4_BACKEND,
    TIER4_MODEL,
    TIER5_BACKEND,
    TIER5_MODEL,
    TIER_ESCALATION_PATIENCE,
    TIER_MAX_TURNS,
)
from ..console_log import backend_tier_label, bold, dim, routing_stage_label, tag
from ..governor import BudgetGovernor
from ..types import Backend, TurnInfo, WorkflowStatus
from .errors import BudgetFlowBudgetError, BudgetFlowStagnationError, BudgetFlowUpstreamError
from ..run_guards import is_fatal_billing_error, record_billing_halt, record_upstream_error
from .bash_stage import (
    _REPAIR_AGENT_PHASES,
    _VALIDATION_AGENT_PHASES,
    bash_has_progress,
    classify_routing_stage,
)
from .stall_guard import check_stagnation, normalize_bash_command
from .message_utils import estimate_input_tokens, extract_bash_context
from .strategies import RoutingContext, choose_backend, stage_weight

logger = logging.getLogger("budgetflow_litellm_model")

configure_litellm_quiet()

_DASHSCOPE_BACKENDS = frozenset({TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND, TIER4_BACKEND})
_AICODE007_BACKENDS = frozenset({TIER5_BACKEND})


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
) -> dict:
    """Build a single turn-trace dict for observability (no side effects)."""
    trace: dict[str, Any] = {
        "step": step_index,
        "agent_phase": agent_phase,
        "stage": stage.name if stage else None,
        "bash_digest": (bash_command or "")[:120],
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
        self.dashscope_api_key = os.environ.get("DASHSCOPE_API_KEY")
        self.aicode007_api_key = os.environ.get("AICODE007_API_KEY")
        if not self.dashscope_api_key and any(b.name in _DASHSCOPE_BACKENDS for b in routing.backends):
            raise RuntimeError("DASHSCOPE_API_KEY is missing. Add it to the repo root .env file.")
        self.step_index = 0
        self._no_progress_streak = 0
        self._no_progress_on_current_tier = 0  # consecutive non-progress steps on current tier
        self._turns_on_current_tier = 0  # total turns on current tier (for turn cap)
        self._last_backend_tier: int = 0  # track tier changes to reset patience
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._recent_commands: deque[str] = deque(maxlen=16)
        self._progress_refresh = progress_refresh
        self.backend_picks: list[str] = []
        self.last_routing_stage: str = "localization"
        self.last_backend_name: str = "-"
        self.agent_phase: str | None = None
        self.last_exit_reason: str | None = None
        self.last_budget_snapshot: dict[str, float] | None = None
        self._enable_turn_trace: bool = enable_turn_trace
        self.turn_traces: list[dict] = []
        self._last_reserve_out: int = 0
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
            w_i = 1.0 if self.routing.strategy == "stage_blind" else stage_weight(stage),
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
        has_progress, progress_reason = bash_has_progress(bash_command)
        if has_progress or phase in _REPAIR_AGENT_PHASES or phase in _VALIDATION_AGENT_PHASES:
            if not has_progress and phase in _REPAIR_AGENT_PHASES:
                progress_reason = "repair_pattern"
            elif not has_progress and phase in _VALIDATION_AGENT_PHASES:
                progress_reason = "validation_pattern"
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
        if self.routing.adaptive is not None and self.routing.strategy in ("budgetflow_full", "stage_blind"):
            forced_tier = self.routing.adaptive.rescue.forced_min_tier(
                stage=stage,
                agent_phase=self.agent_phase,
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
        prev_tier = self._last_backend_tier
        backend = self._apply_progress_escalation(backend)
        escalated_backend = backend.name
        backend = self._reserve_with_downgrade(backend, input_tokens)
        reserve_out = self._last_reserve_out
        if backend.tier != prev_tier and prev_tier > 0:
            self._no_progress_on_current_tier = 0  # tier changed, reset patience
            self._turns_on_current_tier = 0  # tier changed, reset turn counter
        self._last_backend_tier = backend.tier
        self._turns_on_current_tier += 1
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
        response_ok = True
        error_type = None
        try:
            response = self._completion(
                messages,
                backend_name=backend.name,
                model_name=model_name,
                model_kwargs=model_kwargs,
                **kwargs,
            )
        except Exception as exc:
            response_ok = False
            error_type = type(exc).__name__
            if self._enable_turn_trace:
                self.turn_traces.append(_build_turn_trace(
                    step_index=self.step_index,
                    agent_phase=self.agent_phase,
                    stage=stage,
                    bash_command=bash_command,
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
                ))
            raise
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
        message["extra"] = {
            "actions": self._parse_actions(response),
            "response": response.model_dump(),
            "cost": billable,
            "backend": backend.name,
            "stage": stage.value,
        }
        if self._enable_turn_trace:
            self.turn_traces.append(_build_turn_trace(
                step_index=self.step_index,
                agent_phase=self.agent_phase,
                stage=stage,
                bash_command=bash_command,
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
            ))
        return message

    def _refresh_progress(self) -> None:
        if self._progress_refresh is not None:
            self._progress_refresh()

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
        if self.routing.strategy not in ("budgetflow_full", "stage_blind"):
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
                next_backend = ordered[T4_DOWNGRADE_TIER - 1]  # tier is 1-indexed
                reason = f"T4-stop-loss streak={self._no_progress_on_current_tier}/{patience}"
            else:
                next_tier_idx = backend.tier
                if next_tier_idx < len(ordered):
                    next_backend = ordered[next_tier_idx]
                    reason = f"streak={self._no_progress_on_current_tier}/{patience}"

        # Check turn cap
        if reason is None:
            max_turns = TIER_MAX_TURNS.get(backend.tier)
            if max_turns is not None and self._turns_on_current_tier >= max_turns:
                if backend.tier == 4:
                    next_backend = ordered[T4_DOWNGRADE_TIER - 1]
                    reason = f"T4-turn-cap turns={self._turns_on_current_tier}/{max_turns}"
                elif backend.tier < len(ordered):
                    next_backend = ordered[backend.tier]
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

    def _reserve_with_downgrade(self, backend: Backend, input_tokens: int) -> Backend:
        ordered = self.routing.backends
        start_index = ordered.index(backend)
        min_tier = 1
        adaptive = self.routing.adaptive
        if adaptive is not None and self.routing.strategy in ("budgetflow_full", "stage_blind"):
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
        if backend.name in _DASHSCOPE_BACKENDS:
            common = {
                "temperature": 0.0,
                "parallel_tool_calls": True,
                "drop_params": True,
                "api_base": DASHSCOPE_API_BASE,
                "api_key": self.dashscope_api_key,
            }
            model_map = {
                TIER1_BACKEND: TIER1_MODEL,
                TIER2_BACKEND: TIER2_MODEL,
                TIER3_BACKEND: TIER3_MODEL,
                TIER4_BACKEND: TIER4_MODEL,
            }
            return model_map[backend.name], common
        if backend.name in _AICODE007_BACKENDS:
            if not self.aicode007_api_key:
                raise RuntimeError("AICODE007_API_KEY is missing. Add it to the repo root .env file.")
            ensure_aicode007_proxy()
            return TIER5_MODEL, {
                "temperature": 0.0,
                "parallel_tool_calls": True,
                "drop_params": True,
                "api_base": os.environ.get("AICODE007_BASE_URL") or AICODE007_API_BASE,
                "api_key": self.aicode007_api_key,
            }
        raise ValueError(f"unknown backend: {backend.name}")

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
            if backend_name in _DASHSCOPE_BACKENDS:
                kwargs_merged = {
                    "api_base": DASHSCOPE_API_BASE,
                    "api_key": self.dashscope_api_key,
                    **model_kwargs,
                    **kwargs,
                }
            elif backend_name in _AICODE007_BACKENDS:
                ensure_aicode007_proxy()
                kwargs_merged = {**model_kwargs, **kwargs}
            else:
                kwargs_merged = {**model_kwargs, **kwargs}
            return litellm.completion(
                model=model_name,
                messages=prepared,
                tools=[BASH_TOOL],
                **kwargs_merged,
            )

        try:
            for attempt in retry(logger=logger, abort_exceptions=[KeyboardInterrupt]):
                with attempt:
                    return _query()
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

    def _parse_actions(self, response) -> list[dict]:
        tool_calls = response.choices[0].message.tool_calls or []
        return parse_toolcall_actions(tool_calls, format_error_template=self.format_error_template)

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

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
    AICODE007_API_BASE,
    DEEPSEEK_API_BASE,
    ESCALATION_THRESHOLD,
    PRESSURE_MAX,
    TIER1_BACKEND,
    TIER1_MODEL,
    TIER2_BACKEND,
    TIER2_MODEL,
    TIER3_BACKEND,
    TIER3_MODEL,
)
from ..console_log import backend_tier_label, bold, dim, routing_stage_label, tag
from ..governor import BudgetGovernor
from ..types import Backend, TurnInfo, WorkflowStatus
from .errors import BudgetFlowBudgetError, BudgetFlowStagnationError, BudgetFlowUpstreamError
from ..run_guards import record_upstream_error
from .bash_stage import bash_has_progress, classify_routing_stage
from .stall_guard import check_stagnation, normalize_bash_command
from .message_utils import estimate_input_tokens, extract_bash_context
from .strategies import RoutingContext, choose_backend, stage_weight

logger = logging.getLogger("budgetflow_litellm_model")

configure_litellm_quiet()

_DEEPSEEK_BACKENDS = frozenset({TIER2_BACKEND, TIER3_BACKEND})
_AICODE_BACKENDS = frozenset({TIER1_BACKEND})


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
        self.deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not self.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is missing. Add it to the repo root .env file.")
        self.aicode_api_key = os.environ.get("AICODE007_API_KEY")
        if not self.aicode_api_key:
            raise RuntimeError("AICODE007_API_KEY is missing. Add it to the repo root .env file.")
        self.step_index = 0
        self._no_progress_streak = 0
        self._recent_commands: deque[str] = deque(maxlen=16)
        self._progress_refresh = progress_refresh
        self.backend_picks: list[str] = []
        self.last_routing_stage: str = "localization"
        self.last_backend_name: str = "-"
        self.agent_phase: str | None = None
        self.last_exit_reason: str | None = None
        self.last_budget_snapshot: dict[str, float] | None = None
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
            w_i=stage_weight(stage),
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
        self.routing.budget_pressure = live_budget_pressure(
            self.governor,
            init=self._pressure_init,
            pressure_max=self._pressure_max,
        )
        if bash_has_progress(bash_command):
            self._no_progress_streak = 0
        else:
            self._no_progress_streak += 1
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
        backend = self._apply_progress_escalation(backend)
        backend = self._reserve_with_downgrade(backend, input_tokens)
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
        response = self._completion(
            messages,
            backend_name=backend.name,
            model_name=model_name,
            model_kwargs=model_kwargs,
            **kwargs,
        )
        message = response.choices[0].message.model_dump()
        prompt_tokens = getattr(response.usage, "prompt_tokens", None) or input_tokens
        completion_tokens = getattr(response.usage, "completion_tokens", None) or backend.mean_output_tokens
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
        if self.routing.strategy != "budgetflow_full":
            return backend
        ordered = self.routing.backends
        if len(ordered) < 2:
            return backend
        if self._no_progress_streak >= ESCALATION_THRESHOLD * 2:
            floor = ordered[-1]
        elif self._no_progress_streak >= ESCALATION_THRESHOLD:
            floor = ordered[1]
        else:
            return backend
        if backend.tier >= floor.tier:
            return backend
        print(
            f"{tag('escalate', bold=False)} #{self.step_index} "
            f"streak={self._no_progress_streak} "
            f"{backend_tier_label(backend.name)} -> {backend_tier_label(floor.name)}",
            flush=True,
        )
        return floor

    def _reserve_with_downgrade(self, backend: Backend, input_tokens: int) -> Backend:
        ordered = self.routing.backends
        start_index = ordered.index(backend)
        reserve_out = None
        last_reason: str | None = None
        for candidate in ordered[start_index::-1]:
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
        if backend.name in _DEEPSEEK_BACKENDS:
            common = {
                "temperature": 0.0,
                "parallel_tool_calls": True,
                "drop_params": True,
                "api_base": DEEPSEEK_API_BASE,
                "api_key": self.deepseek_api_key,
            }
            if backend.name == TIER2_BACKEND:
                return TIER2_MODEL, common
            return TIER3_MODEL, common
        if backend.name in _AICODE_BACKENDS:
            common = {
                "temperature": 0.0,
                "parallel_tool_calls": True,
                "drop_params": True,
                "api_base": AICODE007_API_BASE,
                "api_key": self.aicode_api_key,
            }
            return TIER1_MODEL, common
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
            if backend_name in _AICODE_BACKENDS:
                ensure_aicode007_proxy()
            else:
                ensure_direct_api()
            return litellm.completion(
                model=model_name,
                messages=prepared,
                tools=[BASH_TOOL],
                **(model_kwargs | kwargs),
            )

        try:
            for attempt in retry(logger=logger, abort_exceptions=[KeyboardInterrupt]):
                with attempt:
                    return _query()
        except Exception as exc:  # noqa: BLE001
            action = record_upstream_error(str(exc), backend=backend_name)
            if action.halt_all:
                raise BudgetFlowUpstreamError(
                    self.workflow_id,
                    exit_reason=action.reason or "upstream_guard",
                    step_index=self.step_index,
                    backend=backend_name,
                    sample=str(exc),
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

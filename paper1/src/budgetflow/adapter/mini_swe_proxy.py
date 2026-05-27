from __future__ import annotations

import logging
import os
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

from ..deepseek_backend import ensure_direct_api, load_env_file
from ..defaults import DEEPSEEK_API_BASE, DEEPSEEK_FLASH_MODEL, DEEPSEEK_PRO_MODEL
from ..governor import BudgetGovernor
from ..types import Backend, TurnInfo, WorkflowStatus
from .errors import BudgetFlowBudgetError
from .bash_stage import classify_bash_stage
from .message_utils import estimate_input_tokens, extract_bash_context
from .strategies import RoutingContext, choose_backend, stage_weight

logger = logging.getLogger("budgetflow_litellm_model")


class BudgetFlowLitellmModel:
    """mini-SWE-agent Model that routes each query through BudgetFlow governor + DeepSeek Flash/Pro."""

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
    ) -> None:
        load_env_file()
        self.workflow_id = workflow_id
        self.governor = governor
        self.routing = routing
        self.default_max_output_tokens = default_max_output_tokens
        self.cost_tracking = cost_tracking
        self.observation_template = observation_template or (
            "{% if output.exception_info %}<exception>{{output.exception_info}}</exception>\n{% endif %}"
            "<returncode>{{output.returncode}}</returncode>\n<output>\n{{output.output}}</output>"
        )
        self.format_error_template = format_error_template or "{{ error }}"
        self.set_cache_control = set_cache_control
        self.multimodal_regex = multimodal_regex
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is missing. Add it to the repo root .env file.")
        self.step_index = 0
        self.backend_picks: list[str] = []
        self.last_exit_reason: str | None = None
        self.last_budget_snapshot: dict[str, float] | None = None
        self.config = type("Config", (), {"model_name": DEEPSEEK_PRO_MODEL})()

    def query(self, messages: list[dict[str, str]], **kwargs) -> dict:
        self.step_index += 1
        bash_command, observation = extract_bash_context(messages)
        stage = classify_bash_stage(bash_command, observation)
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
        backend = choose_backend(self.routing, turn, expected_costs)
        backend = self._reserve_with_downgrade(backend, input_tokens)
        self.backend_picks.append(backend.name)

        model_name, model_kwargs = self._model_config_for(backend)
        response = self._completion(messages, model_name=model_name, model_kwargs=model_kwargs, **kwargs)
        message = response.choices[0].message.model_dump()
        prompt_tokens = getattr(response.usage, "prompt_tokens", None) or input_tokens
        completion_tokens = getattr(response.usage, "completion_tokens", None) or backend.mean_output_tokens
        actual_cost = (
            prompt_tokens * backend.cost_per_input_token
            + completion_tokens * backend.cost_per_output_token
        )
        reservation_id = self._last_reservation_id
        self.governor.settle(reservation_id, actual_cost, WorkflowStatus.RUNNING)
        message["extra"] = {
            "actions": self._parse_actions(response),
            "response": response.model_dump(),
            "cost": actual_cost,
            "backend": backend.name,
            "stage": stage.value,
        }
        return message

    def _reserve_output_tokens(self, backend: Backend) -> int:
        # Reserve against expected output + headroom, not full 4096 max.
        return min(1024, max(backend.mean_output_tokens * 2, 256))

    def _reserve_with_downgrade(self, backend: Backend, input_tokens: int) -> Backend:
        ordered = self.routing.backends
        start_index = ordered.index(backend)
        reserve_out = None
        last_reason: str | None = None
        for candidate in ordered[start_index::-1]:
            reserve_out = self._reserve_output_tokens(candidate)
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
        if backend.name == "deepseek_flash":
            return DEEPSEEK_FLASH_MODEL, {
                "api_base": DEEPSEEK_API_BASE,
                "api_key": self.api_key,
                "temperature": 0.0,
                "parallel_tool_calls": True,
                "drop_params": True,
                "extra_body": {"thinking": {"type": "disabled"}},
            }
        return DEEPSEEK_PRO_MODEL, {
            "api_base": DEEPSEEK_API_BASE,
            "api_key": self.api_key,
            "temperature": 0.0,
            "parallel_tool_calls": True,
            "drop_params": True,
            "extra_body": {"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
        }

    def _completion(self, messages: list[dict], *, model_name: str, model_kwargs: dict[str, Any], **kwargs):
        prepared = [{k: v for k, v in msg.items() if k != "extra"} for msg in messages]
        prepared = _reorder_anthropic_thinking_blocks(prepared)
        prepared = set_cache_control(prepared, mode=self.set_cache_control)

        def _query():
            ensure_direct_api()
            return litellm.completion(
                model=model_name,
                messages=prepared,
                tools=[BASH_TOOL],
                **(model_kwargs | kwargs),
            )

        for attempt in retry(logger=logger, abort_exceptions=[KeyboardInterrupt]):
            with attempt:
                return _query()

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

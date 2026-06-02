"""Tests for P0 trace extension: new fields in _build_turn_trace."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.adapter.mini_swe_proxy import (
    _build_turn_trace,
    _router_trace_fields,
    _provider_trace_fields,
    _protocol_trace_fields,
)
from budgetflow.adapter.strategies import RoutingContext, build_routing_context
from budgetflow.types import Backend, Stage


class TestTraceExtension:
    def test_trace_includes_provider_model(self):
        trace = _build_turn_trace(
            step_index=1, agent_phase=None, stage=Stage.LOCALIZATION,
            bash_command="test", input_tokens=100,
            expected_costs={}, base_pressure=0.01, effective_pressure=0.01,
            backend_chosen="tier2", escalated_backend="tier2",
            final_backend="tier2", backend_tier=2, reserve_out=256,
            adaptive=None, no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=1, has_progress=False, progress_reason="",
            prompt_tokens=100, completion_tokens=50,
            actual_cost=0.5, billable=0.5, response_ok=True, error_type=None,
            provider="dashscope", model="openai/qwen3-coder-plus",
        )
        assert trace["provider"] == "dashscope"
        assert trace["model"] == "openai/qwen3-coder-plus"

    def test_trace_includes_protocol_parser(self):
        trace = _build_turn_trace(
            step_index=1, agent_phase=None, stage=Stage.LOCALIZATION,
            bash_command="test", input_tokens=100,
            expected_costs={}, base_pressure=0.01, effective_pressure=0.01,
            backend_chosen="tier3", escalated_backend="tier3",
            final_backend="tier3", backend_tier=3, reserve_out=256,
            adaptive=None, no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=1, has_progress=False, progress_reason="",
            prompt_tokens=100, completion_tokens=50,
            actual_cost=0.5, billable=0.5, response_ok=True, error_type=None,
            text_mode=True, protocol="text_regex", parser="parse_regex_actions",
        )
        assert trace["text_mode"] is True
        assert trace["protocol"] == "text_regex"
        assert trace["parser"] == "parse_regex_actions"

    def test_trace_includes_assistant_content(self):
        trace = _build_turn_trace(
            step_index=1, agent_phase=None, stage=Stage.LOCALIZATION,
            bash_command="test", input_tokens=100,
            expected_costs={}, base_pressure=0.01, effective_pressure=0.01,
            backend_chosen="tier2", escalated_backend="tier2",
            final_backend="tier2", backend_tier=2, reserve_out=256,
            adaptive=None, no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=1, has_progress=False, progress_reason="",
            prompt_tokens=100, completion_tokens=50,
            actual_cost=0.5, billable=0.5, response_ok=True, error_type=None,
            assistant_content_head="```bash\necho test\n```",
        )
        assert "echo test" in trace["assistant_content_head"]

    def test_trace_includes_parser_error(self):
        trace = _build_turn_trace(
            step_index=1, agent_phase=None, stage=Stage.LOCALIZATION,
            bash_command="test", input_tokens=100,
            expected_costs={}, base_pressure=0.01, effective_pressure=0.01,
            backend_chosen="tier3", escalated_backend="tier3",
            final_backend="tier3", backend_tier=3, reserve_out=256,
            adaptive=None, no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=1, has_progress=False, progress_reason="",
            prompt_tokens=100, completion_tokens=50,
            actual_cost=0.5, billable=0.5, response_ok=True,
            error_type="FormatError",
            parser_error_type="FormatError",
            parser_error_message="No action found in content",
        )
        assert trace["parser_error_type"] == "FormatError"
        assert "No action" in trace["parser_error_message"]

    def test_trace_includes_provider_error(self):
        trace = _build_turn_trace(
            step_index=1, agent_phase=None, stage=Stage.LOCALIZATION,
            bash_command="test", input_tokens=100,
            expected_costs={}, base_pressure=0.01, effective_pressure=0.01,
            backend_chosen="tier3", escalated_backend="tier3",
            final_backend="tier3", backend_tier=3, reserve_out=256,
            adaptive=None, no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=1, has_progress=False, progress_reason="",
            prompt_tokens=0, completion_tokens=0,
            actual_cost=0.0, billable=0.0, response_ok=False,
            error_type="ServiceUnavailableError",
            provider_status_code=503,
            provider_error_body="service temporarily unavailable",
        )
        assert trace["provider_status_code"] == 503
        assert "unavailable" in trace["provider_error_body"]

    def test_trace_includes_reservation_lifecycle(self):
        trace = _build_turn_trace(
            step_index=1, agent_phase=None, stage=Stage.LOCALIZATION,
            bash_command="test", input_tokens=100,
            expected_costs={}, base_pressure=0.01, effective_pressure=0.01,
            backend_chosen="tier2", escalated_backend="tier2",
            final_backend="tier2", backend_tier=2, reserve_out=256,
            adaptive=None, no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=1, has_progress=False, progress_reason="",
            prompt_tokens=100, completion_tokens=50,
            actual_cost=0.5, billable=0.5, response_ok=True, error_type=None,
            reservation_id="res-123",
            reserved_cost=0.8,
            reservation_settled=True,
        )
        assert trace["reservation_id"] == "res-123"
        assert trace["reserved_cost"] == 0.8
        assert trace["reservation_settled"] is True
        assert trace["reservation_released"] is False

    def test_trace_includes_router_reasoning(self):
        trace = _build_turn_trace(
            step_index=1, agent_phase=None, stage=Stage.LOCALIZATION,
            bash_command="test", input_tokens=100,
            expected_costs={}, base_pressure=0.01, effective_pressure=0.01,
            backend_chosen="tier2", escalated_backend="tier2",
            final_backend="tier2", backend_tier=2, reserve_out=256,
            adaptive=None, no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=1, has_progress=False, progress_reason="",
            prompt_tokens=100, completion_tokens=50,
            actual_cost=0.5, billable=0.5, response_ok=True, error_type=None,
            router_reason="cheapest_baseline_n2",
            router_scores={},
            router_pressure=0.01,
            router_branch="budget_only",
        )
        assert trace["router_reason"] == "cheapest_baseline_n2"
        assert trace["router_branch"] == "budget_only"
        assert trace["router_pressure"] == 0.01

    def test_trace_old_fields_still_present(self):
        """Backward-compat: old fields survive the extension."""
        trace = _build_turn_trace(
            step_index=5, agent_phase="repair", stage=Stage.REPAIR,
            bash_command="git diff", input_tokens=200,
            expected_costs={"tier2": 1.0}, base_pressure=0.01,
            effective_pressure=0.02, backend_chosen="tier2",
            escalated_backend="tier2", final_backend="tier2",
            backend_tier=2, reserve_out=512, adaptive=None,
            no_progress_streak=0, no_progress_on_tier=0,
            turns_on_tier=3, has_progress=True, progress_reason="repair_pattern",
            prompt_tokens=200, completion_tokens=100,
            actual_cost=1.0, billable=1.0, response_ok=True, error_type=None,
        )
        assert trace["step"] == 5
        assert trace["stage"] == "REPAIR"
        assert trace["backend_tier"] == 2
        assert trace["has_progress"] is True
        assert trace["response_ok"] is True
        assert trace["actual_cost"] == 1.0


class TestHelperFunctions:
    def test_provider_trace_fields_tier2(self):
        fields = _provider_trace_fields("tier2")
        assert fields["provider"] == "dashscope"
        assert "qwen3-coder-plus" in fields["model"]

    def test_provider_trace_fields_tier3(self):
        fields = _provider_trace_fields("tier3")
        assert fields["provider"] == "aicode007"
        assert "gpt-5.4" in fields["model"]

    def test_protocol_trace_fields_text_mode(self):
        fields = _protocol_trace_fields("tier3", text_mode=True)
        assert fields["protocol"] == "text_regex"
        assert fields["text_mode"] is True

    def test_protocol_trace_fields_tool_mode(self):
        fields = _protocol_trace_fields("tier2", text_mode=False)
        assert fields["protocol"] == "tool_call"
        assert fields["text_mode"] is False

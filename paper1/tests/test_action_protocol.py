from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_tiers_use_canonical_tool_call_protocol() -> None:
    from budgetflow.adapter.protocol_adapter import ActionProtocolAdapter
    from budgetflow.defaults import TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND

    for backend in (TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND):
        decision = ActionProtocolAdapter.resolve(backend)
        assert decision.protocol == "tool_call"
        assert decision.parser == "parse_toolcall_actions"
        assert decision.reason == "canonical_tool_call"


def test_parser_failure_trace_has_required_fields() -> None:
    from budgetflow.adapter.turn_trace import build_turn_trace

    trace = build_turn_trace(
        step_index=1,
        agent_phase=None,
        stage=None,
        bash_command="cd /tmp",
        input_tokens=100,
        expected_costs={},
        base_pressure=0.1,
        effective_pressure=0.1,
        backend_chosen="tier3",
        escalated_backend="tier3",
        final_backend="tier3",
        backend_tier=3,
        reserve_out=256,
        adaptive=None,
        no_progress_streak=0,
        no_progress_on_tier=0,
        turns_on_tier=1,
        has_progress=False,
        progress_reason="",
        prompt_tokens=100,
        completion_tokens=50,
        actual_cost=0.001,
        billable=0.001,
        response_ok=True,
        error_type="FormatError",
        protocol="tool_call",
        parser="parse_toolcall_actions",
        parser_input_snippet='{"count": 0}',
        assistant_content_head="",
        parser_error_type="FormatError",
        parser_error_message="No tool calls found in the response.",
    )

    assert trace["parser_input_snippet"] is not None
    assert trace["assistant_content_head"] == ""
    assert trace["parser_error_type"] == "FormatError"
    assert "parser_error_message" in trace
    assert trace["protocol"] == "tool_call"

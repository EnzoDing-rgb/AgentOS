from __future__ import annotations

import pytest
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

from budgetflow.adapter.stall_guard import stall_guard_enabled

# mini_swe_proxy imports minisweagent, which may not be installed.
_minisweagent_available = True
try:
    import minisweagent  # noqa: F401
except ImportError:
    _minisweagent_available = False

requires_minisweagent = pytest.mark.skipif(
    not _minisweagent_available, reason="minisweagent not installed"
)


# ── _classify_format_reason ──────────────────────────────────────────────────


class _FakeMessage:
    def __init__(self, content="", tool_calls=None, **extra):
        self.content = content
        self.tool_calls = tool_calls
        self._extra = dict(extra)

    def model_dump(self):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": self.tool_calls,
            **self._extra,
        }


class _FakeResponse:
    """Minimal fake for testing _classify_format_reason."""
    def __init__(self, content="", tool_calls=None, **message_extra):
        self.choices = [MagicMock()]
        self.choices[0].message = _FakeMessage(content, tool_calls, **message_extra)
        self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    def model_dump(self):
        return {
            "choices": [
                {
                    "message": self.choices[0].message.model_dump(),
                }
            ]
        }


class _FakeFormatError(Exception):
    """FormatError-compatible exception for testing."""
    def __init__(self, n_actions=None):
        if n_actions is not None:
            payload = {"extra": {"n_actions": n_actions}}
            super().__init__(payload)
        else:
            super().__init__("bad format")


@requires_minisweagent
def test_classify_found_2_actions_from_payload():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError(n_actions=2)
    resp = _FakeResponse(content="```bash\ncmd1\n```\n```bash\ncmd2\n```")
    assert _classify_format_reason(exc, resp) == "found_2_actions"


@requires_minisweagent
def test_classify_found_0_actions_from_payload():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError(n_actions=0)
    resp = _FakeResponse(content="garbage")
    assert _classify_format_reason(exc, resp) == "found_0_actions"


@requires_minisweagent
@requires_minisweagent
def test_classify_no_tool_call_tool_mode():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError()
    resp = _FakeResponse(content="", tool_calls=[])
    assert _classify_format_reason(exc, resp) == "found_0_actions"


@requires_minisweagent
def test_classify_invalid_tool_call_when_tool_calls_present():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError()
    tc1 = MagicMock()
    tc2 = MagicMock()
    resp = _FakeResponse(content="", tool_calls=[tc1, tc2])
    assert _classify_format_reason(exc, resp) == "invalid_tool_call"


# ── Stall guard gating + protocol retry interaction ──────────────────────────


def test_stall_guard_disabled_means_no_stagnation_on_bare():
    """Bare baselines skip check_stagnation; they should not get stuck."""
    assert not stall_guard_enabled("all_tier2")
    assert not stall_guard_enabled("bare_t3")
    assert not stall_guard_enabled("enterprise_router")


def test_stall_guard_enabled_means_stagnation_possible():
    """BudgetFlow strategies still get stall guard."""
    assert stall_guard_enabled("budgetflow_segment")
    assert stall_guard_enabled("budgetflow_same_router")


def test_parser_abort_breakdown_with_retry_fields():
    """New runs with explicit protocol_retry fields."""
    from budgetflow.run_observability.audit import _parser_abort_breakdown

    records = [
        {
            "protocol_retry_used": True,
            "protocol_retry_success": True,
            "protocol_retry_reason": "found_2_actions",
            "exit_status": "FormatError",
            "exit_reason": "format_error_text_action",
        },
        {
            "protocol_retry_used": True,
            "protocol_retry_success": False,
            "protocol_retry_reason": "found_0_actions",
            "exit_status": "FormatError",
            "exit_reason": "format_error_text_action",
        },
        {
            "protocol_retry_used": True,
            "protocol_retry_success": True,
            "protocol_retry_reason": "found_0_actions",
            "exit_status": "FormatError",
            "exit_reason": "format_error_no_tool_calls",
        },
    ]
    result = _parser_abort_breakdown(records)
    assert result["retry_success"] == 2
    assert result["retry_failed"] == 1
    assert result["found_2_actions"] == 0
    assert result["found_0_actions"] == 1


def test_parser_abort_breakdown_prefers_per_turn_retry_fields():
    """One task can have multiple retry turns; audit must not collapse them."""
    from budgetflow.run_observability.audit import _parser_abort_breakdown

    records = [
        {
            "protocol_retry_used": True,
            "protocol_retry_success": True,
            "protocol_retry_reason": "found_2_actions",
            "turn_traces": [
                {
                    "protocol_retry_used": True,
                    "protocol_retry_success": True,
                    "protocol_retry_reason": "found_2_actions",
                    "protocol_retry_attempts": 1,
                },
                {
                    "protocol_retry_used": True,
                    "protocol_retry_success": False,
                    "protocol_retry_reason": "found_0_actions",
                    "protocol_retry_attempts": 1,
                },
            ],
        },
    ]

    result = _parser_abort_breakdown(records)
    assert result["retry_success"] == 1
    assert result["retry_failed"] == 1
    assert result["found_0_actions"] == 1


def test_parser_abort_breakdown_empty():
    from budgetflow.run_observability.audit import _parser_abort_breakdown

    result = _parser_abort_breakdown([])
    assert result["found_0_actions"] == 0
    assert result["found_2_actions"] == 0
    assert "empty_response" not in result
    assert result["unknown"] == 0
    assert result["retry_success"] == 0
    assert result["retry_failed"] == 0


def test_parser_abort_ignores_non_format_errors():
    """Non-format errors are not counted in parser breakdown."""
    from budgetflow.run_observability.audit import _parser_abort_breakdown

    records = [
        {"exit_status": "NameError", "exit_reason": "NameError"},
        {"exit_status": "StagnationExit", "exit_reason": "stagnation_no_progress"},
        {"exit_status": "HarnessFailed", "exit_reason": "harness_failed"},
    ]
    result = _parser_abort_breakdown(records)
    assert all(v == 0 for v in result.values())


# ── Per-reason parse error thresholds ────────────────────────────────────────


@requires_minisweagent
def test_format_error_stop_after_default():
    from budgetflow.adapter.action_parsing import format_error_stop_after

    assert format_error_stop_after() == 4
    assert format_error_stop_after(error_reason="") == 4
    assert format_error_stop_after(error_reason="unknown") == 4


@requires_minisweagent
def test_format_error_stop_after_found_2_actions():
    from budgetflow.adapter.action_parsing import format_error_stop_after

    assert format_error_stop_after(error_reason="found_2_actions") == 4


@requires_minisweagent
def test_format_error_stop_after_found_0():
    from budgetflow.adapter.action_parsing import format_error_stop_after

    assert format_error_stop_after(error_reason="found_0_actions") == 3
    assert format_error_stop_after(error_reason="invalid_tool_call") == 3


@requires_minisweagent
def test_parse_actions_no_tool_calls_uses_current_reason_limit():
    """No tool calls should stop on the found_0_actions threshold."""
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
    from budgetflow.adapter.errors import BudgetFlowStagnationError

    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.step_index = 7
    model.format_error_template = "{{ error }}"
    model._format_error_streak = 2
    model._protocol_retry_reason = ""
    model._protocol_retry_limit = 4

    resp = _FakeResponse(content="", tool_calls=[])
    try:
        model._parse_actions(resp, backend_tier=3)
        assert False, "third consecutive no-tool response should stop"
    except BudgetFlowStagnationError:
        pass

    assert model._protocol_retry_reason == "found_0_actions"
    assert model._protocol_retry_limit == 3


@requires_minisweagent
def test_parse_actions_invalid_tool_call_accumulates_streak():
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
    from budgetflow.adapter.errors import BudgetFlowStagnationError

    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.step_index = 8
    model.format_error_template = "{{ error }}"
    model._format_error_streak = 2
    model._protocol_retry_reason = "found_0_actions"
    model._protocol_retry_limit = 3

    resp = _FakeResponse(content="", tool_calls=[MagicMock(), MagicMock()])
    with pytest.raises(BudgetFlowStagnationError):
        model._parse_actions(resp, backend_tier=3)

    assert model._protocol_retry_reason == "invalid_tool_call"
    assert model._protocol_retry_limit == 3
    assert model._format_error_streak == 3


@requires_minisweagent
def test_query_retries_final_no_tool_call_before_protocol_abort(monkeypatch):
    from budgetflow.adapter.backends import build_ceiling_backends
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
    from budgetflow.adapter.strategies import build_routing_context
    from budgetflow.governor import BudgetGovernor
    from budgetflow.ledger import WorkflowLedgerStore
    from budgetflow.types import GovernorConfig

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("AICODE007_API_KEY", "test")

    governor = BudgetGovernor(
        GovernorConfig(total_budget=100.0, default_max_output_tokens=128),
        WorkflowLedgerStore(),
    )
    model = BudgetFlowLitellmModel(
        workflow_id="wf",
        governor=governor,
        routing=build_routing_context("all_t3", build_ceiling_backends(), budget_pressure=0.1),
        default_max_output_tokens=128,
        enable_turn_trace=True,
    )
    model._api_keys = {
        "DASHSCOPE_API_KEY": "test",
        "DEEPSEEK_API_KEY": "test",
        "AICODE007_API_KEY": "test",
    }
    model._model_config_for = lambda backend, *, max_tokens=None: (
        backend.name,
        {"max_tokens": max_tokens} if max_tokens is not None else {},
    )
    model._format_error_streak = 2

    valid_tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="bash", arguments='{"command":"pwd"}'),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[]),
        _FakeResponse(content="", tool_calls=[valid_tool_call]),
    ]
    attempts = []

    def fake_completion(messages, *, backend_name, **kwargs):
        attempts.append(messages)
        return responses.pop(0)

    model._completion = fake_completion

    message = model.query([{"role": "user", "content": "inspect"}])

    assert len(attempts) == 2
    assert message["extra"]["actions"] == [{"command": "pwd", "tool_call_id": "call_1"}]
    assert model._format_error_streak == 0
    assert model._protocol_retry_used is True
    assert model._protocol_retry_success is True
    assert model._protocol_retry_reason == "found_0_actions"


@requires_minisweagent
def test_retry_message_strips_unexecuted_tool_calls_but_preserves_reasoning_history():
    from budgetflow.adapter.mini_swe_proxy import _format_retry_assistant_message

    response = _FakeResponse(
        content="",
        tool_calls=[MagicMock(id="bad_call")],
        reasoning_content="hidden reasoning token",
    )

    message = _format_retry_assistant_message(response)

    assert message["role"] == "assistant"
    assert "invalid tool calls" in message["content"]
    assert "tool_calls" not in message
    assert message["reasoning_content"] == "hidden reasoning token"


@requires_minisweagent
def test_provider_messages_preserve_legal_tool_history():
    from budgetflow.adapter.mini_swe_proxy import _prepare_provider_messages

    tool_calls = [MagicMock(id="call_1")]
    prepared = _prepare_provider_messages([
        {
            "role": "assistant",
            "content": "running command",
            "tool_calls": tool_calls,
            "reasoning_content": "hidden reasoning token",
            "extra": {"local": True},
        },
        {
            "role": "tool",
            "content": "<returncode>0</returncode>",
            "tool_call_id": "call_1",
            "extra": {"local": True},
            "provider_only": None,
        },
    ])
    assert prepared == [
        {
            "role": "assistant",
            "content": "running command",
            "tool_calls": tool_calls,
            "reasoning_content": "hidden reasoning token",
        },
        {
            "role": "tool",
            "content": "<returncode>0</returncode>",
            "tool_call_id": "call_1",
        },
    ]


@requires_minisweagent
def test_provider_messages_reject_unpaired_tool_calls():
    from budgetflow.adapter.mini_swe_proxy import _prepare_provider_messages

    with pytest.raises(ValueError, match="assistant tool_calls"):
        _prepare_provider_messages([
            {
                "role": "assistant",
                "content": "running command",
                "tool_calls": [MagicMock(id="call_1")],
            },
            {"role": "user", "content": "retry"},
        ])

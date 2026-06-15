from __future__ import annotations

import pytest
from collections import deque
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


class _FakeResponse:
    """Minimal fake for testing _classify_format_reason."""
    def __init__(self, content="", tool_calls=None):
        self.choices = [MagicMock()]
        self.choices[0].message = MagicMock()
        self.choices[0].message.content = content
        self.choices[0].message.tool_calls = tool_calls


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
    assert _classify_format_reason(exc, resp, text_mode=True) == "found_2_actions"


@requires_minisweagent
def test_classify_found_0_actions_from_payload():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError(n_actions=0)
    resp = _FakeResponse(content="garbage")
    assert _classify_format_reason(exc, resp, text_mode=True) == "found_0_actions"


@requires_minisweagent
def test_classify_empty_response():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError()  # no n_actions
    resp = _FakeResponse(content="   ")
    assert _classify_format_reason(exc, resp, text_mode=True) == "empty_response"


@requires_minisweagent
def test_classify_empty_response_tool_mode():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError()
    resp = _FakeResponse(content="", tool_calls=[])
    assert _classify_format_reason(exc, resp, text_mode=False) == "found_0_actions"


@requires_minisweagent
def test_classify_found_2_actions_tool_mode():
    from budgetflow.adapter.mini_swe_proxy import _classify_format_reason
    exc = _FakeFormatError()
    tc1 = MagicMock()
    tc2 = MagicMock()
    resp = _FakeResponse(content="", tool_calls=[tc1, tc2])
    assert _classify_format_reason(exc, resp, text_mode=False) == "found_2_actions"


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
            "protocol_retry_reason": "empty_response",
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
    assert result["found_0_actions"] == 0


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
                    "protocol_retry_reason": "empty_response",
                    "protocol_retry_attempts": 1,
                },
            ],
        },
    ]

    result = _parser_abort_breakdown(records)
    assert result["retry_success"] == 1
    assert result["retry_failed"] == 1
    assert result["empty_response"] == 1


def test_parser_abort_breakdown_empty():
    from budgetflow.run_observability.audit import _parser_abort_breakdown

    result = _parser_abort_breakdown([])
    assert result["found_0_actions"] == 0
    assert result["found_2_actions"] == 0
    assert result["empty_response"] == 0
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
def test_format_error_stop_after_found_0_or_empty():
    from budgetflow.adapter.action_parsing import format_error_stop_after

    assert format_error_stop_after(error_reason="found_0_actions") == 3
    assert format_error_stop_after(error_reason="empty_response") == 3


@requires_minisweagent
def test_parse_actions_empty_response_uses_current_reason_limit():
    """First empty response must use the empty-response limit, not stale default."""
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
    from budgetflow.adapter.errors import BudgetFlowStagnationError

    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.step_index = 7
    model.format_error_template = "{{ error }}"
    model._format_error_streak = 2
    model._protocol_retry_reason = ""
    model._protocol_retry_limit = 4

    resp = _FakeResponse(content="")
    try:
        model._parse_actions(resp, text_mode=True, backend_tier=3)
        assert False, "third consecutive empty response should stop"
    except BudgetFlowStagnationError:
        pass

    assert model._protocol_retry_reason == "empty_response"
    assert model._protocol_retry_limit == 3


@requires_minisweagent
def test_parse_actions_found_2_actions_uses_current_reason_limit():
    """found_2_actions stays more lenient than empty_response."""
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel
    from budgetflow.adapter.errors import BudgetFlowStagnationError
    from minisweagent.exceptions import FormatError

    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.step_index = 8
    model.format_error_template = "{{ error }}"
    model._format_error_streak = 2
    model._protocol_retry_reason = "empty_response"
    model._protocol_retry_limit = 3

    resp = _FakeResponse(content="```bash\ncmd1\n```\n```bash\ncmd2\n```")
    try:
        model._parse_actions(resp, text_mode=True, backend_tier=3)
    except BudgetFlowStagnationError:
        assert False, "found_2_actions should not stop at empty-response limit"
    except FormatError:
        pass
    else:
        assert False, "FormatError should propagate before found_2_actions reaches limit"

    assert model._protocol_retry_reason == "found_2_actions"
    assert model._protocol_retry_limit == 4
    assert model._format_error_streak == 3
z
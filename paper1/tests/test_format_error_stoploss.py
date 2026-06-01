from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "external" / "mini-swe-agent" / "src"))

import pytest  # noqa: E402

from budgetflow.adapter.mini_swe_proxy import (  # noqa: E402
    FORMAT_ERROR_STOP_AFTER,
    BudgetFlowLitellmModel,
)
from budgetflow.adapter.errors import BudgetFlowStagnationError  # noqa: E402
from minisweagent.exceptions import FormatError  # noqa: E402


def _model() -> BudgetFlowLitellmModel:
    model = object.__new__(BudgetFlowLitellmModel)
    model.workflow_id = "wf"
    model.format_error_template = "{{ error }}"
    model.step_index = 0
    model._format_error_streak = 0
    return model


def _response(tool_calls=None):
    message = SimpleNamespace(tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def test_missing_tool_calls_fail_fast_after_threshold() -> None:
    model = _model()

    for step in range(1, FORMAT_ERROR_STOP_AFTER):
        model.step_index = step
        with pytest.raises(FormatError):
            model._parse_actions(_response())

    model.step_index = FORMAT_ERROR_STOP_AFTER
    with pytest.raises(BudgetFlowStagnationError) as excinfo:
        model._parse_actions(_response())

    assert excinfo.value.exit_reason == "format_error_no_tool_calls"


def test_valid_tool_call_resets_format_error_streak() -> None:
    model = _model()
    model._format_error_streak = 3
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="bash", arguments='{"command":"ls"}'),
    )

    actions = model._parse_actions(_response([tool_call]))

    assert actions == [{"command": "ls", "tool_call_id": "call_1"}]


def test_text_mode_parses_bash_block() -> None:
    model = _model()
    response = _response()
    response.choices[0].message.content = "THOUGHT: list files\n\n```mswea_bash_command\nls -la\n```"

    actions = model._parse_actions(response, text_mode=True)

    assert actions == [{"command": "ls -la"}]
    assert model._format_error_streak == 0


def test_text_mode_format_error_stops_after_threshold() -> None:
    model = _model()
    response = _response()
    response.choices[0].message.content = "THOUGHT: no command"

    for step in range(1, FORMAT_ERROR_STOP_AFTER):
        model.step_index = step
        with pytest.raises(FormatError):
            model._parse_actions(response, text_mode=True)

    model.step_index = FORMAT_ERROR_STOP_AFTER
    with pytest.raises(BudgetFlowStagnationError) as excinfo:
        model._parse_actions(response, text_mode=True)

    assert excinfo.value.exit_reason == "format_error_text_action"

"""Tests for text-mode command parsing.

Covers:
  - ```bash (GPT-5.4 actual output)
  - ```sh variant
  - JSON {"command": "..."} fallback
  - [bash] {"command": "..."} variant
  - prose-only → no match
  - T1/T2/T3 share one text_regex action contract
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.adapter.action_parsing import (
    TEXT_ACTION_REGEX,
    try_extract_json_command,
)


# ── Regex tests ────────────────────────────────────────────────────────


def test_regex_matches_bash_fenced_block() -> None:
    content = """THOUGHT: inspect\n```bash
cd /tmp && python - <<'PY'
print('hello')
PY
```"""
    matches = re.findall(TEXT_ACTION_REGEX, content, re.DOTALL)
    assert len(matches) == 1
    assert "cd /tmp" in matches[0]


def test_regex_matches_sh_fenced_block() -> None:
    content = "```sh\ncd /tmp\n```"
    matches = re.findall(TEXT_ACTION_REGEX, content, re.DOTALL)
    assert len(matches) == 1
    assert matches[0].strip() == "cd /tmp"


def test_regex_extracts_bash_block_after_thought_text() -> None:
    content = "THOUGHT: inspect before editing.```bash\ncd /work/repo && python -m pytest tests/test_x.py\n```"
    matches = re.findall(TEXT_ACTION_REGEX, content, re.DOTALL)
    assert len(matches) == 1
    assert "python" in matches[0]


def test_regex_rejects_prose_only() -> None:
    content = "THOUGHT: I need to inspect the relevant latex printer code and reproduce the issue before editing."
    matches = re.findall(TEXT_ACTION_REGEX, content, re.DOTALL)
    assert len(matches) == 0


def test_regex_only_one_match_per_block() -> None:
    """Single bash block → exactly 1 match."""
    content = "before\n```bash\ncd /tmp\n```\nafter"
    matches = re.findall(TEXT_ACTION_REGEX, content, re.DOTALL)
    assert len(matches) == 1


def test_regex_handles_windows_newlines() -> None:
    content = "```bash\r\ncd /tmp\r\n```"
    matches = re.findall(TEXT_ACTION_REGEX, content, re.DOTALL)
    assert len(matches) == 1


# ── JSON fallback tests ────────────────────────────────────────────────


def test_json_extract_simple() -> None:
    content = 'THOUGHT: test\n{"command":"cd /tmp && ls"}'
    cmd = try_extract_json_command(content)
    assert cmd == "cd /tmp && ls"


def test_json_extract_with_escaped_newlines() -> None:
    content = '{"command":"cd /tmp && python -c \\"print(1)\\""}'
    cmd = try_extract_json_command(content)
    assert cmd is not None
    assert "cd /tmp" in cmd


def test_json_extract_with_bash_prefix() -> None:
    content = 'THOUGHT: inspect\n[bash] {"command":"cd /tmp && ls"}'
    cmd = try_extract_json_command(content)
    assert cmd == "cd /tmp && ls"


def test_json_extract_after_thought_text() -> None:
    content = """THOUGHT: inspect before editing.{"command":"cd /work/repo && python -m pytest tests/test_x.py"}"""
    cmd = try_extract_json_command(content)
    assert cmd is not None
    assert "python" in cmd


def test_json_extract_picks_first_valid() -> None:
    content = '{"command":"first"}\n{"command":"second"}'
    cmd = try_extract_json_command(content)
    assert cmd == "first"


def test_json_extract_returns_none_for_prose_only() -> None:
    content = "THOUGHT: I need to inspect the code."
    cmd = try_extract_json_command(content)
    assert cmd is None


def test_json_extract_skips_invalid_json() -> None:
    content = '{"command":"unclosed'
    cmd = try_extract_json_command(content)
    assert cmd is None


# ── Integration: parse_regex_actions unchanged ─────────────────────────


def test_parse_regex_actions_still_works_with_new_regex() -> None:
    """parse_regex_actions from mini-swe-agent still enforces exactly-1-match."""
    from minisweagent.models.utils.actions_text import parse_regex_actions
    from minisweagent.exceptions import FormatError

    # Valid: one match
    content = "```bash\ncd /tmp\n```"
    actions = parse_regex_actions(content, action_regex=TEXT_ACTION_REGEX,
                                  format_error_template="{{ error }}")
    assert len(actions) == 1
    assert actions[0]["command"] == "cd /tmp"

    # Invalid: zero matches
    try:
        parse_regex_actions("no command here", action_regex=TEXT_ACTION_REGEX,
                            format_error_template="{{ error }}")
        assert False, "should have raised FormatError"
    except FormatError:
        pass

    # Invalid: two matches
    try:
        parse_regex_actions("```bash\ncmd1\n```\n```bash\ncmd2\n```",
                            action_regex=TEXT_ACTION_REGEX,
                            format_error_template="{{ error }}")
        assert False, "should have raised FormatError"
    except FormatError:
        pass


# ── Protocol safety: routed tiers share one action contract ────────────


def test_t1_uses_text_regex_protocol() -> None:
    """T1 uses the same text_regex contract as routed stronger tiers."""
    from budgetflow.adapter.protocol_adapter import ActionProtocolAdapter
    from budgetflow.defaults import TIER1_BACKEND

    decision = ActionProtocolAdapter.resolve(TIER1_BACKEND)
    assert decision.protocol == "text_regex"
    assert decision.parser == "parse_regex_actions"


def test_t2_uses_text_regex_protocol() -> None:
    """T2 uses the same text_regex contract as routed stronger tiers."""
    from budgetflow.adapter.protocol_adapter import ActionProtocolAdapter
    from budgetflow.defaults import TIER2_BACKEND

    decision = ActionProtocolAdapter.resolve(TIER2_BACKEND)
    assert decision.protocol == "text_regex"
    assert decision.parser == "parse_regex_actions"


def test_t3_stays_text_regex() -> None:
    """T3 (GPT-5.4) remains text_regex (parser regex broadened, not protocol)."""
    from budgetflow.adapter.protocol_adapter import ActionProtocolAdapter
    from budgetflow.defaults import TIER3_BACKEND

    decision = ActionProtocolAdapter.resolve(TIER3_BACKEND)
    assert decision.protocol == "text_regex"
    assert decision.parser == "parse_regex_actions"


# ── Trace evidence: parser failure records required fields ─────────────


def test_parser_failure_trace_has_required_fields() -> None:
    """Simulate a trace row after parser failure — verify field presence."""
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
        protocol="text_regex",
        parser="parse_regex_actions",
        parser_input_snippet="THOUGHT: test\n```bash\ncd /tmp\n```",
        assistant_content_head="THOUGHT: test",
        parser_error_type="FormatError",
        parser_error_message="Expected exactly 1 action, found 0.",
    )
    assert trace["parser_input_snippet"] is not None
    assert trace["assistant_content_head"] is not None
    assert trace["parser_error_type"] == "FormatError"
    assert "parser_error_message" in trace
    assert trace["protocol"] == "text_regex"

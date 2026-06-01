from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.adapter.message_utils import extract_bash_context, extract_text_bash_command  # noqa: E402


def test_extract_text_bash_command_single_block() -> None:
    content = "THOUGHT: inspect\n\n```mswea_bash_command\nls -la\n```"

    assert extract_text_bash_command(content) == "ls -la"


def test_extract_text_bash_command_rejects_multiple_blocks() -> None:
    content = "```mswea_bash_command\nls\n```\n```mswea_bash_command\npwd\n```"

    assert extract_text_bash_command(content) is None


def test_extract_bash_context_from_text_mode_messages() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "THOUGHT: inspect\n\n```mswea_bash_command\nls -la\n```",
        },
        {
            "role": "user",
            "content": "<returncode>0</returncode>\n<output>\nok\n</output>",
        },
    ]

    command, observation = extract_bash_context(messages)

    assert command == "ls -la"
    assert observation is not None
    assert "<returncode>0</returncode>" in observation

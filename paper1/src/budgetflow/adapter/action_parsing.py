from __future__ import annotations

import json
import re

from minisweagent.exceptions import FormatError
from minisweagent.models.utils.actions_text import parse_regex_actions
from minisweagent.models.utils.actions_toolcall import parse_toolcall_actions


FORMAT_ERROR_STOP_AFTER = 5

# Canonical regex for text-mode bash command extraction.
# Matches: ```mswea_bash_command, ```bash, ```sh
TEXT_ACTION_REGEX = r"```(?:mswea_bash_command|bash|sh)\s*\n(.*?)\n```"


def format_error_stop_after(backend_tier: int | None) -> int:  # noqa: ARG001
    return FORMAT_ERROR_STOP_AFTER


def try_extract_json_command(content: str) -> str | None:
    """Extract a bash command from JSON emitted by text-mode models."""
    for match in re.finditer(r'\{"command"\s*:\s*"((?:[^"\\]|\\.)*)"\}', content):
        try:
            return json.loads(match.group(0))["command"]
        except (json.JSONDecodeError, KeyError):
            continue
    for match in re.finditer(r'\[bash\]\s*\{[^}]*"command"\s*:\s*"((?:[^"\\]|\\.)*)"[^}]*\}', content):
        try:
            inner = re.search(r'\{[^}]*"command"\s*:\s*"((?:[^"\\]|\\.)*)"[^}]*\}', match.group(0))
            if inner:
                return json.loads(inner.group(0))["command"]
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def parse_text_actions(content: str, *, format_error_template: str) -> list[dict]:
    """Parse text-mode bash actions, including JSON command fallback."""
    try:
        return parse_regex_actions(
            content,
            action_regex=TEXT_ACTION_REGEX,
            format_error_template=format_error_template,
        )
    except FormatError:
        command = try_extract_json_command(content)
        if command is not None:
            return [{"command": command}]
        raise


def parse_tool_actions(tool_calls, *, format_error_template: str) -> list[dict]:
    return parse_toolcall_actions(tool_calls, format_error_template=format_error_template)

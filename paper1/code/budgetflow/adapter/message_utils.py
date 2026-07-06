from __future__ import annotations

import json
import re


def estimate_input_tokens(messages: list[dict]) -> int:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.append(json.dumps(content))
        tool_calls = message.get("tool_calls") or []
        for call in tool_calls:
            fn = call.get("function") or {}
            parts.append(fn.get("name") or "")
            parts.append(fn.get("arguments") or "")
    text = "\n".join(parts)
    return max(64, len(text.split()) * 4 // 3)


def extract_bash_context(messages: list[dict]) -> tuple[str | None, str | None]:
    last_command: str | None = None
    last_observation: str | None = None

    for message in reversed(messages):
        role = message.get("role")
        if role == "tool" and last_observation is None:
            last_observation = _stringify_content(message.get("content"))
            continue
        if role == "user" and last_observation is None and "<returncode>" in _stringify_content(message.get("content")):
            last_observation = _stringify_content(message.get("content"))
            continue
        if role == "assistant" and last_command is None:
            for call in message.get("tool_calls") or []:
                fn = call.get("function") or {}
                if fn.get("name") != "bash":
                    continue
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                command = args.get("command")
                if isinstance(command, str) and command.strip():
                    last_command = command.strip()
                    break
            if last_command is None:
                command = extract_text_bash_command(message.get("content") or "")
                if command:
                    last_command = command
        if last_command and last_observation:
            break
    return last_command, last_observation


def _stringify_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return json.dumps(content)
    return str(content or "")


def extract_text_bash_command(content: str) -> str | None:
    """Extract one mini-SWE text-mode bash block."""
    matches = re.findall(r"```mswea_bash_command\s*\n(.*?)\n```", content, re.DOTALL)
    if len(matches) != 1:
        return None
    command = matches[0].strip()
    return command or None

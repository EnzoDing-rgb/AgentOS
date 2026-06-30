from __future__ import annotations

from typing import Any


def format_retry_assistant_message(response: Any) -> dict[str, Any]:
    """Build an OpenAI-valid assistant message for protocol retry history.

    The failed response was not executed, so any tool calls in that response
    must not be replayed. Provider-side fields such as reasoning_content are
    preserved because thinking-mode providers may require them in subsequent
    history.
    """
    raw = response.choices[0].message.model_dump()
    message = {
        k: v
        for k, v in raw.items()
        if k not in {"extra", "tool_calls"} and v is not None
    }
    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        content = "The previous response contained invalid tool calls and was not executed."
    message["role"] = "assistant"
    message["content"] = content
    return message


def prepare_provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip local bookkeeping while preserving provider-required history."""
    prepared: list[dict[str, Any]] = []
    for msg in messages:
        clean = {k: v for k, v in msg.items() if k != "extra" and v is not None}
        prepared.append(clean)
    assert_provider_tool_sequence(prepared)
    return prepared


def assert_provider_tool_sequence(messages: list[dict[str, Any]]) -> None:
    """Validate OpenAI-style assistant tool_call / tool result adjacency."""
    pending_tool_call_ids: list[str] = []
    for index, msg in enumerate(messages):
        role = msg.get("role")
        if pending_tool_call_ids:
            if role != "tool":
                raise ValueError(
                    "provider message history has assistant tool_calls without "
                    f"matching tool messages before message {index}"
                )
            if str(msg.get("tool_call_id") or "") not in pending_tool_call_ids:
                raise ValueError(
                    "provider message history has a tool message with an "
                    f"unexpected tool_call_id before message {index}"
                )
            pending_tool_call_ids.remove(str(msg.get("tool_call_id")))
            continue

        if role == "tool":
            raise ValueError(
                "provider message history has a tool message without a preceding "
                f"assistant tool_call before message {index}"
            )

        if role == "assistant":
            pending_tool_call_ids = _tool_call_ids(msg.get("tool_calls"))

    if pending_tool_call_ids:
        raise ValueError("provider message history ends with unpaired assistant tool_calls")


def _tool_call_ids(tool_calls: object) -> list[str]:
    ids: list[str] = []
    if not isinstance(tool_calls, list):
        return ids
    for call in tool_calls:
        call_id = getattr(call, "id", None)
        if call_id is None and isinstance(call, dict):
            call_id = call.get("id")
        if call_id:
            ids.append(str(call_id))
    return ids

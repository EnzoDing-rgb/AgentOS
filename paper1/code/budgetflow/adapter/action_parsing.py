from __future__ import annotations

from minisweagent.models.utils.actions_toolcall import parse_toolcall_actions


# Per-reason format error stop thresholds (consecutive errors before abort).
# Native tool-call parsing currently emits found_0/found_2/invalid reasons.
_FORMAT_ERROR_STOP = {
    "found_2_actions": 4,
    "found_0_actions": 3,
    "invalid_tool_call": 3,
}
_FORMAT_ERROR_STOP_DEFAULT = 4

def format_error_stop_after(
    backend_tier: int | None = None,  # noqa: ARG001
    error_reason: str = "",
) -> int:
    if error_reason:
        for key, limit in _FORMAT_ERROR_STOP.items():
            if key in error_reason:
                return limit
    return _FORMAT_ERROR_STOP_DEFAULT


def parse_tool_actions(tool_calls, *, format_error_template: str) -> list[dict]:
    return parse_toolcall_actions(tool_calls, format_error_template=format_error_template)

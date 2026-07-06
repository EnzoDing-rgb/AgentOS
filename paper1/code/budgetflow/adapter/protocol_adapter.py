"""ActionProtocolAdapter — canonical tool-call action contract.

All active BudgetFlow runs use native tool calls.  Text-regex parsing is
historical evidence only; it is not an active runtime path.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class ProtocolDecision:
    """Record of which protocol/parser was selected for a turn."""
    backend_name: str
    protocol: str = "tool_call"
    parser: str = "parse_toolcall_actions"
    reason: str = "canonical_tool_call"


class ActionProtocolAdapter:
    """Resolve protocol mode for a backend and record the decision."""

    @staticmethod
    def resolve(backend_name: str) -> ProtocolDecision:
        """Return the canonical protocol decision for *backend_name*."""
        return ProtocolDecision(backend_name=backend_name)

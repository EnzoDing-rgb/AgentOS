"""ActionProtocolAdapter — protocol-aware parser dispatch.

Each model declares its action protocol mode.  The adapter selects the parser
based on that declaration and records the decision for trace observability.

Protocol modes:
  - tool_call: model returns native tool-call blocks (parse_toolcall_actions)
  - text_regex: model returns fenced text commands (parse_regex_actions)
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model_tiers import protocol_for


@dataclass(frozen=True)
class ProtocolDecision:
    """Record of which protocol/parser was selected for a turn."""
    backend_name: str
    protocol: str  # "tool_call" | "text_regex"
    parser: str     # "parse_toolcall_actions" | "parse_regex_actions"
    reason: str     # "tier_config" | "env_override" | "fallback"


class ActionProtocolAdapter:
    """Resolve protocol mode for a backend and record the decision."""

    @staticmethod
    def resolve(backend_name: str) -> ProtocolDecision:
        """Return the protocol decision for *backend_name*.

        Declaration order:
        1. TierConfig.text_mode flag
        2. BF_GPT_TEXT_MODE env var (global override)
        3. Default: tool_call
        """
        import os

        declared = protocol_for(backend_name)
        env_override = os.environ.get("BF_GPT_TEXT_MODE") == "1"

        if env_override:
            return ProtocolDecision(
                backend_name=backend_name,
                protocol="text_regex",
                parser="parse_regex_actions",
                reason="env_override",
            )

        if declared == "text_regex":
            return ProtocolDecision(
                backend_name=backend_name,
                protocol="text_regex",
                parser="parse_regex_actions",
                reason="tier_config",
            )

        return ProtocolDecision(
            backend_name=backend_name,
            protocol="tool_call",
            parser="parse_toolcall_actions",
            reason="tier_config",
        )

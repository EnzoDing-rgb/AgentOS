from __future__ import annotations

from ..defaults import TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND
from ..types import Backend

# rpm_limit / concurrency_limit kept on Backend for Tier-2 paper metrics only; governor does not enforce them.
_UNLIMITED = 0


def build_compare_backends() -> list[Backend]:
    """Three-tier pool: codex-spark (T1) < gpt-5.4-mini (T2) < gpt-5.3-codex (T3).

    Costs are governor mock units (not USD). Ratio ~ 1 : 2.5 : 6.
    """
    return [
        Backend(
            name=TIER1_BACKEND,
            tier=1,
            cost_per_input_token=0.0010,
            cost_per_output_token=0.0020,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=256,
            progress_score=0.11,
            latency_ms=300,
        ),
        Backend(
            name=TIER2_BACKEND,
            tier=2,
            cost_per_input_token=0.0025,
            cost_per_output_token=0.0050,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=384,
            progress_score=0.14,
            latency_ms=500,
        ),
        Backend(
            name=TIER3_BACKEND,
            tier=3,
            cost_per_input_token=0.0060,
            cost_per_output_token=0.0120,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=512,
            progress_score=0.18,
            latency_ms=700,
        ),
    ]


def build_deepseek_backends() -> list[Backend]:
    """Backward-compatible alias."""
    return build_compare_backends()

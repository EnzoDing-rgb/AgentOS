from __future__ import annotations

from ..types import Backend

# rpm_limit / concurrency_limit kept on Backend for Tier-2 paper metrics only; governor does not enforce them.
_UNLIMITED = 0


def build_deepseek_backends() -> list[Backend]:
    """Mock-scale governor units for routing (not exact API USD). Budget is enforced by Governor."""
    return [
        Backend(
            name="deepseek_flash",
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
            name="deepseek_pro",
            tier=2,
            cost_per_input_token=0.0028,
            cost_per_output_token=0.0056,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=512,
            progress_score=0.16,
            latency_ms=600,
        ),
    ]

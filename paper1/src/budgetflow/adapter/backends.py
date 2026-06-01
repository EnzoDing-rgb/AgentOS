from __future__ import annotations

from ..defaults import TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND
from ..types import Backend

# rpm_limit / concurrency_limit kept on Backend for Tier-2 paper metrics only; governor does not enforce them.
_UNLIMITED = 0


def build_compare_backends() -> list[Backend]:
    """Three-tier Qwen pool via 阿里云百炼.

    Costs are governor units scaled from ¥ pricing (per 1M tokens):
      T1 (qwen3.5-flash): ¥0.2/M in, ¥0.8/M out
      T2 (qwen3.6-flash): ¥1.2/M in, ¥7.2/M out
      T3 (qwen3.6-plus):  ¥2.0/M in, ¥12/M out
    Ratio T1:T2:T3 ≈ 1:6:10 (in), 1:9:15 (out).
    Huge T1→T2 gap makes T1 the default, T2/T3 for important stages.
    """
    return [
        Backend(
            name=TIER1_BACKEND,
            tier=1,
            cost_per_input_token=0.0002,
            cost_per_output_token=0.0008,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=512,
            progress_score=0.10,
            latency_ms=350,
        ),
        Backend(
            name=TIER2_BACKEND,
            tier=2,
            cost_per_input_token=0.0012,
            cost_per_output_token=0.0072,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=768,
            progress_score=0.14,
            latency_ms=500,
        ),
        Backend(
            name=TIER3_BACKEND,
            tier=3,
            cost_per_input_token=0.0020,
            cost_per_output_token=0.0120,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.18,
            latency_ms=700,
        ),
    ]


def build_deepseek_backends() -> list[Backend]:
    """Backward-compatible alias."""
    return build_compare_backends()

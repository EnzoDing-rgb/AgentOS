from __future__ import annotations

from ..defaults import TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND
from ..types import Backend

# rpm_limit / concurrency_limit kept on Backend for Tier-2 paper metrics only; governor does not enforce them.
_UNLIMITED = 0


def build_compare_backends() -> list[Backend]:
    """Three-tier Qwen pool via 阿里云百炼.

    Costs are governor units scaled from ¥ pricing (per 1M tokens):
      T1 (qwen3.6-flash): ¥1.2/M in, ¥7.2/M out
      T2 (qwen3.6-plus): ¥2.0/M in, ¥12/M out
      T3 (qwen3.7-max):  ¥4.0/M in, ¥16/M out
    Ratio T1:T2:T3 ≈ 1 : 1.67 : 3.33 (in), 1 : 1.67 : 2.22 (out).
    """
    return [
        Backend(
            name=TIER1_BACKEND,
            tier=1,
            cost_per_input_token=0.0012,
            cost_per_output_token=0.0072,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=512,
            progress_score=0.11,
            latency_ms=400,
        ),
        Backend(
            name=TIER2_BACKEND,
            tier=2,
            cost_per_input_token=0.0020,
            cost_per_output_token=0.0120,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=768,
            progress_score=0.14,
            latency_ms=600,
        ),
        Backend(
            name=TIER3_BACKEND,
            tier=3,
            cost_per_input_token=0.0040,
            cost_per_output_token=0.0160,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.18,
            latency_ms=900,
        ),
    ]


def build_deepseek_backends() -> list[Backend]:
    """Backward-compatible alias."""
    return build_compare_backends()

from __future__ import annotations

from ..defaults import (
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER3_BACKEND,
    TIER4_BACKEND,
    TIER4_QWEN_MAX_BACKEND,
    TIER4_GPT53_BACKEND,
    TIER5_BACKEND,
    active_t4_backend_name,
)
from ..types import Backend

# rpm_limit / concurrency_limit kept on Backend for Tier-2 paper metrics only; governor does not enforce them.
_UNLIMITED = 0


def _build_all_backends() -> list[Backend]:
    """Four-tier Qwen pool via 阿里云百炼 with coder models.

    Costs are governor units scaled from ¥ pricing (per 1M tokens):
      T1 (qwen3.5-flash):      ¥0.3/M in, ¥0.6/M out
      T2 (qwen3-coder-flash):  ¥0.5/M in, ¥2.0/M out
      T3 (qwen3.6-plus):       ¥2.0/M in, ¥6.0/M out
      T4 (qwen3-coder-plus):   ¥4.0/M in, ¥12/M out (SWE-bench 78.8%)
    T4 is code-specialized and cheap enough to use aggressively.
    """
    return [
        Backend(
            name=TIER1_BACKEND,
            tier=1,
            cost_per_input_token=0.0003,
            cost_per_output_token=0.0006,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=512,
            progress_score=0.10,
            latency_ms=350,
        ),
        Backend(
            name=TIER2_BACKEND,
            tier=2,
            cost_per_input_token=0.0005,
            cost_per_output_token=0.0020,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=768,
            progress_score=0.15,
            latency_ms=500,
        ),
        Backend(
            name=TIER3_BACKEND,
            tier=3,
            cost_per_input_token=0.0020,
            cost_per_output_token=0.0060,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.18,
            latency_ms=700,
        ),
        Backend(
            name=TIER4_BACKEND,
            tier=4,
            cost_per_input_token=0.0040,
            cost_per_output_token=0.0120,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.22,
            latency_ms=900,
        ),
        Backend(
            name=TIER4_QWEN_MAX_BACKEND,
            tier=4,
            cost_per_input_token=0.0040,
            cost_per_output_token=0.0120,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.22,
            latency_ms=950,
        ),
        Backend(
            name=TIER4_GPT53_BACKEND,
            tier=4,
            cost_per_input_token=0.0060,
            cost_per_output_token=0.0180,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.25,
            latency_ms=1200,
        ),
        Backend(
            name=TIER5_BACKEND,
            tier=5,
            cost_per_input_token=0.01,
            cost_per_output_token=0.04,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=2048,
            progress_score=0.35,
            latency_ms=2000,
        ),
    ]


def build_compare_backends(*, include_t1: bool = False) -> list[Backend]:
    """Default experiment pool: Qwen T1-T4 only.

    GPT-5.5 is a ceiling probe and must not be reachable by budgeted strategies
    unless the caller explicitly asks for the ceiling pool.
    """
    active_t4 = active_t4_backend_name()
    excluded = {TIER5_BACKEND, TIER4_BACKEND, TIER4_QWEN_MAX_BACKEND, TIER4_GPT53_BACKEND} - {active_t4}
    if not include_t1:
        excluded.add(TIER1_BACKEND)
    return [backend for backend in _build_all_backends() if backend.name not in excluded]


def build_ceiling_backends() -> list[Backend]:
    """Full pool including GPT-5.5 for explicit all_gpt55 ceiling probes."""
    return _build_all_backends()


def build_backends_for_strategy(strategy: str) -> list[Backend]:
    if strategy in {"all_gpt53", "all_gpt55"}:
        return build_ceiling_backends()
    return build_compare_backends(include_t1=strategy in {"all_flash", "all_t1"})


def build_deepseek_backends() -> list[Backend]:
    """Backward-compatible alias."""
    return build_compare_backends()

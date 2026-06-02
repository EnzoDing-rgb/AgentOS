from __future__ import annotations

from ..defaults import (
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER3_BACKEND,
)
from ..types import Backend

# rpm_limit / concurrency_limit kept on Backend for Tier-2 paper metrics only; governor does not enforce them.
_UNLIMITED = 0


def _build_all_backends() -> list[Backend]:
    """Current three-tier pool: Coder Flash, Coder Plus, GPT-5.3 Codex."""
    return [
        Backend(
            name=TIER1_BACKEND,
            tier=1,
            cost_per_input_token=0.0005,
            cost_per_output_token=0.0020,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=768,
            progress_score=0.15,
            latency_ms=500,
        ),
        Backend(
            name=TIER2_BACKEND,
            tier=2,
            cost_per_input_token=0.0040,
            cost_per_output_token=0.0120,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.22,
            latency_ms=900,
        ),
        Backend(
            name=TIER3_BACKEND,
            tier=3,
            cost_per_input_token=0.0060,
            cost_per_output_token=0.0180,
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.25,
            latency_ms=1200,
        ),
    ]


def build_compare_backends(*, include_t1: bool = False) -> list[Backend]:
    backends = _build_all_backends()
    if include_t1:
        return backends
    return [backend for backend in backends if backend.name != TIER1_BACKEND]


def build_ceiling_backends() -> list[Backend]:
    return _build_all_backends()


def build_backends_for_strategy(strategy: str) -> list[Backend]:
    return build_compare_backends(include_t1=strategy in {"all_flash", "all_t1"})


def build_deepseek_backends() -> list[Backend]:
    """Backward-compatible alias."""
    return build_compare_backends()

from __future__ import annotations

import os

from ..defaults import (
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER2_XFYUN_BACKEND,
    TIER3_BACKEND,
)
from ..types import Backend

# rpm_limit / concurrency_limit kept on Backend for Tier-2 paper metrics only; governor does not enforce them.
_UNLIMITED = 0


def _build_all_backends() -> list[Backend]:
    """Current three-tier BudgetFlow pool.

    Token pricing calibrated to real API costs (2026-06):
      - T1 (qwen3-coder-flash):  DashScope ¥0.0004/1K in, ¥0.002/1K out
      - T2 (qwen3-coder-plus):  DashScope ¥0.004/1K in,  ¥0.016/1K out
      - T3 (GPT-5.4):           aicode007 ~$2.50/1M in,  ~$15.00/1M out
    USD conversion at CNY/USD ≈ 7.25.
    """
    _R = 1.0 / 7.25  # CNY→USD
    return [
        Backend(
            name=TIER1_BACKEND,
            tier=1,
            cost_per_input_token=0.0004 / 1000 * _R,   # ¥0.0004/1K → $/token
            cost_per_output_token=0.002 / 1000 * _R,    # ¥0.002/1K → $/token
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=768,
            progress_score=0.15,
            latency_ms=500,
        ),
        Backend(
            name=TIER2_BACKEND,
            tier=2,
            cost_per_input_token=0.004 / 1000 * _R,    # ¥0.004/1K → $/token
            cost_per_output_token=0.016 / 1000 * _R,    # ¥0.016/1K → $/token
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.22,
            latency_ms=900,
        ),
        Backend(
            name=TIER3_BACKEND,
            tier=3,
            cost_per_input_token=2.50 / 1_000_000,     # $2.50/1M → $/token
            cost_per_output_token=15.00 / 1_000_000,    # $15.00/1M → $/token
            rpm_limit=_UNLIMITED,
            concurrency_limit=_UNLIMITED,
            mean_output_tokens=1024,
            progress_score=0.25,
            latency_ms=1200,
        ),
    ]


def _alternative_backends() -> dict[str, Backend]:
    """Optional provider alternatives keyed by stable backend name.

    Keep alternatives out of _build_all_backends() so the paper's canonical
    three-tier pool stays stable. Selection replaces a tier, it does not add a
    fourth active tier unless a future strategy explicitly asks for that.
    """
    _R = 1.0 / 7.25
    return {
        TIER2_XFYUN_BACKEND: Backend(
            name=TIER2_XFYUN_BACKEND,
            tier=2,
            # Limited-free MaaS backend: use qwen-coder-plus pricing as a
            # conservative accounting proxy so smoke tests do not distort caps.
            cost_per_input_token=0.004 / 1000 * _R,
            cost_per_output_token=0.016 / 1000 * _R,
            rpm_limit=300,
            concurrency_limit=5,
            mean_output_tokens=1024,
            progress_score=0.22,
            latency_ms=900,
        )
    }


def _selected_t2_backend() -> str:
    choice = os.environ.get("BUDGETFLOW_T2_BACKEND", "").strip().lower()
    if choice in {"xfyun", "xfyun_qwen36", "qwen36", TIER2_XFYUN_BACKEND}:
        return TIER2_XFYUN_BACKEND
    return TIER2_BACKEND


def build_compare_backends(*, include_t1: bool = False) -> list[Backend]:
    backends = _build_all_backends()
    selected_t2 = _selected_t2_backend()
    if selected_t2 != TIER2_BACKEND:
        alternatives = _alternative_backends()
        replacement = alternatives[selected_t2]
        backends = [replacement if backend.name == TIER2_BACKEND else backend for backend in backends]
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

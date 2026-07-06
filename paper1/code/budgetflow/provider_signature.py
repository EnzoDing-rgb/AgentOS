from __future__ import annotations

import time
from dataclasses import dataclass

import litellm

from .model_tiers import MODEL_CATALOG, load_env_file


@dataclass(frozen=True)
class ProviderSignatureResult:
    backend: str
    model: str
    provider: str
    ok: bool
    status_code: int | None
    error_type: str | None
    error_sample: str
    latency_ms: int


def _kwargs_for(backend: str) -> dict:
    _, kwargs = MODEL_CATALOG.litellm_kwargs(backend, max_tokens=8)
    return kwargs


def check_backend_signature(backend: str) -> ProviderSignatureResult:
    load_env_file()
    config = MODEL_CATALOG.require_config(backend)
    model = config.model
    provider = config.provider
    started = time.time()
    try:
        litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "Return exactly: OK"}],
            **_kwargs_for(backend),
        )
        return ProviderSignatureResult(
            backend=backend,
            model=model,
            provider=provider,
            ok=True,
            status_code=None,
            error_type=None,
            error_sample="",
            latency_ms=int((time.time() - started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderSignatureResult(
            backend=backend,
            model=model,
            provider=provider,
            ok=False,
            status_code=getattr(exc, "status_code", None),
            error_type=type(exc).__name__,
            error_sample=str(exc)[:300],
            latency_ms=int((time.time() - started) * 1000),
        )


def check_required_signatures(backends: list[str]) -> list[ProviderSignatureResult]:
    seen: set[str] = set()
    results: list[ProviderSignatureResult] = []
    for backend in backends:
        if backend in seen:
            continue
        seen.add(backend)
        results.append(check_backend_signature(backend))
    return results

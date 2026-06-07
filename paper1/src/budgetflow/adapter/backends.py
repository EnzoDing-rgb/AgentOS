from __future__ import annotations

from ..defaults import MODEL_CATALOG, TIER1_BACKEND
from ..types import Backend


def build_compare_backends(*, include_t1: bool = False) -> list[Backend]:
    backends = MODEL_CATALOG.backends()
    if include_t1:
        return backends
    return [backend for backend in backends if backend.name != TIER1_BACKEND]


def build_ceiling_backends() -> list[Backend]:
    return MODEL_CATALOG.backends()


def build_backends_for_strategy(strategy: str) -> list[Backend]:
    return build_compare_backends(include_t1=strategy in {"all_flash", "all_t1"})

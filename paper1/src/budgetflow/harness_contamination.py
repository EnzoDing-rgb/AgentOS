from __future__ import annotations


HOST_DEPENDENCY_CONTAMINATION_MARKERS = (
    "numpy.dtype size changed",
    "_ARRAY_API not found",
    "opik/evaluation/metrics",
    "site-packages/tensorflow",
    "site-packages/keras",
    "site-packages/pandas",
)


def has_host_dependency_contamination(detail: str) -> bool:
    return any(marker in detail for marker in HOST_DEPENDENCY_CONTAMINATION_MARKERS)

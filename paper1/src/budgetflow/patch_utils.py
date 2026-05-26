from __future__ import annotations

import re

from swebench.harness.utils import extract_minimal_patch
from swebench.inference.make_datasets.utils import extract_diff


def normalize_model_patch(response_text: str) -> str | None:
    if not response_text or not response_text.strip():
        return None
    raw = extract_diff(response_text)
    if not raw or not raw.strip():
        return None
    patch = extract_minimal_patch(raw).strip()
    if not patch:
        return None
    if "diff --git" not in patch and "--- a/" not in patch:
        return None
    return patch

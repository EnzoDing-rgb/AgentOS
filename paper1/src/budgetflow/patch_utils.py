from __future__ import annotations

import re

from swebench.harness.utils import extract_minimal_patch
from swebench.inference.make_datasets.utils import extract_diff


def validate_patch_structure(patch_text: str) -> str | None:
    if not patch_text.strip():
        return "empty patch"
    if "diff --git" not in patch_text and "--- a/" not in patch_text and "+++ b/" not in patch_text:
        return "missing file headers"
    lines = patch_text.splitlines()
    if lines and lines[-1].startswith(("diff --git ", "--- a/", "+++ b/")):
        return "patch appears truncated"
    last_line = lines[-1] if lines else ""
    if re.fullmatch(r"[+\- ]?[A-Za-z_][A-Za-z0-9_]*\s*=\s*$", last_line):
        return "patch appears truncated"
    return None


def normalize_model_patch(response_text: str) -> str | None:
    patch, _error = normalize_model_patch_with_error(response_text)
    return patch


def normalize_model_patch_with_error(response_text: str) -> tuple[str | None, str | None]:
    if not response_text or not response_text.strip():
        return None, "empty model response"
    raw = extract_diff(response_text)
    if not raw or not raw.strip():
        return None, "no diff block found in model response"
    patch = extract_minimal_patch(raw).strip()
    if not patch:
        return None, "empty diff after normalization"
    error = validate_patch_structure(patch)
    if error is not None:
        return None, error
    return patch, None

from __future__ import annotations

from typing import Any


_INFRA_STATUSES = {
    "BadRequestError",
    "APIError",
    "RateLimitError",
    "AuthenticationError",
    "PermissionDeniedError",
}

_BUDGET_REASONS = {
    "budget_exhausted",
    "cap_exhausted",
    "reserve_failed_budget",
}


def classify_failure(record: dict[str, Any]) -> str:
    """Coarse failure class for experiment diagnosis.

    This is intentionally record-only: no oracle, no task-specific knowledge.
    """
    if record.get("harness_resolved"):
        return "pass"

    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    if status in _INFRA_STATUSES or "error" in status.lower():
        return "infra_fail"

    if reason in _BUDGET_REASONS or "budget" in reason.lower() or "cap" in reason.lower():
        if record.get("patch_extracted") or record.get("agent_gold_edited"):
            return "budget_fail"

    if not record.get("patch_extracted"):
        return "extract_fail"

    if not record.get("agent_gold_edited"):
        return "loc_fail"

    return "repair_fail"

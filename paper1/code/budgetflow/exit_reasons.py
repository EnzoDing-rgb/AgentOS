"""Shared runtime-exit predicates for scoring and calibration."""

from __future__ import annotations

import re
from typing import Any


BUDGET_EXIT_REASONS = frozenset({
    "budget_exhausted",
    "cap_exhausted",
    "overrun_guard",
    "reserve_failed_budget",
    "task_budget_exhausted",
    "task_budget_settlement_overrun",
})

BUDGET_EXIT_STATUSES = frozenset({
    "BudgetFlowBudgetError",
})

_FIXED_TIER_TURN_CAP = re.compile(r"^tier\d+_turn_cap$")


def is_fixed_tier_turn_cap_reason(reason: object) -> bool:
    return bool(_FIXED_TIER_TURN_CAP.match(str(reason or "")))


def is_fixed_tier_turn_cap_record(record: dict[str, Any]) -> bool:
    return any(
        is_fixed_tier_turn_cap_reason(record.get(field))
        for field in ("exit_reason", "agent_exit_reason")
    )


def is_budget_exit(status: object, reason: object) -> bool:
    """Return True only for actual budget-reservation exhaustion.

    Fixed-tier turn caps are runtime truncation. They contain the word "cap",
    but they are not spend floors and must not enter budget or ModelFit
    calibration as censored budget-exhausted evidence.
    """

    if is_fixed_tier_turn_cap_reason(reason):
        return False
    status_s = str(status or "")
    reason_s = str(reason or "")
    return status_s in BUDGET_EXIT_STATUSES or reason_s in BUDGET_EXIT_REASONS


def record_is_budget_exhausted(record: dict[str, Any]) -> bool:
    if is_fixed_tier_turn_cap_record(record):
        return False
    if record.get("budget_exhausted") is True:
        return True
    if str(record.get("exit_owner") or "") == "budget_exhausted":
        return True
    if str(record.get("abort_owner") or "") == "budget_exhausted":
        return True
    return (
        is_budget_exit(record.get("exit_status"), record.get("exit_reason"))
        or is_budget_exit(record.get("agent_exit_status"), record.get("agent_exit_reason"))
    )

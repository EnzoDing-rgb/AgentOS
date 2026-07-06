"""Standard metric-dict builder and legacy alias mapping for BudgetFlow reporting.

This module does NOT modify historical JSONL or runtime record schemas.
It provides a single place where reporting, summary, and observability code
can build standard North Star metric dicts from strategy-level aggregates.

Old field names (yield_score, yield_per_dollar, etc.) remain as aliases
for backward compatibility with existing data and tests, but new report
output MUST use the North Star field names.
"""

from __future__ import annotations

# -- Field name constants (North Star v1) ----------------------------------

FIELD_RESOLVED_COUNT = "resolved_count"
FIELD_RESOLVED_RATE = "resolved_rate"
FIELD_TOTAL_SPEND = "total_spend"
FIELD_COST_PER_RESOLVED_TASK = "cost_per_resolved_task"
FIELD_TOTAL_RESOLVED_VALUE = "total_resolved_value"
FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR = "total_resolved_value_per_dollar"

# Legacy aliases — read these from existing data but don't write them into
# new report output.  No code should delete or rename these in historical
# JSONL / artifact / record schemas.
LEGACY_YIELD_SCORE = "yield_score"
LEGACY_YIELD_COVERAGE = "yield_coverage"
LEGACY_YIELD_PER_DOLLAR = "yield_per_dollar"
LEGACY_YIELD_PER_TOTAL_DOLLAR = "yield_per_total_dollar"
LEGACY_YIELD_PER_SCOREABLE_DOLLAR = "yield_per_scoreable_dollar"
LEGACY_PASS_RATE = "pass_rate"

NORTH_STAR_METRIC_FIELDS = [
    FIELD_RESOLVED_COUNT,
    FIELD_RESOLVED_RATE,
    FIELD_TOTAL_SPEND,
    FIELD_COST_PER_RESOLVED_TASK,
    FIELD_TOTAL_RESOLVED_VALUE,
    FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR,
]

# Display column headers for report tables
DISPLAY_HEADERS = {
    FIELD_RESOLVED_COUNT: "Resolved",
    FIELD_RESOLVED_RATE: "Rate (%)",
    FIELD_TOTAL_SPEND: "Spend ($)",
    FIELD_COST_PER_RESOLVED_TASK: "$/Resolved",
    FIELD_TOTAL_RESOLVED_VALUE: "Total Resolved Value",
    FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR: "Resolved Value/$",
}

LEGACY_DISPLAY_HEADERS = {
    LEGACY_YIELD_SCORE: "Total Resolved Value",
    LEGACY_YIELD_COVERAGE: "coverage",
    LEGACY_YIELD_PER_DOLLAR: "Resolved Value/score$",
    LEGACY_YIELD_PER_TOTAL_DOLLAR: "Resolved Value/total$",
    LEGACY_YIELD_PER_SCOREABLE_DOLLAR: "Resolved Value/score$",
    LEGACY_PASS_RATE: "resolved_rate",
}


def resolved_field(stats: dict, *, key: str, default=0.0) -> float:
    """Read *key* from *stats*, trying both the North Star name and the legacy
    alias when *key* is a North Star field.

    Legacy fields in historical records use ``yield_score``,
    ``yield_per_dollar``, etc.  Newly computed stats carry both names.
    This helper lets reporting code read new names while falling back to
    legacy names from old record data.
    """
    if key in stats:
        return float(stats[key])
    # Fall back to legacy aliases, in semantic order.
    for alias in _legacy_aliases_for(key):
        if alias in stats:
            return float(stats[alias])
    return default


def _legacy_aliases_for(key: str) -> tuple[str, ...]:
    _map = {
        FIELD_TOTAL_RESOLVED_VALUE: (LEGACY_YIELD_SCORE,),
        # North Star value-per-dollar uses total spend. Prefer the legacy
        # total-dollar alias before falling back to scoreable-dollar aliases.
        FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR: (
            LEGACY_YIELD_PER_TOTAL_DOLLAR,
            LEGACY_YIELD_PER_DOLLAR,
        ),
        FIELD_RESOLVED_COUNT: ("pass",),
        FIELD_RESOLVED_RATE: (LEGACY_PASS_RATE,),
    }
    return _map.get(key, ())


def build_standard_metrics(
    *,
    resolved_count: int,
    total_tasks: int,
    total_spend: float,
    total_resolved_value: float,
) -> dict[str, float | int]:
    """Return a dict with all six North Star metric fields computed.

    Callers that already have these aggregates can use this instead of
    computing each field manually.
    """
    resolved_rate = resolved_count / total_tasks if total_tasks > 0 else 0.0
    cost_per_resolved = total_spend / resolved_count if resolved_count > 0 else float("inf")
    resolved_value_per_dollar = (
        total_resolved_value / total_spend if total_spend > 0 else 0.0
    )
    return {
        FIELD_RESOLVED_COUNT: resolved_count,
        FIELD_RESOLVED_RATE: round(resolved_rate, 6),
        FIELD_TOTAL_SPEND: round(total_spend, 6),
        FIELD_COST_PER_RESOLVED_TASK: round(cost_per_resolved, 6),
        FIELD_TOTAL_RESOLVED_VALUE: round(total_resolved_value, 6),
        FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR: round(resolved_value_per_dollar, 6),
    }


def enrich_strategy_summary(summary: dict) -> dict:
    """Add North Star field names to a per-strategy summary dict.

    Reads from whichever fields are already present (North Star or legacy)
    and ensures both sets exist.  Mutates and returns *summary*.
    """
    # resolved_count
    if FIELD_RESOLVED_COUNT not in summary:
        if "pass" in summary:
            summary[FIELD_RESOLVED_COUNT] = int(summary["pass"])
        elif "resolved" in summary:
            summary[FIELD_RESOLVED_COUNT] = int(summary["resolved"])
        else:
            summary[FIELD_RESOLVED_COUNT] = 0

    # total_resolved_value
    if FIELD_TOTAL_RESOLVED_VALUE not in summary:
        summary[FIELD_TOTAL_RESOLVED_VALUE] = float(
            summary.get(LEGACY_YIELD_SCORE, summary.get("resolved_value", 0.0))
        )

    # total_spend
    if FIELD_TOTAL_SPEND not in summary:
        base_cost = float(summary.get("total_cost", summary.get("cost", 0.0)) or 0.0)
        abort_cost = float(summary.get("abort_cost", 0.0) or 0.0)
        summary[FIELD_TOTAL_SPEND] = base_cost + abort_cost

    # resolved_rate
    if FIELD_RESOLVED_RATE not in summary:
        total = summary.get("scoreable_count")
        if total is None:
            if "pass" in summary and "fail" in summary:
                total = int(summary["pass"]) + int(summary["fail"])
            elif "pass" in summary and "true_fail" in summary:
                total = int(summary["pass"]) + int(summary["true_fail"])
            else:
                total = summary.get("total", 0)
        resolved_count = summary[FIELD_RESOLVED_COUNT]
        summary[FIELD_RESOLVED_RATE] = round(
            resolved_count / total if total > 0 else 0.0, 6
        )

    # cost_per_resolved_task
    if FIELD_COST_PER_RESOLVED_TASK not in summary:
        total_spend = summary[FIELD_TOTAL_SPEND]
        resolved_count = summary[FIELD_RESOLVED_COUNT]
        summary[FIELD_COST_PER_RESOLVED_TASK] = round(
            total_spend / resolved_count if resolved_count > 0 else float("inf"), 6
        )

    # total_resolved_value_per_dollar
    if FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR not in summary:
        total_spend = summary[FIELD_TOTAL_SPEND]
        total_value = summary[FIELD_TOTAL_RESOLVED_VALUE]
        summary[FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR] = round(
            total_value / total_spend if total_spend > 0 else 0.0, 6
        )

    return summary


def display_name(field: str) -> str:
    """Return the North Star display column header for *field*."""
    return DISPLAY_HEADERS.get(field, LEGACY_DISPLAY_HEADERS.get(field, field))

from __future__ import annotations

import pytest

from budgetflow.metrics_reporting import (
    FIELD_RESOLVED_COUNT,
    FIELD_RESOLVED_RATE,
    FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR,
    display_name,
    enrich_strategy_summary,
    resolved_field,
)


def test_enrich_strategy_summary_does_not_treat_value_as_resolved_count() -> None:
    summary = enrich_strategy_summary({
        "yield_score": 2.5,
        "total": 4,
        "total_cost": 1.0,
    })

    assert summary[FIELD_RESOLVED_COUNT] == 0
    assert summary[FIELD_RESOLVED_RATE] == 0.0


def test_enrich_strategy_summary_uses_pass_count_for_resolved_count() -> None:
    summary = enrich_strategy_summary({
        "pass": 2,
        "fail": 1,
        "abort": 1,
        "yield_score": 2.5,
        "total_cost": 0.8,
        "abort_cost": 0.2,
    })

    assert summary[FIELD_RESOLVED_COUNT] == 2
    assert summary[FIELD_RESOLVED_RATE] == pytest.approx(2 / 3)
    assert summary["cost_per_resolved_task"] == pytest.approx(0.5)
    assert summary[FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR] == pytest.approx(2.5)


def test_resolved_field_prefers_total_dollar_legacy_alias_for_value_per_dollar() -> None:
    stats = {
        "yield_per_dollar": 4.0,
        "yield_per_total_dollar": 2.0,
    }

    assert resolved_field(
        stats,
        key=FIELD_TOTAL_RESOLVED_VALUE_PER_DOLLAR,
    ) == pytest.approx(2.0)


def test_display_name_does_not_emit_retired_yield_labels() -> None:
    assert display_name("yield_score") == "Total Resolved Value"
    assert display_name("yield_per_dollar") == "Resolved Value/score$"
    assert display_name("yield_per_total_dollar") == "Resolved Value/total$"

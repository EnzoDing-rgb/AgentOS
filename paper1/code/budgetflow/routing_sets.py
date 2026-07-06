from __future__ import annotations

ADAPTIVE_ROUTINGS = frozenset(
    {
        "budgetflow_segment",
        "budgetflow_conservative",
        "segment_value_aware",
        "value_aware_task_level",
        "budgetflow_equal_weight",
        "stage_blind",
    }
)

VALUE_AWARE_ROUTINGS = frozenset({"segment_value_aware", "value_aware_task_level"})

IN_TASK_SWITCHING_ROUTINGS = ADAPTIVE_ROUTINGS - frozenset({"value_aware_task_level"})

VALUE_TRIGGERED_ESCALATION_ROUTINGS = frozenset({"segment_value_aware"})

GOLD_EDIT_REPAIR_GUARD_ROUTINGS = (ADAPTIVE_ROUTINGS | frozenset({"budget_only"})) - frozenset(
    {"value_aware_task_level"}
)


def is_adaptive_routing(routing: str) -> bool:
    return routing in ADAPTIVE_ROUTINGS

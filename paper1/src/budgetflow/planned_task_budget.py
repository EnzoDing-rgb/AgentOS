from __future__ import annotations


def effective_planned_task_cap(
    *,
    planned_task_caps: dict[str, float],
    remaining_task_ids: list[str],
    task_id: str,
    batch_budget_cap: float,
    shared_spent: float,
) -> float | None:
    """Return the live task hard cap implied by a shared hard budget.

    ``planned_task_caps`` are compiled demand weights and may sum above the
    shared cap. This function clips the current task against the remaining
    shared pool and remaining planned demand. The returned value is the
    per-task execution cap for policies that opt into planned task budgets.
    """
    planned_cap = float(planned_task_caps.get(task_id, 0.0) or 0.0)
    if planned_cap <= 0:
        return None
    shared_remaining = max(0.0, float(batch_budget_cap) - max(0.0, float(shared_spent)))
    if shared_remaining <= 0:
        return 0.0
    remaining_planned = sum(
        max(0.0, float(planned_task_caps.get(str(remaining_id), 0.0) or 0.0))
        for remaining_id in remaining_task_ids
    )
    if remaining_planned <= 0:
        return min(planned_cap, shared_remaining)
    if remaining_planned <= shared_remaining:
        return min(planned_cap, shared_remaining)
    return min(planned_cap, shared_remaining * planned_cap / remaining_planned)

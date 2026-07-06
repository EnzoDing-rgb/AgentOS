from __future__ import annotations


def effective_planned_task_cap(
    *,
    planned_task_caps: dict[str, float],
    task_id: str,
    batch_budget_cap: float,
    shared_spent: float,
) -> float | None:
    """Return the live task hard cap implied by a shared hard budget.

    ``planned_task_caps`` are compiled per-task runways and may sum above the
    shared cap. The current task may spend up to its planned runway, clipped
    only by the live shared pool. Shared-budget pressure is a routing signal;
    it must not shrink a task runway by the ratio of remaining planned demand,
    because that turns a loose stop-loss into premature truncation.
    """
    planned_cap = float(planned_task_caps.get(task_id, 0.0) or 0.0)
    if planned_cap <= 0:
        return None
    shared_remaining = max(0.0, float(batch_budget_cap) - max(0.0, float(shared_spent)))
    if shared_remaining <= 0:
        return 0.0
    return min(planned_cap, shared_remaining)

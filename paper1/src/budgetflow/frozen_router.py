"""Pre-registered frozen router plan for mechanism isolation experiments.

A frozen plan is a static mapping from instance_id to preferred_model, base_cap,
and priority. It does NOT read runtime progress, learn, or share a dynamic ledger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrozenPlanEntry:
    instance_id: str
    preferred_model: str
    base_cap: float
    priority: int


@dataclass(frozen=True)
class FrozenRouterPlan:
    name: str
    plan: dict[str, FrozenPlanEntry]

    def lookup(self, instance_id: str) -> FrozenPlanEntry | None:
        return self.plan.get(instance_id)

    def as_jsonl_record(self, instance_id: str) -> dict:
        entry = self.lookup(instance_id)
        if entry is None:
            return {"frozen_plan_name": self.name, "frozen_plan_entry": None}
        return {
            "frozen_plan_name": self.name,
            "frozen_plan_preferred_model": entry.preferred_model,
            "frozen_plan_base_cap": entry.base_cap,
            "frozen_plan_priority": entry.priority,
        }


def load_frozen_plan(path: str | Path) -> FrozenRouterPlan:
    raw = json.loads(Path(path).read_text())
    meta = raw.get("meta", {})
    name = str(meta.get("name", Path(path).stem))
    plan_data = raw.get("plan", raw.get("tasks", {}))
    if not isinstance(plan_data, dict) or not plan_data:
        raise ValueError("frozen router plan must contain a non-empty 'plan' object")
    plan: dict[str, FrozenPlanEntry] = {}
    for instance_id, entry in plan_data.items():
        if not isinstance(entry, dict):
            raise ValueError(f"frozen plan entry {instance_id!r} must be an object")
        missing = [field for field in ("preferred_model", "base_cap", "priority") if field not in entry]
        if missing:
            raise ValueError(f"frozen plan entry {instance_id!r} missing required fields: {missing}")
        base_cap = float(entry["base_cap"])
        priority = int(entry["priority"])
        preferred_model = str(entry["preferred_model"])
        if not preferred_model:
            raise ValueError(f"frozen plan entry {instance_id!r} has empty preferred_model")
        if base_cap <= 0:
            raise ValueError(f"frozen plan entry {instance_id!r} has non-positive base_cap={base_cap}")
        if priority < 0:
            raise ValueError(f"frozen plan entry {instance_id!r} has negative priority={priority}")
        plan[instance_id] = FrozenPlanEntry(
            instance_id=instance_id,
            preferred_model=preferred_model,
            base_cap=base_cap,
            priority=priority,
        )
    return FrozenRouterPlan(name=name, plan=plan)

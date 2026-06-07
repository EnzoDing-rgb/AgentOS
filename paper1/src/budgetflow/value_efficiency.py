"""Value-driven token-efficiency metrics for BudgetFlow.

Tier 1 is the paper objective: verified resolved value per dollar. Tier 2 is
the equal-value special case used as a mechanism ablation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValueEfficiencyContext:
    profile: str = "equal"
    matrix_path: str | None = None
    lookup: dict[str, float] | None = None
    median_task_value: float = 1.0

    @property
    def objective(self) -> str:
        return "t2_equal_value_ablation" if self.profile == "equal" else "t1_value_efficiency"

    def init(self, *, value_profile: str = "equal", value_matrix_path: str | None = None) -> None:
        self.profile = value_profile
        self.matrix_path = value_matrix_path
        self.lookup = None
        self.median_task_value = 1.0
        if value_matrix_path:
            artifact = json.loads(Path(value_matrix_path).read_text())
            self.lookup = _extract_lookup(artifact, value_profile)
            if self.lookup:
                self.median_task_value = _median(self.lookup.values())
            elif value_profile != "equal":
                print(
                    f"[value_observability] WARNING: profile '{value_profile}' not found "
                    f"in value matrix {value_matrix_path}",
                    flush=True,
                )

    def task_value(self, instance_id: str) -> tuple[float, str]:
        if self.lookup is not None and instance_id in self.lookup:
            return float(self.lookup[instance_id]), "value_matrix"
        if self.profile == "equal":
            return 1.0, "default_equal"
        raise SystemExit(
            f"[value_observability] FATAL: instance_id='{instance_id}' not found "
            f"in value matrix {self.matrix_path} for profile '{self.profile}'. "
            f"Either add this task to the matrix or use --value-profile=equal."
        )

    def enrich_record(self, record: dict) -> dict:
        """Add value-efficiency observability fields. Mutates and returns."""
        instance_id = str(record.get("instance_id", ""))
        resolved = bool(record.get("harness_resolved"))
        task_cost = float(record.get("task_cost") or record.get("total_cost") or 0)
        task_value, value_source = self.task_value(instance_id)
        resolved_value = task_value if resolved else 0.0
        rvpd = resolved_value / task_cost if task_cost > 0 else 0.0

        routing = str(record.get("routing", ""))
        va_active = routing == "budgetflow_value_aware"
        record["value_objective"] = self.objective
        record["task_value_profile"] = self.profile
        record["task_value"] = task_value
        record["resolved_value"] = resolved_value
        record["value_source"] = value_source
        record["value_matrix_artifact"] = self.matrix_path
        record["resolved_value_per_dollar"] = round(rvpd, 6)
        record["va_active"] = va_active
        if va_active:
            raw = task_value / max(0.001, self.median_task_value) if self.median_task_value > 0 else 1.0
            record["task_value_multiplier"] = round(max(0.5, min(2.0, raw)), 4)
        else:
            record["task_value_multiplier"] = None

        if record.get("auto_budget_enabled"):
            record["budget_source"] = "auto_budget"
        elif record.get("budget_memory_enabled"):
            record["budget_source"] = "budget_memory"
        else:
            record["budget_source"] = "static_cap"
        return record

    def summary_for_strategy(self, records: list[dict]) -> dict:
        resolved_count = sum(1 for r in records if r.get("harness_resolved"))
        total_cost = sum(float(r.get("task_cost") or r.get("total_cost") or 0) for r in records)
        resolved_value = sum(float(r.get("resolved_value") or 0) for r in records)
        total_task_value = sum(float(r.get("task_value") or 1.0) for r in records)
        rvpd = resolved_value / total_cost if total_cost > 0 else 0.0
        return {
            "resolved_count": resolved_count,
            "total_cost": round(total_cost, 6),
            "resolved_value": round(resolved_value, 6),
            "total_task_value": round(total_task_value, 6),
            "resolved_value_per_dollar": round(rvpd, 6),
            "value_profile": self.profile,
            "value_source": self.matrix_path or "default_equal",
            "value_objective": self.objective,
        }


def _extract_lookup(artifact: dict, profile: str) -> dict[str, float] | None:
    tasks = artifact.get("tasks")
    if isinstance(tasks, dict) and tasks:
        lookup: dict[str, float] = {}
        for instance_id, task_data in tasks.items():
            if not isinstance(task_data, dict):
                continue
            values = task_data.get("values")
            if isinstance(values, dict) and profile in values:
                lookup[instance_id] = float(values[profile])
        if lookup:
            return lookup

    matrix = artifact.get("matrix", {})
    profile_data = matrix.get(profile) if isinstance(matrix, dict) else None
    if profile_data and isinstance(profile_data, dict):
        return {
            task_id: float(entry.get("value", 1.0))
            for task_id, entry in profile_data.items()
            if isinstance(entry, dict)
        }
    return None


def _median(values) -> float:
    vals = sorted(float(v) for v in values)
    if not vals:
        return 1.0
    n = len(vals)
    return (vals[n // 2 - 1] + vals[n // 2]) / 2.0 if n % 2 == 0 else vals[n // 2]
